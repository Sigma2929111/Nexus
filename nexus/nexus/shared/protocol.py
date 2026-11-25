"""Protocol constants shared across the wire."""
from __future__ import annotations

SERVICE_TYPE = "_nexus._tcp.local."
DEFAULT_PORT = 8787

# WebSocket message types (MASTER <-> BLOCK agent)
MSG_HELLO = "hello"
MSG_HELLO_OK = "hello_ok"
MSG_HEARTBEAT = "heartbeat"
MSG_HEARTBEAT_ACK = "heartbeat_ack"
MSG_COMMAND = "command"
MSG_COMMAND_RESULT = "command_result"
MSG_LOG = "log"
MSG_ERROR = "error"

# Agent command actions
CMD_APP_CREATE = "app.create"
CMD_APP_START = "app.start"
CMD_APP_STOP = "app.stop"
CMD_APP_RESTART = "app.restart"
CMD_APP_DELETE = "app.delete"
CMD_APP_LOGS = "app.logs"
CMD_APP_EXEC = "app.exec"
CMD_FS_LIST = "fs.list"
CMD_FS_READ = "fs.read"
CMD_FS_WRITE = "fs.write"
CMD_FS_DELETE = "fs.delete"
CMD_FS_MKDIR = "fs.mkdir"
CMD_FS_RENAME = "fs.rename"
CMD_AGENT_RESTART = "agent.restart"
CMD_CLUSTER_EXEC = "cluster.exec"

# REST endpoints
API_PREFIX = "/api/v1"
