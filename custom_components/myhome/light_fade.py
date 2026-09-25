"""Software stepped dimming transition engine for MyHOME lights."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from OWNd.message import OWNLightingCommand

from .const import (
    CONF_TRANSITION_MODE,
    CONF_WORKER_COUNT,
    DEFAULT_TRANSITION_MODE,
    LOGGER,
    SOFTWARE_TRANSITION_MAX_STEPS,
    SOFTWARE_TRANSITION_MIN_STEPS,
    SOFTWARE_TRANSITION_STEP_INTERVAL,
    TRANSITION_MODE_AUTO,
    TRANSITION_MODE_NATIVE,
    TRANSITION_MODE_SOFTWARE,
)

if TYPE_CHECKING:
    from .light import MyHOMELight


class SoftwareFadeEngine:
    """Manages software stepped transition fades using instant brightness commands."""

    def __init__(self, light: MyHOMELight) -> None:
        """Initialize the software fade engine for a light entity."""
        self.light: MyHOMELight = light
        self.fade_task: asyncio.Task[None] | None = None
        self.fade_id: int = 0
        self.cmd_lock: asyncio.Lock = asyncio.Lock()
        self.warned_multi_worker: bool = False

    @property
    def is_fading(self) -> bool:
        """Return whether a software fade task is currently active."""
        return bool(self.fade_task and not self.fade_task.done())

    def get_transition_mode(self) -> str:
        """Return the effective transition mode for the light."""
        handler = getattr(self.light, "_gateway_handler", None)
        if not handler or not handler.config_entry:
            return DEFAULT_TRANSITION_MODE
        raw = str(
            handler.config_entry.options.get(
                CONF_TRANSITION_MODE, DEFAULT_TRANSITION_MODE
            )
        )
        if raw == TRANSITION_MODE_AUTO:
            return TRANSITION_MODE_SOFTWARE
        if raw not in (TRANSITION_MODE_SOFTWARE, TRANSITION_MODE_NATIVE):
            return DEFAULT_TRANSITION_MODE
        return raw

    def should_use_software_stepped(self, transition: float | None) -> bool:
        """Return whether software-stepped dimming should be used."""
        if transition is None or transition <= 0:
            return False
        mode = self.get_transition_mode()
        return mode != TRANSITION_MODE_NATIVE

    async def set_brightness_instant(self, pct: int) -> None:
        """Send set_brightness with transition=0. Uses per-light lock to help ordering."""
        pct = max(0, min(100, int(pct)))
        async with self.cmd_lock:
            await self.light._gateway_handler.send(
                OWNLightingCommand.set_brightness(self.light._full_where, pct, 0)
            )

    async def maybe_instant_brightness(
        self, start_pct: int, target_pct: int, is_on: bool | None = None
    ) -> bool:
        """Execute instant brightness if delta <= 1%, skipping bus if already at target."""
        delta_pct = abs(target_pct - start_pct)
        if delta_pct <= 1:
            if not (self.light.is_on and target_pct == start_pct):
                await self.light._set_brightness_instant(target_pct)
            self.light._apply_brightness_state(target_pct, is_on=is_on)
            self.light.async_schedule_update_ha_state()
            return True
        return False

    def next_fade_id(self) -> int:
        """Increment and return the next fade sequence id."""
        self.fade_id += 1
        return self.fade_id

    def cancel_fade_if_active(self) -> None:
        """Simple cancel for @callback contexts (e.g. handle_event)."""
        if self.fade_task and not self.fade_task.done():
            self.fade_task.cancel()
            self.fade_task = None

    async def cancel_fade_robustly(self) -> None:
        """Robust cancel + drain for async contexts."""
        if self.fade_task and not self.fade_task.done():
            self.fade_task.cancel()
            try:
                # shield() prevents wait_for from double-cancelling the task
                # when the 0.15 s timeout fires (we already called .cancel()).
                await asyncio.wait_for(asyncio.shield(self.fade_task), timeout=0.15)
            except (Exception, asyncio.CancelledError):
                pass
            self.fade_task = None

    def start_fade(
        self, start_pct: int, target_pct: int, duration: float
    ) -> asyncio.Task[None]:
        """Start a software fade background task on the entity's Home Assistant loop."""
        fid = self.next_fade_id()
        task: asyncio.Task[None] = self.light.hass.async_create_task(
            self.async_fade_to(start_pct, target_pct, duration, fid)
        )
        self.fade_task = task
        return task

    async def async_fade_to(
        self, start_pct: int, target_pct: int, duration: float, fade_id: int
    ) -> None:
        """Background software stepped fade using instant brightness commands."""
        start_pct = max(0, min(100, int(start_pct or 0)))
        target_pct = max(0, min(100, int(target_pct or 0)))
        duration = max(0.0, float(duration))

        if fade_id != self.light._fade_id:
            return

        # Warn once if using multiple workers (can interleave steps for this light)
        try:
            handler = getattr(self.light, "_gateway_handler", None)
            if not self.warned_multi_worker and handler and handler.config_entry:
                wc = handler.config_entry.options.get(CONF_WORKER_COUNT, 1)
                if int(wc) > 1:
                    LOGGER.warning(
                        "%s: Using software stepped fade with command_worker_count=%s. "
                        "Step reordering is possible. Recommend =1 for reliable fades.",
                        self.light._where, wc
                    )
                    self.warned_multi_worker = True
        except Exception:
            pass

        if await self.maybe_instant_brightness(start_pct, target_pct):
            if fade_id == self.light._fade_id:
                self.fade_task = None
            return

        if duration < 0.05:
            await self.light._set_brightness_instant(target_pct)
            self.light._apply_brightness_state(target_pct)
            self.light.async_schedule_update_ha_state()
            if fade_id == self.light._fade_id:
                self.fade_task = None
            return

        delta_pct = abs(target_pct - start_pct)
        calc_steps = int(duration / SOFTWARE_TRANSITION_STEP_INTERVAL + 0.5)
        num_steps = max(
            min(SOFTWARE_TRANSITION_MIN_STEPS, delta_pct),
            min(
                SOFTWARE_TRANSITION_MAX_STEPS,
                calc_steps,
                delta_pct,
            ),
        )
        step_time = duration / num_steps
        delta = (target_pct - start_pct) / num_steps

        last_sent = start_pct
        try:
            for i in range(1, num_steps + 1):
                if fade_id != self.light._fade_id:
                    LOGGER.debug("%s Aborting stale fade step", self.light._where)
                    return
                current = int(round(start_pct + delta * i))
                current = max(0, min(100, current))

                if current != last_sent:
                    await self.light._set_brightness_instant(current)
                    self.light._apply_brightness_state(current)
                    self.light.async_schedule_update_ha_state()
                    last_sent = current

                if i < num_steps:
                    await asyncio.sleep(step_time)

            if fade_id == self.light._fade_id:
                if last_sent != target_pct:  # pragma: no cover - defensive guarantee
                    await self.light._set_brightness_instant(target_pct)
                self.light._apply_brightness_state(target_pct)
                self.light.async_schedule_update_ha_state()
        except asyncio.CancelledError:
            LOGGER.debug("%s Software fade cancelled (id=%s)", self.light._where, fade_id)
            raise
        except Exception as err:  # prevent "Task exception was never retrieved"
            LOGGER.warning("%s Fade task error (id=%s): %s", self.light._where, fade_id, err)
        finally:
            if fade_id == self.light._fade_id:
                self.fade_task = None
