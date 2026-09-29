"""Helper for cross-integration decoder discovery and companion resolution.

The MyHOME BTicino F441M analog matrix connects to physical hardware decoders
(such as Cambridge Audio, Squeezelite, WiiM, Sonos, etc.). Some vendor integrations
(e.g. ``cambridge_audio``) expose device controls but refuse direct HTTP stream
URLs via ``play_media``. However, the underlying hardware also exposes standard
UPnP / DLNA DMR, which accepts stream URLs.

This module provides registry lookups to find companion streaming entities
for a given decoder entity.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

STREAMING_COMPANION_PLATFORMS: frozenset[str] = frozenset({"dlna_dmr", "upnp", "cast"})


def async_find_streaming_companion(hass: HomeAssistant, entity_id: str) -> str | None:
    """Find a streaming-capable companion entity (e.g. DLNA DMR, Cast) for an entity.

    Inspects Home Assistant's Entity Registry, Device Registry, and Config Entries
    to find whether the physical hardware behind ``entity_id`` also exposes a DLNA DMR,
    Google Cast, or other streaming-capable media_player entity.

    Args:
        hass: Home Assistant instance.
        entity_id: The entity_id of the configured decoder (e.g. media_player.network_streamer).

    Returns:
        The entity_id of the companion media_player, or None if not found.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    entry = ent_reg.async_get(entity_id)
    if not entry:
        return None

    # 1. Check all entities attached to the EXACT same device in Home Assistant
    if entry.device_id:
        for cand in er.async_entries_for_device(ent_reg, entry.device_id):
            if cand.domain == "media_player" and cand.entity_id != entity_id:
                if cand.platform in STREAMING_COMPANION_PLATFORMS:
                    return cand.entity_id

    device = dev_reg.async_get(entry.device_id) if entry.device_id else None

    # 2. Check devices sharing the same MAC address (if not merged by device registry)
    if device is not None:
        macs = {conn[1] for conn in device.connections if conn[0] == dr.CONNECTION_NETWORK_MAC}
        if macs:
            all_devices = dev_reg.devices.values() if hasattr(dev_reg.devices, "values") else dev_reg.devices
            for other_dev in all_devices:
                if other_dev.id == device.id:
                    continue
                other_macs = {conn[1] for conn in other_dev.connections if conn[0] == dr.CONNECTION_NETWORK_MAC}
                if macs & other_macs:
                    for cand in er.async_entries_for_device(ent_reg, other_dev.id):
                        if cand.domain == "media_player" and cand.platform in STREAMING_COMPANION_PLATFORMS:
                            return cand.entity_id

    # 3. Check config entries sharing the same host/IP address
    host = None
    if entry.config_entry_id:
        cfg = hass.config_entries.async_get_entry(entry.config_entry_id)
        if cfg:
            host = cfg.data.get("host") or cfg.data.get("ip_address")

    if host:
        for other_entry in hass.config_entries.async_entries():
            if other_entry.entry_id == entry.config_entry_id:
                continue
            other_host = other_entry.data.get("host") or other_entry.data.get("ip_address")
            if other_host == host:
                for cand in er.async_entries_for_config_entry(ent_reg, other_entry.entry_id):
                    if cand.domain == "media_player" and cand.platform in STREAMING_COMPANION_PLATFORMS:
                        return cand.entity_id

    # 4. Check devices with matching names (e.g. user-named "Audio Decoder")
    if device is not None:
        dev_name = (device.name_by_user or device.name or "").lower().strip()
        if dev_name:
            all_devices = dev_reg.devices.values() if hasattr(dev_reg.devices, "values") else dev_reg.devices
            for other_dev in all_devices:
                if other_dev.id == device.id:
                    continue
                other_name = (other_dev.name_by_user or other_dev.name or "").lower().strip()
                if other_name and (other_name == dev_name or other_name in dev_name or dev_name in other_name):
                    for cand in er.async_entries_for_device(ent_reg, other_dev.id):
                        if cand.domain == "media_player" and cand.platform in STREAMING_COMPANION_PLATFORMS:
                            return cand.entity_id

    return None


def async_get_excluded_decoders(hass: HomeAssistant) -> list[str]:
    """Return entity IDs that must not be selected as decoders.

    Excludes internal MyHOME sound zones (preventing circular loops) and
    Music Assistant cloned entities.
    """
    ent_reg = er.async_get(hass)
    return [
        entry.entity_id
        for entry in ent_reg.entities.values()
        if entry.domain == "media_player" and entry.platform in ("myhome", "mass")
    ]
