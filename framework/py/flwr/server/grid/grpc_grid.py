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
"""Flower gRPC Grid."""


import time
from collections.abc import Iterable
from logging import DEBUG, ERROR, WARNING
from typing import Optional, cast

import grpc

from flwr.common import Message, RecordDict
from flwr.common.constant import (
    SERVERAPPIO_API_DEFAULT_CLIENT_ADDRESS,
    SUPERLINK_NODE_ID,
)
from flwr.common.grpc import create_channel, on_channel_state_change
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
from flwr.common.logger import log, warn_deprecated_feature
from flwr.common.message import remove_content_from_message
from flwr.common.retry_invoker import _make_simple_grpc_retry_invoker, _wrap_stub
from flwr.common.serde import message_to_proto, run_from_proto
from flwr.common.typing import Run
from flwr.proto.appio_pb2 import (  # pylint: disable=E0611
    PullAppMessagesRequest,
    PullAppMessagesResponse,
    PushAppMessagesRequest,
    PushAppMessagesResponse,
)
from flwr.proto.message_pb2 import (  # pylint: disable=E0611
    ConfirmMessageReceivedRequest,
)
from flwr.proto.node_pb2 import Node  # pylint: disable=E0611
from flwr.proto.run_pb2 import GetRunRequest, GetRunResponse  # pylint: disable=E0611
from flwr.proto.serverappio_pb2 import (  # pylint: disable=E0611
    GetNodesRequest,
    GetNodesResponse,
)
from flwr.proto.serverappio_pb2_grpc import ServerAppIoStub  # pylint: disable=E0611

from .grid import Grid

ERROR_MESSAGE_PUSH_MESSAGES_RESOURCE_EXHAUSTED = """

[Grid.push_messages] gRPC error occurred:

The 2GB gRPC limit has been reached. Consider reducing the number of messages pushed
at once, or push messages individually, for example:

> msgs = [msg1, msg2, msg3]
> msg_ids = []
> for msg in msgs:
>     msg_id = grid.push_messages([msg])
>     msg_ids.extend(msg_id)
"""

ERROR_MESSAGE_PULL_MESSAGES_RESOURCE_EXHAUSTED = """

[Grid.pull_messages] gRPC error occurred:

The 2GB gRPC limit has been reached. Consider reducing the number of messages pulled
at once, or pull messages individually, for example:

> msgs_ids = [msg_id1, msg_id2, msg_id3]
> msgs = []
> for msg_id in msg_ids:
>     msg = grid.pull_messages([msg_id])
>     msgs.extend(msg)
"""


