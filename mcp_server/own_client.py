"""Standalone OpenWebNet client for the MCP server.

Re-uses the ownd connection and message parsing layer from the custom_component
but operates completely standalone — no Home Assistant dependency required.
"""

import asyncio
import logging
import sys
import os
from collections import deque
from datetime import datetime, timezone
from typing import Optional

# ── Make the ownd library importable ────────────────────────────────────────
# We add the custom_components/myhome directory to sys.path so we can import
# the ownd package directly, without needing Home Assistant installed.
_MYHOME_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "custom_components",
    "myhome",
)
if _MYHOME_DIR not in sys.path:
    sys.path.insert(0, _MYHOME_DIR)

from ownd.connection import OWNGateway, OWNSession, OWNEventSession, OWNCommandSession
from ownd.message import OWNMessage, OWNSignaling, OWNCommand


logger = logging.getLogger("myhome_mcp.own_client")


class GatewayClient:
    """Lightweight, standalone OpenWebNet gateway client for debugging.

    Maintains:
    - A persistent EVENT session (bus monitor)
    - An on-demand COMMAND session (send raw OWN frames)
    - A ring-buffer of recent messages for inspection
    """

    MAX_LOG_SIZE = 2000  # keep last N messages in memory

    def __init__(
        self,
        host: str,
        port: int = 20000,
        password: str = "12345",
    ):
        self.host = host
        self.port = port
        self.password = password

        self._gateway: Optional[OWNGateway] = None
        self._event_session: Optional[OWNEventSession] = None
        self._command_session: Optional[OWNCommandSession] = None

        # Ring buffer: each entry is a dict with ts, direction, raw, parsed
        self._message_log: deque = deque(maxlen=self.MAX_LOG_SIZE)
        self._listener_task: Optional[asyncio.Task] = None
        self._connected = False
        self._stats = {
            "messages_received": 0,
            "commands_sent": 0,
            "errors": 0,
            "connect_time": None,
        }

    # ── Connection lifecycle ────────────────────────────────────────────

    async def connect(self) -> dict:
        """Establish both event and command sessions."""
        discovery_info = {
            "address": self.host,
            "port": self.port,
            "password": self.password,
            "ssdp_location": None,
            "ssdp_st": None,
            "deviceType": None,
            "friendlyName": "MCP Debug Client",
            "manufacturer": "BTicino S.p.A.",
            "manufacturerURL": None,
            "modelName": "MCP Debug",
            "modelNumber": None,
            "serialNumber": None,
            "UDN": None,
        }
        self._gateway = OWNGateway(discovery_info)

        # Open event session
        self._event_session = OWNEventSession(gateway=self._gateway, logger=logger)
        result = await self._event_session.connect()

        if result and result.get("Success"):
            self._connected = True
            self._stats["connect_time"] = datetime.now(timezone.utc).isoformat()

            # Open command session
            self._command_session = OWNCommandSession(
                gateway=self._gateway, logger=logger
            )
            await self._command_session.connect()

            # Start background listener
            self._listener_task = asyncio.create_task(self._listen_loop())

            return {
                "status": "connected",
                "host": self.host,
                "port": self.port,
                "time": self._stats["connect_time"],
            }
        else:
            msg = result.get("Message", "unknown") if result else "no response"
            return {"status": "failed", "error": msg}

    async def disconnect(self) -> dict:
        """Gracefully tear down all sessions."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._event_session:
            try:
                await self._event_session.close()
            except Exception:
                pass

        if self._command_session:
            try:
                await self._command_session.close()
            except Exception:
                pass

        self._connected = False
        return {"status": "disconnected"}

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Bus listener ────────────────────────────────────────────────────

    async def _listen_loop(self):
        """Continuously read events from the gateway bus."""
        while self._connected:
            try:
                message = await self._event_session.get_next()
                if message is None:
                    continue

                entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "direction": "RX",
                    "raw": str(message),
                }

                if isinstance(message, OWNMessage):
                    entry["parsed"] = {
                        "type": type(message).__name__,
                        "who": message.who if hasattr(message, "who") else None,
                        "where": message.where if hasattr(message, "where") else None,
                        "family": message._family if hasattr(message, "_family") else None,
                        "human_readable": (
                            message.human_readable_log
                            if hasattr(message, "human_readable_log")
                            else None
                        ),
                    }
                    # Add event_content for richer introspection
                    if hasattr(message, "event_content"):
                        entry["event_content"] = message.event_content
                else:
                    entry["parsed"] = {"type": "raw_string", "value": str(message)}

                self._message_log.append(entry)
                self._stats["messages_received"] += 1

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._stats["errors"] += 1
                logger.exception("Listener error: %s", exc)
                await asyncio.sleep(1)

    # ── Command interface ───────────────────────────────────────────────

    async def send_raw(self, raw_frame: str) -> dict:
        """Send a raw OpenWebNet frame to the gateway.

        Args:
            raw_frame: Complete OWN frame string, e.g. '*1*1*23##'

        Returns:
            dict with status and the parsed message info.
        """
        if not self._connected or not self._command_session:
            return {"status": "error", "error": "Not connected"}

        # Normalise: ensure it ends with ##
        if not raw_frame.endswith("##"):
            raw_frame = raw_frame.rstrip("#") + "##"

        # Parse to get an OWNCommand/OWNMessage object
        parsed = OWNCommand.parse(raw_frame)
        if parsed is None:
            # Fallback: try OWNMessage.parse for status requests
            parsed = OWNMessage.parse(raw_frame)

        # Log the outgoing frame
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "TX",
            "raw": raw_frame,
            "parsed": {
                "type": type(parsed).__name__ if parsed else "unparsed",
                "human_readable": (
                    parsed.human_readable_log
                    if parsed and hasattr(parsed, "human_readable_log")
                    else raw_frame
                ),
            },
        }
        self._message_log.append(entry)

        try:
            is_status = raw_frame.startswith("*#")
            await self._command_session.send(
                message=parsed if parsed else raw_frame,
                is_status_request=is_status,
            )
            self._stats["commands_sent"] += 1
            return {
                "status": "sent",
                "frame": raw_frame,
                "parsed_as": entry["parsed"]["type"],
                "description": entry["parsed"]["human_readable"],
            }
        except Exception as exc:
            self._stats["errors"] += 1
            return {"status": "error", "error": str(exc)}

    # ── Query interface ─────────────────────────────────────────────────

    def get_message_log(
        self,
        last_n: int = 50,
        direction: Optional[str] = None,
        who_filter: Optional[int] = None,
        where_filter: Optional[str] = None,
    ) -> list:
        """Return recent messages from the ring buffer.

        Args:
            last_n: Number of most recent messages to return.
            direction: Filter by 'RX' (received) or 'TX' (sent).
            who_filter: Filter by WHO field (1=lighting, 2=automation, etc.).
            where_filter: Filter by WHERE field.
        """
        result = list(self._message_log)

        if direction:
            result = [m for m in result if m["direction"] == direction.upper()]

        if who_filter is not None:
            def matches_who(m):
                parsed = m.get("parsed", {})
                if parsed.get("who") == who_filter:
                    return True
                # Fallback: if unparsed, check the raw frame string directly
                if parsed.get("type") in ("raw_string", "unparsed"):
                    raw = m.get("raw", "")
                    if raw.startswith(f"*{who_filter}*") or raw.startswith(f"*#{who_filter}*"):
                        return True
                return False
            result = [m for m in result if matches_who(m)]

        if where_filter is not None:
            result = [
                m
                for m in result
                if m.get("parsed", {}).get("where") == where_filter
            ]

        return result[-last_n:]

    def get_stats(self) -> dict:
        """Return connection and traffic statistics."""
        return {
            **self._stats,
            "is_connected": self._connected,
            "log_size": len(self._message_log),
            "host": self.host,
            "port": self.port,
        }

    def parse_frame(self, raw_frame: str) -> dict:
        """Parse a raw OWN frame string without sending it.

        Useful for understanding what a message means.
        """
        if not raw_frame.endswith("##"):
            raw_frame = raw_frame.rstrip("#") + "##"

        parsed = OWNMessage.parse(raw_frame)

        if parsed is None:
            return {"raw": raw_frame, "valid": False, "error": "Could not parse frame"}

        result = {
            "raw": raw_frame,
            "valid": True,
            "type": type(parsed).__name__,
        }

        if isinstance(parsed, OWNSignaling):
            result["category"] = "signaling"
            result["is_ack"] = parsed.is_ack()
            result["is_nack"] = parsed.is_nack()
        elif isinstance(parsed, OWNMessage):
            result["category"] = parsed._family if hasattr(parsed, "_family") else "unknown"
            result["who"] = parsed.who if hasattr(parsed, "who") else None
            result["where"] = parsed.where if hasattr(parsed, "where") else None
            if hasattr(parsed, "human_readable_log"):
                result["description"] = parsed.human_readable_log
            if hasattr(parsed, "event_content"):
                result["event_content"] = parsed.event_content

        return result
