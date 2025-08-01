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
"""Flower constants."""


from __future__ import annotations

TRANSPORT_TYPE_GRPC_BIDI = "grpc-bidi"
TRANSPORT_TYPE_GRPC_RERE = "grpc-rere"
TRANSPORT_TYPE_GRPC_ADAPTER = "grpc-adapter"
TRANSPORT_TYPE_REST = "rest"
TRANSPORT_TYPE_VCE = "vce"
TRANSPORT_TYPES = [
    TRANSPORT_TYPE_GRPC_BIDI,
    TRANSPORT_TYPE_GRPC_RERE,
    TRANSPORT_TYPE_REST,
    TRANSPORT_TYPE_VCE,
]

# Addresses
# Ports
CLIENTAPPIO_PORT = "9094"
SERVERAPPIO_PORT = "9091"
FLEETAPI_GRPC_RERE_PORT = "9092"
FLEETAPI_PORT = "9095"
EXEC_API_PORT = "9093"
SIMULATIONIO_PORT = "9096"
# Octets
SERVER_OCTET = "0.0.0.0"
CLIENT_OCTET = "127.0.0.1"
# SuperNode
CLIENTAPPIO_API_DEFAULT_SERVER_ADDRESS = f"{SERVER_OCTET}:{CLIENTAPPIO_PORT}"
CLIENTAPPIO_API_DEFAULT_CLIENT_ADDRESS = f"{CLIENT_OCTET}:{CLIENTAPPIO_PORT}"
# SuperLink
SERVERAPPIO_API_DEFAULT_SERVER_ADDRESS = f"{SERVER_OCTET}:{SERVERAPPIO_PORT}"
SERVERAPPIO_API_DEFAULT_CLIENT_ADDRESS = f"{CLIENT_OCTET}:{SERVERAPPIO_PORT}"
FLEET_API_GRPC_RERE_DEFAULT_ADDRESS = f"{SERVER_OCTET}:{FLEETAPI_GRPC_RERE_PORT}"
FLEET_API_GRPC_BIDI_DEFAULT_ADDRESS = (
    "[::]:8080"  # IPv6 to keep start_server compatible
)
FLEET_API_REST_DEFAULT_ADDRESS = f"{SERVER_OCTET}:{FLEETAPI_PORT}"
EXEC_API_DEFAULT_SERVER_ADDRESS = f"{SERVER_OCTET}:{EXEC_API_PORT}"
SIMULATIONIO_API_DEFAULT_SERVER_ADDRESS = f"{SERVER_OCTET}:{SIMULATIONIO_PORT}"
SIMULATIONIO_API_DEFAULT_CLIENT_ADDRESS = f"{CLIENT_OCTET}:{SIMULATIONIO_PORT}"

# Constants for heartbeat
HEARTBEAT_DEFAULT_INTERVAL = 30
HEARTBEAT_CALL_TIMEOUT = 5
HEARTBEAT_BASE_MULTIPLIER = 0.8
HEARTBEAT_RANDOM_RANGE = (-0.1, 0.1)
HEARTBEAT_MAX_INTERVAL = 1e300
HEARTBEAT_PATIENCE = 2
RUN_FAILURE_DETAILS_NO_HEARTBEAT = "No heartbeat received from the run."

# IDs
RUN_ID_NUM_BYTES = 8
NODE_ID_NUM_BYTES = 8

# Constants for FAB
APP_DIR = "apps"
FAB_ALLOWED_EXTENSIONS = {".py", ".toml", ".md"}
FAB_CONFIG_FILE = "pyproject.toml"
FAB_DATE = (2024, 10, 1, 0, 0, 0)
FAB_HASH_TRUNCATION = 8
FAB_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
FLWR_DIR = ".flwr"  # The default Flower directory: ~/.flwr/
FLWR_HOME = "FLWR_HOME"  # If set, override the default Flower directory

# Constant for SuperLink
SUPERLINK_NODE_ID = 1

# Constants entries in Node config for Simulation
PARTITION_ID_KEY = "partition-id"
NUM_PARTITIONS_KEY = "num-partitions"

# Constants for keys in `metadata` of `MessageContainer` in `grpc-adapter`
GRPC_ADAPTER_METADATA_FLOWER_PACKAGE_NAME_KEY = "flower-package-name"
GRPC_ADAPTER_METADATA_FLOWER_PACKAGE_VERSION_KEY = "flower-package-version"
GRPC_ADAPTER_METADATA_FLOWER_VERSION_KEY = "flower-version"  # Deprecated
GRPC_ADAPTER_METADATA_SHOULD_EXIT_KEY = "should-exit"
GRPC_ADAPTER_METADATA_MESSAGE_MODULE_KEY = "grpc-message-module"
GRPC_ADAPTER_METADATA_MESSAGE_QUALNAME_KEY = "grpc-message-qualname"

