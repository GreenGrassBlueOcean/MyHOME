# MyHOME OpenWebNet MCP Server

A Model Context Protocol (MCP) server designed to provide your AI Coding Assistant direct, real-time access to a BTicino/Legrand MyHOME gateway over the OpenWebNet protocol.

This is a standalone diagnostic and debugging tool. It directly reuses the low-level `ownd` socket and message parsing layer from the `myhome` custom component, but requires **zero dependencies** on Home Assistant.

## Features

1.  **Live Bus Monitoring:** Maintains a background EVENT session to listen to all traffic on the SCS bus in real time.
2.  **Command Execution:** Maintains an on-demand COMMAND session to send raw OWN frames.
3.  **Automatic Parsing:** Uses the `OWNMessage` regex engine to automatically decode raw frames (e.g., `*1*1*23##` → `OWNLightingEvent: Light 23 is switched on.`).
4.  **Device Discovery:** Built-in `scan_bus` tool to quickly probe lighting, automation, heating, and audio subsystems.
5.  **Cheatsheets:** Built-in tools for looking up `WHO` categories and common frame syntaxes.

## Setup

The MCP server uses a standalone Python 3.12 virtual environment to avoid interfering with Home Assistant or the system Python.

Dependencies are installed in `mcp_server/.venv`.

## Connecting to Gemini / Cursor

The server configuration is located in `mcp_config.json`:

```json
{
  "mcpServers": {
    "myhome-gateway": {
      "command": "c:\\Users\\laurensvdb\\Documents\\GitHub\\MyHOME\\mcp_server\\.venv\\Scripts\\python.exe",
      "args": [
        "c:\\Users\\laurensvdb\\Documents\\GitHub\\MyHOME\\mcp_server\\server.py"
      ],
      "timeout": 30000
    }
  }
}
```

Add this snippet to your IDE's MCP configuration (e.g., `%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\cline_mcp_settings.json` or equivalent Gemini settings).

## Available Tools

*   `connect_gateway(host, port=20000, password=12345)`: Establish the debug connection. MUST be called first.
*   `disconnect_gateway()`: Safely close sockets.
*   `get_bus_messages(last_n=50, direction, who, where)`: Fetch the recent traffic ring-buffer.
*   `send_raw_frame(frame)`: Inject a frame (e.g., `*1*1*23##`) and capture the result.
*   `scan_bus(subsystems)`: Send broadcast status requests (`*#1*0##`) to map out available devices.
*   `parse_own_frame(frame)`: Dry-run parser to understand a string without sending it.
*   `get_own_cheatsheet()`: Get a handy reference for OpenWebNet commands.
*   `get_who_reference()`: Map `WHO` numbers to subsystems.

## Debugging

The MCP server writes a headless log to:
`c:\Users\laurensvdb\Documents\GitHub\MyHOME\mcp_server\mcp_server.log`

Check this log if you encounter socket timeouts or authentication (SHA/HMAC) issues with the gateway.
