# Copyright 2025 Flower Labs GmbH. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Contextmanager for a gRPC request-response channel to the Flower server."""


from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from logging import DEBUG, ERROR
from pathlib import Path
from typing import Callable, Optional, Union, cast

import grpc
from cryptography.hazmat.primitives.asymmetric import ec

from flwr.common import GRPC_MAX_MESSAGE_LENGTH
from flwr.common.constant import HEARTBEAT_CALL_TIMEOUT, HEARTBEAT_DEFAULT_INTERVAL
from flwr.common.grpc import create_channel, on_channel_state_change
from flwr.common.heartbeat import HeartbeatSender
from flwr.common.inflatable import (
    get_all_nested_objects,
    get_object_tree,
    iterate_object_tree,
    no_object_id_recompute,
)
from flwr.common.inflatable_protobuf_utils import (
    make_pull_object_fn_protobuf,
    make_push_object_fn_protobuf,
)
from flwr.common.inflatable_utils import (
    inflate_object_from_contents,
    pull_objects,
    push_objects,
)
from flwr.common.logger import log
from flwr.common.message import Message, remove_content_from_message
from flwr.common.retry_invoker import RetryInvoker, _wrap_stub
from flwr.common.secure_aggregation.crypto.symmetric_encryption import (
    generate_key_pairs,
)
from flwr.common.serde import message_to_proto, run_from_proto
from flwr.common.typing import Fab, Run, RunNotRunningException
from flwr.proto.fab_pb2 import GetFabRequest, GetFabResponse  # pylint: disable=E0611
from flwr.proto.fleet_pb2 import (  # pylint: disable=E0611
    CreateNodeRequest,
    DeleteNodeRequest,
    PullMessagesRequest,
    PullMessagesResponse,
    PushMessagesRequest,
    PushMessagesResponse,
)
from flwr.proto.fleet_pb2_grpc import FleetStub  # pylint: disable=E0611
from flwr.proto.heartbeat_pb2 import (  # pylint: disable=E0611
    SendNodeHeartbeatRequest,
    SendNodeHeartbeatResponse,
)
from flwr.proto.message_pb2 import (  # pylint: disable=E0611
    ConfirmMessageReceivedRequest,
)
from flwr.proto.node_pb2 import Node  # pylint: disable=E0611
from flwr.proto.run_pb2 import GetRunRequest, GetRunResponse  # pylint: disable=E0611

from .client_interceptor import AuthenticateClientInterceptor
from .grpc_adapter import GrpcAdapter


