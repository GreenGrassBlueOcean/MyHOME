"""Regression and discovery tests for central heating units (BTicino 3550 / 4695).

Guarantees:
1. Physical bus frames from 3550 central units (#0) and 4-zone central units (#0#1)
   never trigger bus discovery of phantom 'Climate Zone 99' (#582).
2. Deleting an unused/ghost heating zone entity permanently drops its unresponsive
   repair alert and prevents resurrection in the absence of on-wire frames for that zone.
3. Central units operate via event-driven broadcast synchronization without point-to-point status polling.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from OWNd.message import OWNEvent, OWNHeatingEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.climate import (
    MyHOMEClimate,
    _calling_zones,
    _zone_address,
    _zone_route_keys,
    async_setup_entry,
)
from custom_components.myhome.const import DOMAIN
from tests.conftest import attach_runtime

MAC = "00:03:50:44:55:66"

BTICINO_3550_FRAMES = [
    "*4*101*#0##",  # Heating command mode
    "*4*102*#0##",  # Cooling / Antifreeze command mode
    "*4*100*#0##",  # Conditioning / Heating OFF command mode
    "*4*103*#0##",  # Automatic command mode
    "*4*110*#0##",  # Heating status event
    "*4*210*#0##",  # Cooling status event
    "*4*303*#0##",  # OFF status event
    "*4*311*#0##",  # Auto status event
    "*4*110#0200*#0##",  # Manual setpoint 20.0 °C on central unit
    "*4*210#0240*#0##",  # Cooling setpoint 24.0 °C on central unit
    "*4*21*#0##",  # Remote control enabled
    "*4*20*#0##",  # Remote control disabled
    "*4*31*#0##",  # Central unit battery fault
    "*4*40*#0##",  # Release local probe adjustment
    "*4*1101*#0##",  # Weekly program 1
    "*4*1102*#0##",  # Weekly program 2
    "*4*1103*#0##",  # Weekly program 3
    "*4*1201*#0##",  # Scenario 1
    "*#4*#0*30*01*10*2026##",  # Holiday end date
    "*#4*#0*31*12*00##",  # Holiday end time
]

BTICINO_4695_FRAMES = [
    "*4*101*#0#1##",
    "*4*102*#0#1##",
    "*4*100*#0#1##",
    "*4*110*#0#1##",
    "*4*210*#0#1##",
    "*4*303*#0#1##",
    "*4*110#0210*#0#1##",
]


@pytest.mark.parametrize("raw_frame", BTICINO_3550_FRAMES)
def test_3550_frames_never_resolve_to_zone_99(raw_frame: str) -> None:
    """Assert that 3550 central unit frames never resolve to zone 99 in routing or discovery (#582)."""
    message = OWNEvent.parse(raw_frame)
    assert message is not None

    zones, interface = _calling_zones(message)
    assert "99" not in zones

    address = _zone_address(message)
    if address is not None:
        assert address.where != "99"
        assert address.clean_where != "99"

    route_keys = _zone_route_keys(message, address)
    assert "99" not in route_keys
    assert "4-99" not in route_keys


@pytest.mark.parametrize("raw_frame", BTICINO_4695_FRAMES)
def test_4695_frames_never_resolve_to_zone_99(raw_frame: str) -> None:
    """Assert that 4695 4-zone central unit frames never resolve to zone 99 (#582)."""
    message = OWNEvent.parse(raw_frame)
    assert message is not None

    zones, interface = _calling_zones(message)
    assert "99" not in zones

    address = _zone_address(message)
    if address is not None:
        assert address.where != "99"
        assert address.clean_where != "99"

    route_keys = _zone_route_keys(message, address)
    assert "99" not in route_keys


async def test_3550_bus_traffic_never_discovers_phantom_climate_zone_99(hass: HomeAssistant) -> None:
    """Feed complete 3550 central unit bus activity into PlatformDiscovery and assert zone 99 is never created (#582)."""
    entry = MockConfigEntry(domain=DOMAIN, data={"mac": MAC}, unique_id=MAC)
    entry.add_to_hass(hass)

    gateway = MagicMock()
    gateway.mac = MAC
    gateway.log_id = "[test 3550 discovery]"
    gateway.send = AsyncMock()
    gateway.send_status_request = AsyncMock()

    runtime = attach_runtime(hass, entry, MAC, gateway)
    runtime.platforms["climate"] = {
        "central_unit": {
            "zone": "#0",
            "name": "Centrale termoregolazione",
            "heat": True,
            "cool": False,
            "central": True,
            "standalone": False,
            "manufacturer": "BTicino",
            "model": "3550",
        }
    }

    discovered_entities: list[MyHOMEClimate] = []
    await async_setup_entry(hass, entry, discovered_entities.extend)

    # 1. Initially, only the configured central unit exists
    assert len(discovered_entities) == 1
    assert discovered_entities[0]._where == "#0"
    assert discovered_entities[0]._central is True

    # 2. Dispatch all 3550 central unit traffic through the event dispatcher
    for raw_frame in BTICINO_3550_FRAMES:
        event = OWNHeatingEvent(raw_frame)
        runtime.gateway._event_dispatcher.process_message_sync(event)

    # 3. Assert zero additional entities were discovered
    assert len(discovered_entities) == 1
    assert not any(getattr(e, "_where", None) == "99" for e in discovered_entities)
    assert not any("99" in (getattr(e, "name", "") or "") for e in discovered_entities)


async def test_ghost_zone_99_deletion_permanently_clears_repair_and_prevents_resurrection(
    hass: HomeAssistant,
) -> None:
    """Assert deleting a ghost Climate Zone 99 entity removes its repair and does not resurrect on central bus traffic (#582)."""
    entry = MockConfigEntry(domain=DOMAIN, data={"mac": MAC}, unique_id=MAC)
    entry.add_to_hass(hass)

    gateway = MagicMock()
    gateway.mac = MAC
    gateway.log_id = "[test ghost 99]"
    gateway.name = "MyHomeServer1 Gateway"
    gateway.send = AsyncMock()
    gateway.send_status_request = AsyncMock()

    runtime = attach_runtime(hass, entry, MAC, gateway)
    runtime.platforms["climate"] = {
        "central_unit": {
            "zone": "#0",
            "name": "Centrale termoregolazione",
            "central": True,
        }
    }

    # Simulate pre-existing ghost entity in entity registry (e.g. from prior user configuration)
    entity_reg = er.async_get(hass)
    ghost_reg_entry = entity_reg.async_get_or_create(
        domain="climate",
        platform=DOMAIN,
        unique_id=f"{MAC}-4-99",
        config_entry=entry,
        original_name="Climate Zone 99",
    )
    assert "99" in ghost_reg_entry.entity_id

    entities: list[MyHOMEClimate] = []
    await async_setup_entry(hass, entry, entities.extend)

    # Both central unit and registered ghost zone 99 are built
    assert len(entities) == 2
    cu = next(e for e in entities if e._where == "#0")
    assert cu._central is True
    ghost_z99 = next(e for e in entities if e._where == "99")
    ghost_z99.entity_id = ghost_reg_entry.entity_id

    # Simulate 2 failed polls on ghost zone 99
    future_nack = asyncio.get_running_loop().create_future()
    gateway.send_status_request.return_value = future_nack
    await ghost_z99.async_update()
    future_nack.cancel()
    await asyncio.sleep(0)

    future_nack2 = asyncio.get_running_loop().create_future()
    gateway.send_status_request.return_value = future_nack2
    await ghost_z99.async_update()
    future_nack2.cancel()
    await asyncio.sleep(0)

    # Repair issue is raised for ghost zone 99
    issue_id = f"unresponsive_zone_{ghost_z99.unique_id}"
    issue_reg = ir.async_get(hass)
    assert issue_reg.async_get_issue(DOMAIN, issue_id) is not None

    # Owner removes the entity from Home Assistant settings
    entity_reg.async_remove(ghost_z99.entity_id)
    await ghost_z99.async_will_remove_from_hass()

    # The repair issue is automatically dropped
    assert issue_reg.async_get_issue(DOMAIN, issue_id) is None

    # Central unit bus activity does NOT resurrect or recreate ghost zone 99
    gateway.send_status_request.reset_mock()
    for raw_frame in BTICINO_3550_FRAMES:
        event = OWNHeatingEvent(raw_frame)
        runtime.gateway._event_dispatcher.process_message_sync(event)

    assert len(entities) == 2  # No new entities added
    assert issue_reg.async_get_issue(DOMAIN, issue_id) is None


async def test_central_unit_event_driven_synchronization(hass: HomeAssistant) -> None:
    """Verify central units operate purely via event-driven bus synchronization without point-to-point status polling (#582)."""
    gateway = MagicMock()
    gateway.mac = MAC
    gateway.log_id = "[test event-driven sync]"
    gateway.send = AsyncMock()
    gateway.send_status_request = AsyncMock()

    cu = MyHOMEClimate(
        hass=hass,
        device_id="cu_3550",
        who="4",
        where="#0",
        interface=None,
        name="Centrale termoregolazione",
        heating=True,
        cooling=True,
        fan=False,
        standalone=False,
        central=True,
        manufacturer="BTicino",
        model="Central Unit (3550)",
        gateway=gateway,
    )
    cu.entity_id = "climate.centrale_termoregolazione"
    cu.async_write_ha_state = MagicMock()

    # 1. Startup update sends zero status requests
    await cu.async_update()
    gateway.send_status_request.assert_not_called()

    # 2. Autonomous mode broadcast events update HVACMode immediately
    cu.handle_event(OWNHeatingEvent("*4*110*#0##"))
    assert cu.hvac_mode == HVACMode.HEAT

    cu.handle_event(OWNHeatingEvent("*4*210*#0##"))
    assert cu.hvac_mode == HVACMode.COOL

    cu.handle_event(OWNHeatingEvent("*4*103*#0##"))
    assert cu.hvac_mode == HVACMode.OFF

    # 3. Target setpoint broadcast frame updates target temperature and restores mode
    cu.handle_event(OWNHeatingEvent("*4*110#0215*#0##"))
    assert cu.target_temperature == 21.5
    assert cu.hvac_mode == HVACMode.HEAT
