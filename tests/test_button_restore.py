"""Regression tests for lock/unlock buttons after discovery and restart."""

import logging
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome import button
from custom_components.myhome.const import DOMAIN

MAC = "00:03:50:81:17:76"


@pytest.mark.parametrize(
    ("domain", "who", "address"),
    [("light", "1", "01"), ("switch", "1", "0015"),
     ("cover", "2", "01"), ("cover", "2", "01#4#02")],
)
async def test_registered_actuator_buttons_survive_reload(hass, domain, who, address):
    """Restore the same HA entities without requiring a new discovery event."""
    entry = MockConfigEntry(domain=DOMAIN, data={"mac": MAC})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{MAC}-{who}-{address}")},
        name="Actuator", manufacturer="Legrand", model="Existing model",
    )
    registry.async_get_or_create(
        domain, DOMAIN, f"{MAC}-{who}-{address}",
        config_entry=entry, original_name="Actuator", device_id=device.id,
    )
    expected_ids = []
    for suffix in ("disable", "enable"):
        registered = registry.async_get_or_create(
            "button", DOMAIN, f"{MAC}-{who}-{address}-{suffix}",
            config_entry=entry, suggested_object_id=f"custom_{suffix}", device_id=device.id,
        )
        expected_ids.append(registered.entity_id)

    gateway = MagicMock(
        mac=MAC, unique_id=MAC, available=True,
        availability_signal=f"myhome_{MAC}_availability", device_registry_id=None,
    )
    for _ in range(2):
        # Only the entity registry survives a fresh setup: no YAML/discovery cache.
        hass.data[DOMAIN] = {MAC: {"entity": gateway, "platforms": {"button": {}}}}
        platform = EntityPlatform(
            hass=hass, logger=logging.getLogger(__name__), domain="button",
            platform_name=DOMAIN, platform=button, scan_interval=timedelta(seconds=30),
            entity_namespace=None,
        )
        assert await platform.async_setup_entry(entry)
        await hass.async_block_till_done()
        try:
            assert set(platform.entities) == set(expected_ids)
            assert devices.async_get(device.id).model == "Existing model"
            assert devices.async_get(device.id).manufacturer == "Legrand"
            for entity_id in expected_ids:
                state = hass.states.get(entity_id)
                assert state is not None
                assert state.state != STATE_UNAVAILABLE
                assert not state.attributes.get("restored")
                assert registry.async_get(entity_id).device_id == device.id

            where, _, interface = address.partition("#4#")
            async_dispatcher_send(hass, f"myhome_new_device_{MAC}", {
                "who": who, "where": where, "interface": interface or None,
                "name": "Actuator", "device_id": address,
            })
            await hass.async_block_till_done()
            assert set(platform.entities) == set(expected_ids)

            gateway.available = False
            async_dispatcher_send(hass, gateway.availability_signal)
            await hass.async_block_till_done()
            assert all(hass.states.get(e).state == STATE_UNAVAILABLE for e in expected_ids)
            gateway.available = True
            async_dispatcher_send(hass, gateway.availability_signal)
            await hass.async_block_till_done()
            assert all(hass.states.get(e).state != STATE_UNAVAILABLE for e in expected_ids)
        finally:
            await platform.async_reset()
            await entry._async_process_on_unload(hass)


async def test_restore_filters_and_deduplicates_actuators(hass):
    """Keep gateway/WHO/address boundaries and ignore unrelated or deleted devices."""
    entry = MockConfigEntry(domain=DOMAIN, data={"mac": MAC})
    entry.add_to_hass(hass)
    other_entry = MockConfigEntry(domain=DOMAIN, data={"mac": "00:03:50:00:00:02"})
    other_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for domain, unique_id, config in [
        ("light", f"{MAC}-1-01", entry),
        ("cover", f"{MAC}-2-01", entry),
        ("sensor", f"{MAC}-1-12", entry),
        ("light", f"{MAC}-1-#1", entry),
        ("light", "foreign-1-99", entry),
        ("cover", f"{MAC}-1-42", entry),
        ("light", f"{MAC}-1-31", other_entry),
        ("button", f"{MAC}-1-88-disable", entry),
    ]:
        registry.async_get_or_create(domain, DOMAIN, unique_id, config_entry=config)
    gateway = MagicMock(mac=MAC, unique_id=MAC)
    hass.data[DOMAIN] = {MAC: {
        "entity": gateway,
        "platforms": {"button": {
            "configured": {"who": "1", "where": "01", "name": "Configured light"},
        }},
    }}
    added = []
    await button.async_setup_entry(hass, entry, added.extend)
    try:
        assert {e.unique_id for e in added} == {
            f"{MAC}-{who}-01-{suffix}"
            for who in ("1", "2") for suffix in ("disable", "enable")
        }
        assert len(added) == 4
        assert added[0].entity_id == "button.configured_light_lock"
    finally:
        await entry._async_process_on_unload(hass)
