"""Test decoder companion resolution and discovery."""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.decoder_companion import (
    async_find_streaming_companion,
    async_get_excluded_decoders,
)


@pytest.mark.asyncio
async def test_find_streaming_companion_same_device(hass: HomeAssistant) -> None:
    """Test finding a streaming companion registered to the exact same device."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    cam_entry = MockConfigEntry(domain="cambridge_audio")
    cam_entry.add_to_hass(hass)

    device = dev_reg.async_get_or_create(
        config_entry_id=cam_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "00:11:22:33:44:55")},
        identifiers={("cambridge_audio", "unique_cambridge_1")},
        manufacturer="Cambridge Audio",
        model="CXN V2",
    )

    # Cambridge primary entity
    ent_reg.async_get_or_create(
        "media_player",
        "cambridge_audio",
        "unique_cambridge_1",
        device_id=device.id,
        suggested_object_id="streamer",
    )

    # Companion DLNA DMR entity
    ent_reg.async_get_or_create(
        "media_player",
        "dlna_dmr",
        "unique_dlna_1",
        device_id=device.id,
        suggested_object_id="streamer_dlna",
    )

    companion = async_find_streaming_companion(hass, "media_player.streamer")
    assert companion == "media_player.streamer_dlna"


@pytest.mark.asyncio
async def test_find_streaming_companion_by_mac_address(hass: HomeAssistant) -> None:
    """Test finding a streaming companion on another device sharing the same MAC."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    cam_entry = MockConfigEntry(domain="cambridge_audio")
    cam_entry.add_to_hass(hass)
    dlna_entry = MockConfigEntry(domain="dlna_dmr")
    dlna_entry.add_to_hass(hass)

    device1 = dev_reg.async_get_or_create(
        config_entry_id=cam_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        identifiers={("cambridge_audio", "id1")},
    )
    device2 = dev_reg.async_get_or_create(
        config_entry_id=dlna_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        identifiers={("dlna_dmr", "id2")},
    )

    ent_reg.async_get_or_create(
        "media_player",
        "cambridge_audio",
        "cambridge_unique",
        device_id=device1.id,
        suggested_object_id="cambridge_streamer",
    )

    ent_reg.async_get_or_create(
        "media_player",
        "dlna_dmr",
        "dlna_unique",
        device_id=device2.id,
        suggested_object_id="cambridge_dlna",
    )

    companion = async_find_streaming_companion(hass, "media_player.cambridge_streamer")
    assert companion == "media_player.cambridge_dlna"


@pytest.mark.asyncio
async def test_find_streaming_companion_not_found(hass: HomeAssistant) -> None:
    """Test returning None when no streaming companion is available."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    cam_entry = MockConfigEntry(domain="cambridge_audio")
    cam_entry.add_to_hass(hass)

    device = dev_reg.async_get_or_create(
        config_entry_id=cam_entry.entry_id,
        identifiers={("cambridge_audio", "solo_id")},
    )
    ent_reg.async_get_or_create(
        "media_player",
        "cambridge_audio",
        "solo_unique",
        device_id=device.id,
        suggested_object_id="solo_audio",
    )

    companion = async_find_streaming_companion(hass, "media_player.solo_audio")
    assert companion is None


@pytest.mark.asyncio
async def test_excluded_decoders_includes_myhome_and_mass(hass: HomeAssistant) -> None:
    """Excluded decoders includes mass and myhome, but not physical players."""
    ent_reg = er.async_get(hass)

    ent_reg.async_get_or_create("media_player", "myhome", "myhome_zone_1", suggested_object_id="dining_room")
    ent_reg.async_get_or_create("media_player", "mass", "mass_player_1", suggested_object_id="mass_dining_room")
    ent_reg.async_get_or_create("media_player", "squeezelite", "squeezelite_1", suggested_object_id="kitchen_pi")
    ent_reg.async_get_or_create("media_player", "dlna_dmr", "dlna_1", suggested_object_id="living_dlna")

    excluded = async_get_excluded_decoders(hass)

    assert "media_player.dining_room" in excluded
    assert "media_player.mass_dining_room" in excluded
    assert "media_player.kitchen_pi" not in excluded
    assert "media_player.living_dlna" not in excluded
