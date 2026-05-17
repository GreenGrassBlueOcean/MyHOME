"""MyHOME OpenWebNet Gateway — MCP Server.

A Model Context Protocol server that provides direct, real-time access to a
BTicino/Legrand MyHOME gateway over the OpenWebNet protocol.  Designed for
live debugging: monitor the SCS bus, send raw OWN frames, query device state,
and parse protocol messages — all from your AI coding assistant.

Transport: stdio (JSON-RPC over stdin/stdout).
"""

import asyncio
import json
import logging
import os
import sys

# ── Logging to stderr (stdout is reserved for JSON-RPC) ────────────────────
LOG_FILE = os.path.join(os.path.dirname(__file__), "mcp_server.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("myhome_mcp")

# Suppress noisy asyncio logs
logging.getLogger("asyncio").setLevel(logging.WARNING)

from own_client import GatewayClient  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
#  OpenWebNet WHO Reference Table
# ══════════════════════════════════════════════════════════════════════════════
WHO_TABLE = {
    0: "Scenarios",
    1: "Lighting",
    2: "Automation (Covers/Shutters)",
    3: "Loads/Power Management",
    4: "Heating/Climate (Thermo-regulation)",
    5: "Alarm/Intrusion",
    6: "VDES (Video Door Entry)",
    7: "Video Intercom",
    9: "Auxiliary",
    13: "Gateway Management",
    14: "Light+Shutter Actuators",
    15: "CEN (Scenario Pushbuttons)",
    16: "Sound System / Audio",
    17: "Scene Management",
    18: "Energy Management",
    22: "Sound Diffusion (extended)",
    24: "Lighting Management",
    25: "CEN+ / Dry Contacts",
    1001: "Diagnostic",
    1004: "Heating Diagnostic",
    1013: "Gateway Diagnostic",
}


# ══════════════════════════════════════════════════════════════════════════════
#  MCP Server Implementation
# ══════════════════════════════════════════════════════════════════════════════

class MyHomeMCPServer:
    """JSON-RPC / MCP server speaking stdio transport."""

    def __init__(self):
        self._client: GatewayClient | None = None

    # ── Tool definitions ────────────────────────────────────────────────

    def _tool_definitions(self) -> list:
        return [
            {
                "name": "connect_gateway",
                "description": (
                    "Connect to the MyHOME OpenWebNet gateway. "
                    "Establishes both an EVENT session (bus monitor) and a "
                    "COMMAND session (send frames). Must be called before any "
                    "other tool."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "IP address of the MyHOME gateway (e.g. '192.168.1.35').",
                        },
                        "port": {
                            "type": "integer",
                            "description": "TCP port (default 20000).",
                            "default": 20000,
                        },
                        "password": {
                            "type": "string",
                            "description": "OpenWebNet numeric password (default '12345').",
                            "default": "12345",
                        },
                    },
                    "required": ["host"],
                },
            },
            {
                "name": "disconnect_gateway",
                "description": "Disconnect from the gateway and close all sessions.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "send_raw_frame",
                "description": (
                    "Send a raw OpenWebNet frame to the gateway. "
                    "Example frames:\n"
                    "  *1*1*23##      → Turn on light at address 23\n"
                    "  *1*0*23##      → Turn off light at address 23\n"
                    "  *#1*23##       → Request status of light 23\n"
                    "  *#1*0##        → Request status of ALL lights\n"
                    "  *2*1*45##      → Open cover at address 45\n"
                    "  *#4*1*0##      → Request temperature for zone 1\n"
                    "  *16*3*11##     → Turn on audio zone 11\n"
                    "  *#16*11*#1##   → Request volume of audio zone 11\n"
                    "The frame is automatically ## terminated if needed."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "frame": {
                            "type": "string",
                            "description": "Raw OWN frame string (e.g. '*1*1*23##').",
                        },
                        "wait_responses": {
                            "type": "number",
                            "description": "Seconds to wait and capture bus responses (default 0.5).",
                            "default": 0.5
                        }
                    },
                    "required": ["frame"],
                },
            },
            {
                "name": "get_bus_messages",
                "description": (
                    "Retrieve recent messages from the OpenWebNet bus. "
                    "Returns a list of messages with timestamps, direction "
                    "(RX=received, TX=sent), raw frame, and parsed details."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "last_n": {
                            "type": "integer",
                            "description": "Number of most recent messages to return (default 50, max 500).",
                            "default": 50,
                        },
                        "direction": {
                            "type": "string",
                            "description": "Filter: 'RX' for received only, 'TX' for sent only, omit for both.",
                            "enum": ["RX", "TX"],
                        },
                        "who": {
                            "type": "integer",
                            "description": "Filter by WHO field (1=Lighting, 2=Automation, 4=Heating, 16=Audio, etc.).",
                        },
                        "where": {
                            "type": "string",
                            "description": "Filter by WHERE field (device/zone address).",
                        },
                    },
                },
            },
            {
                "name": "parse_own_frame",
                "description": (
                    "Parse and explain a raw OpenWebNet frame without sending it. "
                    "Useful for understanding what a message means. Accepts any "
                    "valid OWN frame string."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "frame": {
                            "type": "string",
                            "description": "Raw OWN frame string to parse (e.g. '*1*1*23##').",
                        },
                    },
                    "required": ["frame"],
                },
            },
            {
                "name": "get_connection_status",
                "description": (
                    "Get the current connection status, traffic statistics, "
                    "and message buffer size."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "scan_bus",
                "description": (
                    "Send status requests for all major OpenWebNet subsystems "
                    "(lighting, automation, heating, audio) to discover devices "
                    "on the bus. Results appear in bus messages after a short delay."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "subsystems": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "List of subsystems to scan. Options: "
                                "'lighting', 'automation', 'heating', 'audio', "
                                "'energy', 'gateway'. Default: all."
                            ),
                        },
                    },
                },
            },
            {
                "name": "get_who_reference",
                "description": (
                    "Return the OpenWebNet WHO field reference table mapping "
                    "WHO numbers to subsystem names (1=Lighting, 2=Automation, "
                    "4=Heating, etc.)."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_own_cheatsheet",
                "description": (
                    "Return a comprehensive cheatsheet of common OpenWebNet "
                    "frame patterns with examples for lighting, automation, "
                    "heating, audio, and gateway management."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    # ── Tool dispatch ───────────────────────────────────────────────────

    async def _handle_tool(self, name: str, arguments: dict) -> list:
        """Dispatch a tool call and return MCP content blocks."""
        try:
            if name == "connect_gateway":
                return await self._tool_connect(arguments)
            elif name == "disconnect_gateway":
                return await self._tool_disconnect()
            elif name == "send_raw_frame":
                return await self._tool_send_raw(arguments)
            elif name == "get_bus_messages":
                return await self._tool_get_messages(arguments)
            elif name == "parse_own_frame":
                return self._tool_parse_frame(arguments)
            elif name == "get_connection_status":
                return self._tool_connection_status()
            elif name == "scan_bus":
                return await self._tool_scan_bus(arguments)
            elif name == "get_who_reference":
                return self._tool_who_reference()
            elif name == "get_own_cheatsheet":
                return self._tool_cheatsheet()
            else:
                return [{"type": "text", "text": f"Unknown tool: {name}"}]
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return [{"type": "text", "text": f"Error: {exc}"}]

    # ── Tool implementations ────────────────────────────────────────────

    async def _tool_connect(self, args: dict) -> list:
        host = args["host"]
        port = args.get("port", 20000)
        password = args.get("password", "12345")

        if self._client and self._client.is_connected:
            await self._client.disconnect()

        self._client = GatewayClient(host=host, port=port, password=password)
        result = await self._client.connect()
        return [{"type": "text", "text": json.dumps(result, indent=2)}]

    async def _tool_disconnect(self) -> list:
        if not self._client:
            return [{"type": "text", "text": "Not connected."}]
        result = await self._client.disconnect()
        return [{"type": "text", "text": json.dumps(result, indent=2)}]

    async def _tool_send_raw(self, args: dict) -> list:
        if not self._client or not self._client.is_connected:
            return [{"type": "text", "text": "Error: Not connected. Call connect_gateway first."}]

        frame = args["frame"]
        wait_responses = args.get("wait_responses", 0.5)
        
        start_idx = len(self._client._message_log)
        result = await self._client.send_raw(frame)
        
        # Wait to capture hardware ACK/NACK and status broadcasts
        if result.get("status") == "sent" and wait_responses > 0:
            await asyncio.sleep(wait_responses)
            responses = list(self._client._message_log)[start_idx:]
            if responses:
                result["bus_responses"] = [
                    f"[{m['direction']}] {m['raw']} -> {m.get('parsed', {}).get('type')}" 
                    for m in responses
                ]

        return [{"type": "text", "text": json.dumps(result, indent=2)}]

    async def _tool_get_messages(self, args: dict) -> list:
        if not self._client:
            return [{"type": "text", "text": "Error: Not connected."}]

        last_n = min(args.get("last_n", 50), 500)
        direction = args.get("direction")
        who = args.get("who")
        where = args.get("where")

        messages = self._client.get_message_log(
            last_n=last_n,
            direction=direction,
            who_filter=who,
            where_filter=where,
        )

        if not messages:
            return [{"type": "text", "text": "No messages matching filters."}]

        # Format as a compact, readable table
        lines = [f"{'Time':>12s}  {'Dir':>3s}  {'Type':<25s}  {'Raw':<30s}  Description"]
        lines.append("─" * 120)
        for m in messages:
            ts = m["ts"][11:23]  # HH:MM:SS.mmm
            direction_str = m["direction"]
            parsed = m.get("parsed", {})
            msg_type = parsed.get("type", "?")
            raw = m["raw"][:30]
            desc = parsed.get("human_readable", parsed.get("value", ""))
            if desc and len(desc) > 60:
                desc = desc[:57] + "..."
            lines.append(f"{ts:>12s}  {direction_str:>3s}  {msg_type:<25s}  {raw:<30s}  {desc}")

        return [{"type": "text", "text": "\n".join(lines)}]

    def _tool_parse_frame(self, args: dict) -> list:
        frame = args["frame"]
        if self._client:
            result = self._client.parse_frame(frame)
        else:
            # Can still parse without a connection
            from own_client import GatewayClient
            temp = GatewayClient.__new__(GatewayClient)
            result = temp.parse_frame(frame)

        return [{"type": "text", "text": json.dumps(result, indent=2)}]

    def _tool_connection_status(self) -> list:
        if not self._client:
            return [{"type": "text", "text": json.dumps({"status": "not_initialized"}, indent=2)}]
        return [{"type": "text", "text": json.dumps(self._client.get_stats(), indent=2)}]

    async def _tool_scan_bus(self, args: dict) -> list:
        if not self._client or not self._client.is_connected:
            return [{"type": "text", "text": "Error: Not connected."}]

        subsystems = args.get("subsystems")
        if not subsystems:
            subsystems = ["lighting", "automation", "heating", "audio", "gateway"]

        scan_frames = {
            "lighting": "*#1*0##",
            "automation": "*#2*0##",
            # "heating": "*#4*0##",   # UNSUPPORTED: Causes NACK
            # "audio": "*#16*0##",    # UNSUPPORTED: Causes NACK and socket drop
            "energy": "*#18*0##",
            "gateway": "*#13**15##",  # device type
        }

        sent = []
        for sub in subsystems:
            sub_lower = sub.lower()
            if sub_lower in scan_frames:
                result = await self._client.send_raw(scan_frames[sub_lower])
                sent.append({"subsystem": sub, **result})
            else:
                sent.append({"subsystem": sub, "status": "unknown_subsystem"})

        summary = f"Sent {len([s for s in sent if s.get('status') == 'sent'])} scan requests.\n"
        summary += "Device responses will arrive on the event bus within seconds.\n"
        summary += "Use get_bus_messages to see the responses.\n\n"
        summary += json.dumps(sent, indent=2)

        return [{"type": "text", "text": summary}]

    def _tool_who_reference(self) -> list:
        lines = ["OpenWebNet WHO Reference Table", "=" * 50]
        for who_id, name in sorted(WHO_TABLE.items()):
            lines.append(f"  WHO {who_id:>5d}  →  {name}")
        return [{"type": "text", "text": "\n".join(lines)}]

    def _tool_cheatsheet(self) -> list:
        cheatsheet = """
╔══════════════════════════════════════════════════════════════════════════╗
║                  OpenWebNet Frame Cheatsheet                            ║
╚══════════════════════════════════════════════════════════════════════════╝

FRAME ANATOMY
  Command:          *WHO*WHAT*WHERE##
  Status request:   *#WHO*WHERE##
  Dimension req:    *#WHO*WHERE*DIMENSION##
  Dimension write:  *#WHO*WHERE*#DIMENSION*VAL1*VALn##

═══════════════════ LIGHTING (WHO=1) ═══════════════════════════════════════
  *1*1*23##           Turn ON light at address 23
  *1*0*23##           Turn OFF light at address 23
  *1*1*0##            Turn ON all lights (general command)
  *#1*23##            Request status of light 23
  *#1*0##             Request status of ALL lights
  *#1*23*1##          Request brightness of light 23
  *#1*23*#1*150*0##   Set brightness to 50% (100+50=150), speed 0
  *1*2*23##           Set light to dimmer level 2 (20%)
  *1*20*23##          Blink light 23 every 0.5s

═══════════════════ AUTOMATION / COVERS (WHO=2) ═════════════════════════════
  *2*1*45##           Open/raise shutter at address 45
  *2*2*45##           Close/lower shutter at address 45
  *2*0*45##           Stop shutter at address 45
  *#2*45##            Request status of shutter 45
  *#2*0##             Request status of ALL shutters
  *#2*45*#11#001*30## Set shutter position to 30%

═══════════════════ HEATING / CLIMATE (WHO=4) ═══════════════════════════════
  *#4*1##             Request status of heating zone 1
  *#4*0##             Request status of ALL heating zones
  *#4*1*0##           Request temperature of zone 1
  *#4*1*14##          Request target temperature of zone 1
  *4*303*#1##         Turn OFF zone 1
  *4*311*#1##         Set zone 1 to AUTO mode
  *#4*#1*#14*0220*1## Set zone 1 to 22.0°C in HEAT mode

═══════════════════ SOUND SYSTEM / AUDIO (WHO=16) ═══════════════════════════
  *16*3*11##          Turn ON audio zone 11
  *16*13*11##         Turn OFF audio zone 11
  *16*1001*11##       Volume UP for zone 11
  *16*1000*11##       Volume DOWN for zone 11
  *#16*11*#1*15##     Set volume to 15 for zone 11
  *#16*11##           Request status of audio zone 11
  *#16*11*1##         Request volume of audio zone 11
  *16*3*111##         Select source 1 for zone 11 (addr=111)
  *16*3*121##         Select source 2 for zone 11 (addr=121)

═══════════════════ ENERGY (WHO=18) ═════════════════════════════════════════
  *#18*51*113##       Request instant power draw from sensor 51
  *#18*51*51##        Request total consumption from sensor 51

═══════════════════ GATEWAY (WHO=13) ════════════════════════════════════════
  *#13**0##           Request gateway time
  *#13**1##           Request gateway date
  *#13**10##          Request gateway IP address
  *#13**12##          Request gateway MAC address
  *#13**15##          Request gateway device type
  *#13**16##          Request gateway firmware version
  *#13**19##          Request gateway uptime

═══════════════════ AUXILIARY (WHO=9) ═══════════════════════════════════════
  *9*1*1##            Auxiliary channel 1 ON
  *9*0*1##            Auxiliary channel 1 OFF

═══════════════════ DRY CONTACTS (WHO=25) ═══════════════════════════════════
  *#25*31##           Request dry contact 31 status

═══════════════════ CEN+ PUSHBUTTONS (WHO=25, WHERE starts with 2) ═════════
  Event where=2xx: pushbutton events from CEN+ devices

═══════════════════ WHERE ADDRESS FORMAT ════════════════════════════════════
  Simple:    APL (A=area 0-9, PL=point 01-15)  e.g. 23 = area 2, point 3
  General:   0                                   e.g. *1*1*0## = all lights
  Area:      A (single digit)                    e.g. *1*1*3## = area 3
  Group:     #G                                  e.g. *1*1*#1## = group 1
  Interface: WHERE#4#BUS                         e.g. 23#4#01 = address 23, bus interface 01
"""
        return [{"type": "text", "text": cheatsheet.strip()}]

    # ── MCP JSON-RPC Protocol ───────────────────────────────────────────

    async def handle_request(self, request: dict) -> dict:
        """Handle a single JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        logger.debug("← %s (id=%s)", method, req_id)

        if method == "initialize":
            return self._response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "myhome-gateway",
                    "version": "1.0.0",
                },
            })

        elif method == "notifications/initialized":
            return None  # notification, no response

        elif method == "tools/list":
            return self._response(req_id, {"tools": self._tool_definitions()})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            content = await self._handle_tool(tool_name, tool_args)
            return self._response(req_id, {"content": content})

        elif method == "ping":
            return self._response(req_id, {})

        elif method == "resources/list":
            return self._response(req_id, {"resources": []})

        elif method == "prompts/list":
            return self._response(req_id, {"prompts": []})

        else:
            logger.warning("Unknown method: %s", method)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def _response(self, req_id, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    # ── Main loop (stdio transport) ─────────────────────────────────────

    async def run(self):
        """Run the MCP server on stdin/stdout."""
        logger.info("MyHOME MCP Server starting (stdio transport)...")

        import threading
        loop = asyncio.get_event_loop()
        input_queue = asyncio.Queue()

        def stdin_reader():
            """Read from stdin in a background thread to avoid Windows async pipe issues."""
            while True:
                try:
                    header_line = sys.stdin.buffer.readline()
                    if not header_line:
                        loop.call_soon_threadsafe(input_queue.put_nowait, None)
                        break

                    # Strip the UTF-8 BOM if the MCP client injected it
                    if header_line.startswith(b'\xef\xbb\xbf'):
                        header_line = header_line[3:]

                    if header_line.startswith(b"Content-Length:"):
                        # Parse Content-Length
                        content_length = int(header_line.split(b":")[1].strip())
                        
                        # Consume ALL remaining headers until we hit the empty \r\n line
                        while True:
                            h_line = sys.stdin.buffer.readline()
                            if not h_line or h_line.strip() == b"":
                                break
                                
                        # Read the exact body length
                        body = sys.stdin.buffer.read(content_length)
                        loop.call_soon_threadsafe(input_queue.put_nowait, body)
                    else:
                        # Might be newline-delimited JSON or empty line
                        if header_line.strip():
                            loop.call_soon_threadsafe(input_queue.put_nowait, header_line)
                except Exception as e:
                    logger.exception("Stdin read error: %s", e)
                    loop.call_soon_threadsafe(input_queue.put_nowait, None)
                    break

        reader_thread = threading.Thread(target=stdin_reader, daemon=True)
        reader_thread.start()

        while True:
            try:
                body_bytes = await input_queue.get()
                if body_bytes is None:
                    logger.info("stdin closed, shutting down.")
                    break

                request = json.loads(body_bytes.decode("utf-8"))
                response = await self.handle_request(request)

                if response is not None:
                    response_bytes = json.dumps(response).encode("utf-8")
                    header_bytes = f"Content-Length: {len(response_bytes)}\r\n\r\n".encode("utf-8")
                    sys.stdout.buffer.write(header_bytes + response_bytes)
                    sys.stdout.buffer.flush()
                    logger.debug("→ responded to id=%s", response.get("id"))

            except json.JSONDecodeError as exc:
                logger.error("JSON parse error: %s", exc)
            except Exception as exc:
                logger.exception("Unexpected error in main loop: %s", exc)
                break

        # Cleanup
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        logger.info("MyHOME MCP Server stopped.")


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        # Prevents "WinError 6" when pipes are closed
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    server = MyHomeMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
