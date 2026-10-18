"""Base protocol and shared timing state for pluggable MyHOME cover kinematics strategies."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from homeassistant.components.cover import CoverEntityFeature

from ..const import (
    DEFAULT_MIN_MOTOR_PULSE,
    DEFAULT_SLAT_TIME,
    DEFAULT_TRAVEL_TIME,
    MAX_SLAT_TIME,
    MIN_SLAT_TIME,
)
from ..cover_motion import travel_for


def clamp_slat_time(value: Any, fallback: float = DEFAULT_SLAT_TIME) -> float:
    """Return a slat rotation time clamped to [MIN_SLAT_TIME, MAX_SLAT_TIME]."""
    try:
        seconds = float(value) if value is not None else float(fallback)
    except (TypeError, ValueError):
        seconds = float(fallback)
    return max(MIN_SLAT_TIME, min(MAX_SLAT_TIME, seconds))


@runtime_checkable
class CoverKinematicsStrategy(Protocol):
    """Protocol implemented by all pluggable WHO=2 cover kinematics strategies.

    Strategies own timing parameters (``travel_time_down``, ``travel_time_up``,
    ``min_motor_pulse``, ``slat_time``), the time<->position mapping via
    ``position_after`` and ``duration_for``, slat rotation kinematics, and
    stop-echo re-anchoring via ``reanchor_on_stop_echo``, allowing linear timed
    covers, Venetian slat+roll blinds, and non-linear calibrated geometry
    strategies (#374) to plug into ``MyHOMECover`` without modifying the entity class.
    """

    travel_time_down: float
    travel_time_up: float
    min_motor_pulse: float
    slat_time: float

    @property
    def name(self) -> str:
        """Return strategy identifier."""

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return Home Assistant CoverEntityFeature bitmask for this strategy."""

    @property
    def assumed_state(self) -> bool:
        """Return whether cover position/state is assumed rather than bus-reported or calibrated."""

    def travel_for_direction(self, opening: bool) -> float:
        """Return full end-to-end travel seconds for the given direction."""

    def curtain_travel_for(self, opening: bool) -> float:
        """Return vertical curtain travel seconds for the given direction."""

    def lead_time_for(self, opening: bool, *, entity: Any = None) -> float:
        """Return seconds spent rotating slats before vertical curtain motion begins."""

    def min_pulse_for(self) -> float:
        """Return minimum motor pulse floor in seconds."""

    def slat_time_for(self) -> float:
        """Return full slat rotation time in seconds."""

    def quantize_target(self, current: int | None, target: int) -> int:
        """Quantize a target position against the strategy's deadband if applicable."""

    def turn_slats_after(
        self,
        start_tilt: int | None,
        elapsed: float,
        direction: str,
    ) -> int:
        """Return clamped [0, 100] slat tilt angle after ``elapsed`` seconds in ``direction``."""

    def carry_overshoot_into_curtain(
        self,
        start_position: int,
        start_tilt: int,
        elapsed: float,
        direction: str,
    ) -> int:
        """Convert motor runtime past a full slat rotation into vertical curtain displacement."""

    def tilt_pulse_duration_for(
        self,
        start_tilt: int,
        target_tilt: int,
        *,
        enforce_min_pulse: bool = True,
    ) -> float:
        """Compute motor pulse seconds to rotate slats from ``start_tilt`` to ``target_tilt``."""

    def position_after(
        self,
        start: int,
        elapsed: float,
        direction: str,
        *,
        entity: Any = None,
        lead: float | None = None,
    ) -> int | None:
        """Return cover position (0..100 or None) after ``elapsed`` seconds in ``direction`` from ``start``."""

    def duration_for(
        self,
        start: int,
        target: int,
        direction: str | None = None,
        *,
        entity: Any = None,
    ) -> float:
        """Return motor run duration in seconds required to move from ``start`` to ``target``."""

    def reanchor_on_stop_echo(
        self,
        entity: Any,
        ctx: dict[str, Any],
        now: float,
    ) -> int | None:
        """Re-anchor position (and slat tilt if applicable) on a relayed stop status echo (#705)."""

    def current_position(self, entity: Any, now: float) -> int | None:
        """Return current cover position (0..100) or None if position is unknown."""


class BaseCoverStrategy:
    """Shared timing configuration and default slat helpers for WHO=2 cover strategies."""

    def __init__(
        self,
        travel_time: float = DEFAULT_TRAVEL_TIME,
        *,
        travel_time_up: float | None = None,
        travel_time_down: float | None = None,
        min_motor_pulse: float = DEFAULT_MIN_MOTOR_PULSE,
        slat_time: float | None = None,
    ) -> None:
        """Initialize timing parameters owned by the strategy."""
        base = float(travel_time) if travel_time and travel_time > 0 else float(DEFAULT_TRAVEL_TIME)
        self.travel_time_down: float = (
            float(travel_time_down) if travel_time_down is not None and travel_time_down > 0 else base
        )
        self.travel_time_up: float = (
            float(travel_time_up) if travel_time_up is not None and travel_time_up > 0 else self.travel_time_down
        )
        self.min_motor_pulse: float = max(0.0, float(min_motor_pulse))
        self.slat_time: float = clamp_slat_time(slat_time, DEFAULT_SLAT_TIME)

    def travel_for_direction(self, opening: bool) -> float:
        """Return full end-to-end travel seconds for the given direction."""
        return travel_for(self.travel_time_up, self.travel_time_down, opening)

    def curtain_travel_for(self, opening: bool) -> float:
        """Return vertical curtain travel seconds for the given direction."""
        return self.travel_for_direction(opening)

    def lead_time_for(self, opening: bool, *, entity: Any = None) -> float:  # pylint: disable=unused-argument
        """Return seconds spent rotating slats before vertical curtain motion begins."""
        return 0.0

    def min_pulse_for(self) -> float:
        """Return minimum motor pulse floor in seconds (#704, #708)."""
        return self.min_motor_pulse

    def slat_time_for(self) -> float:
        """Return the effective slat full-rotation time in seconds."""
        return self.slat_time

    def quantize_target(self, current: int | None, target: int) -> int:  # pylint: disable=unused-argument
        """Return target unchanged by default (overridden by NativePositionStrategy)."""
        return int(target)

    def turn_slats_after(
        self,
        start_tilt: int | None,
        elapsed: float,
        direction: str,
    ) -> int:
        """Return clamped [0, 100] slat tilt angle after ``elapsed`` seconds in ``direction``."""
        opening = direction == "open"
        curr = int(start_tilt) if start_tilt is not None else (0 if opening else 100)
        slat = self.slat_time_for()
        turned = (max(0.0, float(elapsed)) / slat) * 100.0 if slat > 0 else 100.0
        if opening:
            return min(100, int(round(curr + turned)))
        return max(0, int(round(curr - turned)))

    def carry_overshoot_into_curtain(
        self,
        start_position: int,
        start_tilt: int,
        elapsed: float,
        direction: str,
    ) -> int:  # pylint: disable=unused-argument
        """Return ``start_position`` unchanged by default (overridden by VenetianTiltStrategy)."""
        return max(0, min(100, int(round(start_position))))

    def tilt_pulse_duration_for(
        self,
        start_tilt: int,
        target_tilt: int,
        *,
        enforce_min_pulse: bool = True,
    ) -> float:
        """Compute motor pulse seconds to rotate slats from ``start_tilt`` to ``target_tilt``."""
        clamped_start = max(0, min(100, int(round(start_tilt))))
        clamped_target = max(0, min(100, int(round(target_tilt))))
        diff = clamped_target - clamped_start
        if diff == 0:
            return 0.0
        run_duration = (abs(diff) / 100.0) * self.slat_time_for()
        if enforce_min_pulse and run_duration < self.min_pulse_for():
            return 0.0
        return run_duration

