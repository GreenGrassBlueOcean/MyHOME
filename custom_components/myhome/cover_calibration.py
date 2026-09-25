"""Support for MyHome cover travel-time calibration (myhome.calibrate_cover)."""
from __future__ import annotations

import asyncio
import collections
import time
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COVER_TRAVEL_TIMES,
    DOMAIN,
    LOGGER,
)
from .data import MyHOMERuntimeData

if TYPE_CHECKING:
    from .gateway import MyHOMEGatewayHandler

# Legacy module globals for backward compatibility and test fixture resets
_CALIBRATION_LOCKS: dict[str, asyncio.Lock] = {}
_CALIBRATION_ACTIVE: dict[str, Any] = {}
_CALIBRATION_QUEUED: dict[str, set[Any]] = {}
_LAST_CALIBRATION_TRACE: collections.deque[dict[str, Any]] = collections.deque(maxlen=1000)


def _gateway_key(gateway: Any) -> str:
    """Return a unique key for the gateway (MAC address or object id)."""
    return str(getattr(gateway, "mac", "") or id(gateway))


def _normalize_mac(mac: Any) -> str | None:
    """One spelling for a gateway MAC so frames and requests compare equal."""
    if mac is None or str(mac).strip() == "":
        return None
    return dr.format_mac(str(mac))


def _calibration_lock(gateway: Any) -> asyncio.Lock:
    """Return the per-gateway calibration lock, rebinding if event loop changed."""
    return get_calibration_hub(gateway).lock


def _record_calibration_frame(gateway: Any, direction: str, raw: str, **extra: Any) -> None:
    """Record a frame during active calibration to the trace buffer."""
    hub = get_calibration_hub(gateway)
    hub.record_frame(direction, raw, **extra)


def get_last_calibration_trace(gateway_mac: str | None = None) -> list[dict[str, Any]]:
    """Return in-memory trace frames captured during recent cover calibrations.

    The buffer is shared by every gateway; each frame carries the MAC of the
    gateway that recorded it. With ``gateway_mac`` only that gateway's frames
    are returned, so an export for one gateway never carries another's runs
    (``None`` is the only unfiltered read; a gateway without a MAC gets the
    frames recorded without one).
    """
    if gateway_mac is None:
        return list(_LAST_CALIBRATION_TRACE)
    wanted = _normalize_mac(gateway_mac)
    return [f for f in _LAST_CALIBRATION_TRACE if f.get("gateway_mac") == wanted]


async def async_stop_cover_calibration(hass: Any, gateway_mac: str | None = None) -> bool:
    """Stop active and queued cover calibrations on one or all gateways."""
    stopped_any = False
    wanted_mac = _normalize_mac(gateway_mac) if gateway_mac else None

    # Stop via registered hubs if hass config entries are available
    if hass is not None and hasattr(hass, "config_entries"):
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            hub = getattr(runtime, "calibration_hub", None)
            if isinstance(hub, CoverCalibrationHub):
                if wanted_mac and hub.mac != wanted_mac:
                    continue
                if await hub.async_stop():
                    stopped_any = True

    # Also handle standalone mock gateways / legacy module globals
    for gw_key, active_cover in list(_CALIBRATION_ACTIVE.items()):
        if wanted_mac:
            normalized_key = _normalize_mac(gw_key)
            if normalized_key != wanted_mac and not gw_key.startswith(str(gateway_mac)):
                continue
        # Cancel queued covers waiting for the lock
        queued_covers = list(_CALIBRATION_QUEUED.get(gw_key, set()))
        _CALIBRATION_QUEUED.setdefault(gw_key, set()).clear()
        for c in queued_covers:
            c._calibration_interrupted = "Calibration stopped by user"
            c._fire_calibration_event("failed", error="Calibration stopped by user")
            stopped_any = True

        # Stop currently running cover
        if active_cover is not None and getattr(active_cover, "_calibrating", False):
            active_cover._calibration_interrupted = "Calibration stopped by user"
            active_cover._motor_started.set()
            active_cover._stopped_event.set()
            try:
                await active_cover.async_stop_cover()
            except Exception as err:
                LOGGER.warning("Error stopping cover %s: %s", active_cover.entity_id, err)
            stopped_any = True
            _CALIBRATION_ACTIVE.pop(gw_key, None)

    return stopped_any


def _stored_calibration(config_entry: Any, device_id: str) -> dict[str, Any] | None:
    """Return the persisted calibration for a cover, if any."""
    options = getattr(config_entry, "options", None) or {}
    stored = options.get(CONF_COVER_TRAVEL_TIMES) or {}
    entry = stored.get(str(device_id))
    return dict(entry) if isinstance(entry, dict) else None


class CalibrationInterrupted(HomeAssistantError):
    """A wall-switch or scenario command interfered with a calibration run."""

    def __init__(self, name: str, cause: str) -> None:
        super().__init__(
            f"{name}: {cause}",
            translation_domain=DOMAIN,
            translation_key="calibration_interrupted",
            translation_placeholders={"name": name, "cause": cause},
        )