class GrpcGrid(Grid):
    """`GrpcGrid` provides an interface to the ServerAppIo API.

    Parameters
    ----------
    serverappio_service_address : str (default: "[::]:9091")
        The address (URL, IPv6, IPv4) of the SuperLink ServerAppIo API service.
    root_certificates : Optional[bytes] (default: None)
        The PEM-encoded root certificates as a byte string.
        If provided, a secure connection using the certificates will be
        established to an SSL-enabled Flower server.
    """

    _deprecation_warning_logged = False

    def __init__(  # pylint: disable=too-many-arguments
        self,
        serverappio_service_address: str = SERVERAPPIO_API_DEFAULT_CLIENT_ADDRESS,
        root_certificates: Optional[bytes] = None,
    ) -> None:
        self._addr = serverappio_service_address
        self._cert = root_certificates
        self._run: Optional[Run] = None
        self._grpc_stub: Optional[ServerAppIoStub] = None
        self._channel: Optional[grpc.Channel] = None
        self.node = Node(node_id=SUPERLINK_NODE_ID)
        self._retry_invoker = _make_simple_grpc_retry_invoker()
        super().__init__()

    @property
    def _is_connected(self) -> bool:
        """Check if connected to the ServerAppIo API server."""
        return self._channel is not None

    def _connect(self) -> None:
        """Connect to the ServerAppIo API.

        This will not call GetRun.
        """
        if self._is_connected:
            log(WARNING, "Already connected")
            return
        self._channel = create_channel(
            server_address=self._addr,
            insecure=(self._cert is None),
            root_certificates=self._cert,
        )
        self._channel.subscribe(on_channel_state_change)
        self._grpc_stub = ServerAppIoStub(self._channel)
        _wrap_stub(self._grpc_stub, self._retry_invoker)
        log(DEBUG, "[flwr-serverapp] Connected to %s", self._addr)

    def _disconnect(self) -> None:
        """Disconnect from the ServerAppIo API."""
        if not self._is_connected:
            log(DEBUG, "Already disconnected")
            return
        channel: grpc.Channel = self._channel
        self._channel = None
        self._grpc_stub = None
        channel.close()
        log(DEBUG, "[flwr-serverapp] Disconnected")

    def set_run(self, run_id: int) -> None:
        """Set the run."""
        # Get the run info
        req = GetRunRequest(run_id=run_id)
        res: GetRunResponse = self._stub.GetRun(req)
        if not res.HasField("run"):
            raise RuntimeError(f"Cannot find the run with ID: {run_id}")
        self._run = run_from_proto(res.run)

    @property
    def run(self) -> Run:
        """Run information."""
        return Run(**vars(self._run))

    @property
    def _stub(self) -> ServerAppIoStub:
        """ServerAppIo stub."""
        if not self._is_connected:
            self._connect()
        return cast(ServerAppIoStub, self._grpc_stub)

    def _check_message(self, message: Message) -> None:
        # Check if the message is valid
        if not (
            message.metadata.message_id != ""
            and message.metadata.reply_to_message_id == ""
            and message.metadata.ttl > 0
        ):
            raise ValueError(f"Invalid message: {message}")

    def create_message(  # pylint: disable=too-many-arguments,R0917
        self,
        content: RecordDict,
        message_type: str,
        dst_node_id: int,
        group_id: str,
        ttl: Optional[float] = None,
    ) -> Message:
        """Create a new message with specified parameters.

        This method constructs a new `Message` with given content and metadata.
        The `run_id` and `src_node_id` will be set automatically.
        """
        if not GrpcGrid._deprecation_warning_logged:
            GrpcGrid._deprecation_warning_logged = True
            warn_deprecated_feature(
                "`Driver.create_message` / `Grid.create_message` is deprecated."
                "Use `Message` constructor instead."
            )
        return Message(content, dst_node_id, message_type, ttl=ttl, group_id=group_id)

    def get_node_ids(self) -> Iterable[int]:
        """Get node IDs."""
        # Call GrpcServerAppIoStub method
        res: GetNodesResponse = self._stub.GetNodes(
            GetNodesRequest(run_id=cast(Run, self._run).run_id)
        )
        return [node.node_id for node in res.nodes]

    def _try_push_message(self, run_id: int, message: Message) -> str:
        """Push one message and its associated objects."""
        # Compute mapping of message descendants
        all_objects = get_all_nested_objects(message)
        msg_id = message.object_id
        object_tree = get_object_tree(message)

        # Call GrpcServerAppIoStub method
        res: PushAppMessagesResponse = self._stub.PushMessages(
            PushAppMessagesRequest(
                messages_list=[message_to_proto(remove_content_from_message(message))],
                run_id=run_id,
                message_object_trees=[object_tree],
            )
        )

        # Push objects
        # If Message was added to the LinkState correctly
        if msg_id is not None:
            obj_ids_to_push = set(res.objects_to_push[msg_id].object_ids)
            # Push only object that are not in the store
            push_objects(
                all_objects,
                push_object_fn=make_push_object_fn_protobuf(
                    push_object_protobuf=self._stub.PushObject,
                    node=self.node,
                    run_id=run_id,
                ),
                object_ids_to_push=obj_ids_to_push,
            )
        return msg_id

    def push_messages(self, messages: Iterable[Message]) -> Iterable[str]:
        """Push messages to specified node IDs.

        This method takes an iterable of messages and sends each message
        to the node specified in `dst_node_id`.
        """
        # Construct Messages
        run_id = cast(Run, self._run).run_id
        message_ids: list[str] = []
        try:
            for msg in messages:
                # Populate metadata
                msg.metadata.__dict__["_run_id"] = run_id
                msg.metadata.__dict__["_src_node_id"] = self.node.node_id
                msg.metadata.__dict__["_message_id"] = msg.object_id
                # Check message
                self._check_message(msg)
                # Try pushing message and its objects
                with no_object_id_recompute():
                    message_ids.append(self._try_push_message(run_id, msg))

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:  # pylint: disable=E1101
                log(ERROR, ERROR_MESSAGE_PUSH_MESSAGES_RESOURCE_EXHAUSTED)
                return []
            raise

        if None in message_ids:
            log(
                WARNING,
                "Not all messages could be pushed to the SuperLink. The returned "
                "list has `None` for those messages (the order is preserved as "
                "passed to `push_messages`). This could be due to a malformed "
                "message.",
            )

        return message_ids

    def pull_messages(self, message_ids: Iterable[str]) -> Iterable[Message]:
        """Pull messages based on message IDs.

        This method is used to collect messages from the SuperLink that correspond to a
        set of given message IDs.
        """
        run_id = cast(Run, self._run).run_id
        try:
            # Pull Messages
            res: PullAppMessagesResponse = self._stub.PullMessages(
                PullAppMessagesRequest(
                    message_ids=message_ids,
                    run_id=run_id,
                )
            )
            # Pull Messages from store
            inflated_msgs: list[Message] = []
            for msg_proto, msg_tree in zip(res.messages_list, res.message_object_trees):
                msg_id = msg_proto.metadata.message_id
                all_object_contents = pull_objects(
                    object_ids=[
                        tree.object_id for tree in iterate_object_tree(msg_tree)
                    ],
                    pull_object_fn=make_pull_object_fn_protobuf(
                        pull_object_protobuf=self._stub.PullObject,
                        node=self.node,
                        run_id=run_id,
                    ),
                )

                # Confirm that the message has been received
                self._stub.ConfirmMessageReceived(
                    ConfirmMessageReceivedRequest(
                        node=self.node, run_id=run_id, message_object_id=msg_id
                    )
                )
                message = cast(
                    Message, inflate_object_from_contents(msg_id, all_object_contents)
                )
                message.metadata.__dict__["_message_id"] = msg_id
                inflated_msgs.append(message)

            return inflated_msgs

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:  # pylint: disable=E1101
                log(ERROR, ERROR_MESSAGE_PULL_MESSAGES_RESOURCE_EXHAUSTED)
                return []
            raise

    def send_and_receive(
        self,
        messages: Iterable[Message],
        *,
        timeout: Optional[float] = None,
    ) -> Iterable[Message]:
        """Push messages to specified node IDs and pull the reply messages.

        This method sends a list of messages to their destination node IDs and then
        waits for the replies. It continues to pull replies until either all replies are
        received or the specified timeout duration is exceeded.
        """
        # Push messages
        msg_ids = set(self.push_messages(messages))

        # Pull messages
        end_time = time.time() + (timeout if timeout is not None else 0.0)
        ret: list[Message] = []
        while timeout is None or time.time() < end_time:
            res_msgs = self.pull_messages(msg_ids)
            ret.extend(res_msgs)
            msg_ids.difference_update(
                {msg.metadata.reply_to_message_id for msg in res_msgs}
            )
            if len(msg_ids) == 0:
                break
            # Sleep
            time.sleep(3)
        return ret

    def close(self) -> None:
        """Disconnect from the SuperLink if connected."""
        # Check if `connect` was called before
        if not self._is_connected:
            return
        # Disconnect
        self._disconnect()