# Message TTL
MESSAGE_TTL_TOLERANCE = 1e-1

# Isolation modes
ISOLATION_MODE_SUBPROCESS = "subprocess"
ISOLATION_MODE_PROCESS = "process"

# Log streaming configurations
CONN_REFRESH_PERIOD = 60  # Stream connection refresh period
CONN_RECONNECT_INTERVAL = 0.5  # Reconnect interval between two stream connections
LOG_STREAM_INTERVAL = 0.5  # Log stream interval for `ExecServicer.StreamLogs`
LOG_UPLOAD_INTERVAL = 0.2  # Minimum interval between two log uploads

# Retry configurations
MAX_RETRY_DELAY = 20  # Maximum delay duration between two consecutive retries.

# Constants for user authentication
CREDENTIALS_DIR = ".credentials"
AUTH_TYPE_JSON_KEY = "auth-type"  # For key name in JSON file
AUTH_TYPE_YAML_KEY = "auth_type"  # For key name in YAML file
ACCESS_TOKEN_KEY = "flwr-oidc-access-token"
REFRESH_TOKEN_KEY = "flwr-oidc-refresh-token"

# Constants for user authorization
AUTHZ_TYPE_YAML_KEY = "authz_type"  # For key name in YAML file

# Constants for node authentication
PUBLIC_KEY_HEADER = "flwr-public-key-bin"  # Must end with "-bin" for binary data
SIGNATURE_HEADER = "flwr-signature-bin"  # Must end with "-bin" for binary data
TIMESTAMP_HEADER = "flwr-timestamp"
TIMESTAMP_TOLERANCE = 10  # General tolerance for timestamp verification
SYSTEM_TIME_TOLERANCE = 5  # Allowance for system time drift

# Constants for grpc retry
GRPC_RETRY_MAX_DELAY = 20  # Maximum delay duration between two consecutive retries.

# Constants for ArrayRecord
GC_THRESHOLD = 200_000_000  # 200 MB

# Constants for Inflatable
HEAD_BODY_DIVIDER = b"\x00"
HEAD_VALUE_DIVIDER = " "
MAX_ARRAY_CHUNK_SIZE = 20_971_520  # 20 MB

# Constants for serialization
INT64_MAX_VALUE = 9223372036854775807  # (1 << 63) - 1

# Constants for `flwr-serverapp` and `flwr-clientapp` CLI commands
FLWR_APP_TOKEN_LENGTH = 128  # Length of the token used

# Constants for object pushing and pulling
MAX_CONCURRENT_PUSHES = 8  # Default maximum number of concurrent pushes
MAX_CONCURRENT_PULLS = 8  # Default maximum number of concurrent pulls
PULL_MAX_TIME = 7200  # Default maximum time to wait for pulling objects
PULL_MAX_TRIES_PER_OBJECT = 500  # Default maximum number of tries to pull an object
PULL_INITIAL_BACKOFF = 1  # Initial backoff time for pulling objects
PULL_BACKOFF_CAP = 10  # Maximum backoff time for pulling objects


# ExecServicer constants
RUN_ID_NOT_FOUND_MESSAGE = "Run ID not found"


class MessageType:
    """Message type."""

    TRAIN = "train"
    EVALUATE = "evaluate"
    QUERY = "query"
    SYSTEM = "system"

    def __new__(cls) -> MessageType:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class MessageTypeLegacy:
    """Legacy message type."""

    GET_PROPERTIES = "get_properties"
    GET_PARAMETERS = "get_parameters"

    def __new__(cls) -> MessageTypeLegacy:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class SType:
    """Serialisation type."""

    NUMPY = "numpy.ndarray"

    def __new__(cls) -> SType:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class ErrorCode:
    """Error codes for Message's Error."""

    UNKNOWN = 0
    LOAD_CLIENT_APP_EXCEPTION = 1
    CLIENT_APP_RAISED_EXCEPTION = 2
    MESSAGE_UNAVAILABLE = 3
    REPLY_MESSAGE_UNAVAILABLE = 4
    NODE_UNAVAILABLE = 5

    def __new__(cls) -> ErrorCode:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class Status:
    """Run status."""

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    FINISHED = "finished"

    def __new__(cls) -> Status:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class SubStatus:
    """Run sub-status."""

    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

    def __new__(cls) -> SubStatus:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class CliOutputFormat:
    """Define output format for `flwr` CLI commands."""

    DEFAULT = "default"
    JSON = "json"

    def __new__(cls) -> CliOutputFormat:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class AuthType:
    """User authentication types."""

    OIDC = "oidc"

    def __new__(cls) -> AuthType:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")


class EventLogWriterType:
    """Event log writer types."""

    STDOUT = "stdout"

    def __new__(cls) -> EventLogWriterType:
        """Prevent instantiation."""
        raise TypeError(f"{cls.__name__} cannot be instantiated.")