class CoverCalibrationHub:
    """Encapsulates calibration state and serialization per gateway."""

    def __init__(self, gateway: Any) -> None:
        self.gateway: MyHOMEGatewayHandler = gateway
        self.trace: collections.deque[dict[str, Any]] = collections.deque(maxlen=1000)
        self._lock: asyncio.Lock | None = None
        self._active_cover: Any | None = None
        self._queued_covers: set[Any] = set()

    @property
    def mac(self) -> str | None:
        """Return the normalized gateway MAC address."""
        return _normalize_mac(getattr(self.gateway, "mac", None))

    @property
    def key(self) -> str:
        """Return a unique key for the gateway."""
        return _gateway_key(self.gateway)

    @property
    def lock(self) -> asyncio.Lock:
        """Return the asyncio.Lock, dynamically rebinding if the running loop changed."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._lock is not None:
            # If the lock was removed from legacy storage (e.g. test fixture reset), invalidate
            if self.key not in _CALIBRATION_LOCKS and (not self.mac or self.mac not in _CALIBRATION_LOCKS):
                self._lock = None

        if self._lock is not None:
            bound_loop = getattr(self._lock, "_bound_loop", None) or getattr(self._lock, "_loop", None)
            if (bound_loop is not None and bound_loop.is_closed()) or (
                current_loop is not None and bound_loop is not None and bound_loop is not current_loop
            ):
                self._lock = None

        if self._lock is None:
            self._lock = asyncio.Lock()
            if current_loop is not None:
                setattr(self._lock, "_bound_loop", current_loop)
            _CALIBRATION_LOCKS[self.key] = self._lock
            if self.mac:
                _CALIBRATION_LOCKS[self.mac] = self._lock

        return self._lock

    @property
    def active_cover(self) -> Any | None:
        """Return the currently calibrating cover for this gateway."""
        if self._active_cover is not None:
            return self._active_cover
        return _CALIBRATION_ACTIVE.get(self.key) or (self.mac and _CALIBRATION_ACTIVE.get(self.mac)) or None

    @active_cover.setter
    def active_cover(self, cover: Any | None) -> None:
        self._active_cover = cover
        if cover is None:
            _CALIBRATION_ACTIVE.pop(self.key, None)
            if self.mac:
                _CALIBRATION_ACTIVE.pop(self.mac, None)
        else:
            _CALIBRATION_ACTIVE[self.key] = cover
            if self.mac:
                _CALIBRATION_ACTIVE[self.mac] = cover

    @property
    def is_calibrating(self) -> bool:
        """Return True if any cover on this gateway is actively calibrating."""
        active = self.active_cover
        return bool(active is not None and getattr(active, "_calibrating", False))

    @property
    def queued_covers(self) -> set[Any]:
        """Return set of covers waiting for calibration lock on this gateway."""
        legacy = _CALIBRATION_QUEUED.setdefault(self.key, self._queued_covers)
        if legacy is not self._queued_covers:
            self._queued_covers.update(legacy)
            _CALIBRATION_QUEUED[self.key] = self._queued_covers
        return self._queued_covers

    def record_frame(self, direction: str, raw: str, **extra: Any) -> None:
        """Record a calibration frame to this hub's trace buffer and legacy trace."""
        now = dt_util.utcnow()
        frame = {
            "timestamp": time.time(),
            "iso_time": now.isoformat(),
            "gateway_mac": self.mac,
            "direction": direction,
            "raw": str(raw).strip(),
            **extra,
        }
        self.trace.append(frame)
        _LAST_CALIBRATION_TRACE.append(frame)

    def get_trace(self) -> list[dict[str, Any]]:
        """Return the in-memory trace frames recorded for this gateway."""
        return list(self.trace)

    async def async_stop(self) -> bool:
        """Stop active and queued calibrations on this gateway."""
        stopped_any = False
        queued = list(self.queued_covers)
        self.queued_covers.clear()
        for c in queued:
            c._calibration_interrupted = "Calibration stopped by user"
            c._fire_calibration_event("failed", error="Calibration stopped by user")
            stopped_any = True

        active = self.active_cover
        if active is not None and getattr(active, "_calibrating", False):
            active._calibration_interrupted = "Calibration stopped by user"
            active._motor_started.set()
            active._stopped_event.set()
            try:
                await active.async_stop_cover()
            except Exception as err:
                LOGGER.warning("Error stopping cover %s: %s", active.entity_id, err)
            stopped_any = True
            self.active_cover = None

        return stopped_any

    def cleanup(self) -> None:
        """Clean up all references when gateway unloads."""
        self._active_cover = None
        self._queued_covers.clear()
        self._lock = None
        _CALIBRATION_LOCKS.pop(self.key, None)
        _CALIBRATION_ACTIVE.pop(self.key, None)
        _CALIBRATION_QUEUED.pop(self.key, None)
        if self.mac:
            _CALIBRATION_LOCKS.pop(self.mac, None)
            _CALIBRATION_ACTIVE.pop(self.mac, None)
            _CALIBRATION_QUEUED.pop(self.mac, None)
        self.trace.clear()


def get_calibration_hub(gateway: Any) -> CoverCalibrationHub:
    """Return or create the CoverCalibrationHub for a gateway handler."""
    entry = getattr(gateway, "config_entry", None)
    runtime = getattr(entry, "runtime_data", None) if entry is not None else None
    if isinstance(runtime, MyHOMERuntimeData):
        if runtime.calibration_hub is None:
            runtime.calibration_hub = CoverCalibrationHub(gateway)
        return runtime.calibration_hub

    if runtime is not None:
        raw_hub = getattr(runtime, "calibration_hub", None)
        if isinstance(raw_hub, CoverCalibrationHub):
            return raw_hub

    # Fallback when runtime_data is not available (e.g. mock objects in unit tests)
    hub = getattr(gateway, "_calibration_hub", None)
    if not isinstance(hub, CoverCalibrationHub):
        hub = CoverCalibrationHub(gateway)
        try:
            gateway._calibration_hub = hub
        except Exception:  # pragma: no cover - defensive
            pass
    return hub
