"""#466: MyHomeServer1 sweep with a setpoint experiment on zone 55 (contributed by @gdluck)."""

from __future__ import annotations

import json
from pathlib import Path

from OWNd.message import OWNHeatingEvent, OWNLightingEvent, OWNMessage

TRACE = (
    Path(__file__).resolve().parent
    / "fixtures/traces/issue_466/myhome_sweep_MyHomeServer1_all_2026-09-29T18-20-22.json"
)


def _frames() -> list[dict]:
    return json.loads(TRACE.read_text(encoding="utf-8"))["frames"]


def test_every_frame_parses():
    messages = [OWNMessage.parse(f["raw"]) for f in _frames()]
    assert len(messages) == 200
    assert all(m is not None for m in messages)
    assert sum(isinstance(m, OWNLightingEvent) for m in messages) >= 40
    assert sum(isinstance(m, OWNHeatingEvent) for m in messages) >= 100


def test_zone_55_pump_stops_before_the_valve_closes():
    """Pump call/stop and the actuator status arrive in this order on the wire."""
    order = [
        f["raw"]
        for f in _frames()
        if f["raw"]
        in (
            "*#4*55#1*20*1##",
            "*4*4001#55*0#3##",
            "*4*4002#55*0#3##",
            "*#4*55#1*20*0##",
        )
    ]
    assert order == ["*#4*55#1*20*1##", "*4*4001#55*0#3##", "*4*4002#55*0#3##", "*#4*55#1*20*0##"]


def test_setpoint_write_is_echoed_as_dimension_12_mode_3():
    frames = [f["raw"] for f in _frames()]
    write = frames.index("*#4*60*#14*0235*1##")
    assert frames[write + 1] == "*#4*60*12*0235*3##"
    assert frames[write + 2] == "*4*1*60##"