@contextmanager
def grpc_request_response(  # pylint: disable=R0913,R0914,R0915,R0917
    server_address: str,
    insecure: bool,
    retry_invoker: RetryInvoker,
    max_message_length: int = GRPC_MAX_MESSAGE_LENGTH,  # pylint: disable=W0613
    root_certificates: Optional[Union[bytes, str]] = None,
    authentication_keys: Optional[
        tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
    ] = None,
    adapter_cls: Optional[Union[type[FleetStub], type[GrpcAdapter]]] = None,
) -> Iterator[
    tuple[
        Callable[[], Optional[Message]],
        Callable[[Message], None],
        Callable[[], Optional[int]],
        Callable[[], None],
        Callable[[int], Run],
        Callable[[str, int], Fab],
    ]
]:
    """Primitives for request/response-based interaction with a server.

    One notable difference to the grpc_connection context manager is that
    `receive` can return `None`.

    Parameters
    ----------
    server_address : str
        The IPv6 address of the server with `http://` or `https://`.
        If the Flower server runs on the same machine
        on port 8080, then `server_address` would be `"http://[::]:8080"`.
    insecure : bool
        Starts an insecure gRPC connection when True. Enables HTTPS connection
        when False, using system certificates if `root_certificates` is None.
    retry_invoker: RetryInvoker
        `RetryInvoker` object that will try to reconnect the client to the server
        after gRPC errors. If None, the client will only try to
        reconnect once after a failure.
    max_message_length : int
        Ignored, only present to preserve API-compatibility.
    root_certificates : Optional[Union[bytes, str]] (default: None)
        Path of the root certificate. If provided, a secure
        connection using the certificates will be established to an SSL-enabled
        Flower server. Bytes won't work for the REST API.
    authentication_keys : Optional[Tuple[PrivateKey, PublicKey]] (default: None)
        Tuple containing the elliptic curve private key and public key for
        authentication from the cryptography library.
        Source: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ec/
        Used to establish an authenticated connection with the server.
    adapter_cls: Optional[Union[type[FleetStub], type[GrpcAdapter]]] (default: None)
        A GrpcStub Class that can be used to send messages. By default the FleetStub
        will be used.

    Returns
    -------
    receive : Callable
    send : Callable
    create_node : Optional[Callable]
    delete_node : Optional[Callable]
    get_run : Optional[Callable]
    """
    if isinstance(root_certificates, str):
        root_certificates = Path(root_certificates).read_bytes()

    # Automatic node auth: generate keys if user didn't provide any
    if authentication_keys is None:
        authentication_keys = generate_key_pairs()

    # Always configure auth interceptor, with either user-provided or generated keys
    interceptors: Sequence[grpc.UnaryUnaryClientInterceptor] = [
        AuthenticateClientInterceptor(*authentication_keys),
    ]
    channel = create_channel(
        server_address=server_address,
        insecure=insecure,
        root_certificates=root_certificates,
        max_message_length=max_message_length,
        interceptors=interceptors,
    )
    channel.subscribe(on_channel_state_change)

    # Shared variables for inner functions
    if adapter_cls is None:
        adapter_cls = FleetStub
    stub = adapter_cls(channel)
    node: Optional[Node] = None

    def _should_giveup_fn(e: Exception) -> bool:
        if e.code() == grpc.StatusCode.PERMISSION_DENIED:  # type: ignore
            raise RunNotRunningException
        if e.code() == grpc.StatusCode.UNAVAILABLE:  # type: ignore
            return False
        return True

    # Restrict retries to cases where the status code is UNAVAILABLE
    # If the status code is PERMISSION_DENIED, additionally raise RunNotRunningException
    retry_invoker.should_giveup = _should_giveup_fn

    # Wrap stub
    _wrap_stub(stub, retry_invoker)
    ###########################################################################
    # send_node_heartbeat/create_node/delete_node/receive/send/get_run functions
    ###########################################################################

    def send_node_heartbeat() -> bool:
        # Get Node
        if node is None:
            log(ERROR, "Node instance missing")
            return False

        # Construct the heartbeat request
        req = SendNodeHeartbeatRequest(
            node=node, heartbeat_interval=HEARTBEAT_DEFAULT_INTERVAL
        )

        # Call FleetAPI
        try:
            res: SendNodeHeartbeatResponse = stub.SendNodeHeartbeat(
                req, timeout=HEARTBEAT_CALL_TIMEOUT
            )
        except grpc.RpcError as e:
            status_code = e.code()
            if status_code == grpc.StatusCode.UNAVAILABLE:
                return False
            if status_code == grpc.StatusCode.DEADLINE_EXCEEDED:
                return False
            raise

        # Check if success
        if not res.success:
            raise RuntimeError(
                "Heartbeat failed unexpectedly. The SuperLink does not "
                "recognize this SuperNode."
            )
        return True

    heartbeat_sender = HeartbeatSender(send_node_heartbeat)

    def create_node() -> Optional[int]:
        """Set create_node."""
        # Call FleetAPI
        create_node_request = CreateNodeRequest(
            heartbeat_interval=HEARTBEAT_DEFAULT_INTERVAL
        )
        create_node_response = stub.CreateNode(request=create_node_request)

        # Remember the node and start the heartbeat sender
        nonlocal node
        node = cast(Node, create_node_response.node)
        heartbeat_sender.start()
        return node.node_id

    def delete_node() -> None:
        """Set delete_node."""
        # Get Node
        nonlocal node
        if node is None:
            log(ERROR, "Node instance missing")
            return

        # Stop the heartbeat sender
        heartbeat_sender.stop()

        # Call FleetAPI
        delete_node_request = DeleteNodeRequest(node=node)
        stub.DeleteNode(request=delete_node_request)

        # Cleanup
        node = None

    def receive() -> Optional[Message]:
        """Receive next message from server."""
        # Get Node
        if node is None:
            log(ERROR, "Node instance missing")
            return None

        # Request instructions (message) from server
        request = PullMessagesRequest(node=node)
        response: PullMessagesResponse = stub.PullMessages(request=request)

        # Get the current Messages
        message_proto = (
            None if len(response.messages_list) == 0 else response.messages_list[0]
        )

        # Discard the current message if not valid
        if message_proto is not None and not (
            message_proto.metadata.dst_node_id == node.node_id
        ):
            message_proto = None

        # Construct the Message
        in_message: Optional[Message] = None

        if message_proto:
            msg_id = message_proto.metadata.message_id
            run_id = message_proto.metadata.run_id
            object_tree = response.message_object_trees[0]
            all_object_contents = pull_objects(
                [tree.object_id for tree in iterate_object_tree(object_tree)],
                pull_object_fn=make_pull_object_fn_protobuf(
                    pull_object_protobuf=stub.PullObject,
                    node=node,
                    run_id=run_id,
                ),
            )

            # Confirm that the message has been received
            stub.ConfirmMessageReceived(
                ConfirmMessageReceivedRequest(
                    node=node, run_id=run_id, message_object_id=msg_id
                )
            )

            in_message = cast(
                Message, inflate_object_from_contents(msg_id, all_object_contents)
            )
            # The deflated message doesn't contain the message_id (its own object_id)
            # Inject
            in_message.metadata.__dict__["_message_id"] = msg_id

        # Return the message if available
        return in_message

    def send(message: Message) -> None:
        """Send message reply to server."""
        # Get Node
        if node is None:
            log(ERROR, "Node instance missing")
            return

        with no_object_id_recompute():
            # Get all nested objects
            all_objects = get_all_nested_objects(message)
            object_tree = get_object_tree(message)

            # Serialize Message
            message_proto = message_to_proto(
                message=remove_content_from_message(message)
            )
            request = PushMessagesRequest(
                node=node,
                messages_list=[message_proto],
                message_object_trees=[object_tree],
            )
            response: PushMessagesResponse = stub.PushMessages(request=request)

            if response.objects_to_push:
                objs_to_push = set(
                    response.objects_to_push[message.object_id].object_ids
                )
                push_objects(
                    all_objects,
                    push_object_fn=make_push_object_fn_protobuf(
                        push_object_protobuf=stub.PushObject,
                        node=node,
                        run_id=message.metadata.run_id,
                    ),
                    object_ids_to_push=objs_to_push,
                )
                log(DEBUG, "Pushed %s objects to servicer.", len(objs_to_push))

    def get_run(run_id: int) -> Run:
        # Call FleetAPI
        get_run_request = GetRunRequest(node=node, run_id=run_id)
        get_run_response: GetRunResponse = stub.GetRun(request=get_run_request)

        # Return fab_id and fab_version
        return run_from_proto(get_run_response.run)

    def get_fab(fab_hash: str, run_id: int) -> Fab:
        # Call FleetAPI
        get_fab_request = GetFabRequest(node=node, hash_str=fab_hash, run_id=run_id)
        get_fab_response: GetFabResponse = stub.GetFab(request=get_fab_request)

        return Fab(get_fab_response.fab.hash_str, get_fab_response.fab.content)

    try:
        # Yield methods
        yield (receive, send, create_node, delete_node, get_run, get_fab)
    except Exception as exc:  # pylint: disable=broad-except
        log(ERROR, exc)
    # Cleanup
    finally:
        try:
            if node is not None:
                # Disable retrying
                retry_invoker.max_tries = 1
                delete_node()
        except grpc.RpcError:
            pass
        channel.close()
