"""Build the shared decoder pool of a MyHOME gateway from its options."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DECODER_ENTITY,
    CONF_DECODER_PRE_GAIN,
    CONF_DECODER_SLOTS,
    CONF_DECODER_SOURCE,
    LOGGER,
)
from .data import MyHOMEConfigEntry
from .decoder_companion import async_find_streaming_companion
from .decoder_pool import DecoderPool, decoder_pool_store
from .repairs import (
    async_create_incompatible_decoder_issue,
    async_delete_incompatible_decoder_issue,
    async_prune_incompatible_decoder_issues,
)

# Integrations that cannot play a stream URL, and the media types they do take.
# ``cambridge_audio`` (StreamMagic) accepts presets, Airable and internet radio
# only; a Music Assistant stream is refused with ``unsupported_media_type``.
STREAM_INCOMPATIBLE_PLATFORMS: dict[str, frozenset[str]] = {
    "cambridge_audio": frozenset({"preset", "airable", "internet_radio"}),
}


def build_pool(hass: HomeAssistant, config_entry: MyHOMEConfigEntry) -> DecoderPool:
    """Build a :class:`DecoderPool` from the current options entry.

    Called from :func:`~.media_player.async_setup_entry`, which an options change
    re-runs by reloading the entry.

    Args:
        hass: Home Assistant instance.
        config_entry: The active config entry for this MyHOME gateway.

    Returns:
        A fully configured :class:`DecoderPool` (may have zero decoders if
        nothing is configured yet).
    """
    options = config_entry.options
    decoder_map: dict[str, int] = {}
    pre_gain_map: dict[str, int] = {}
    stream_incompatible: set[str] = set()
    companion_map: dict[str, str] = {}
    ent_reg = er.async_get(hass)

    for i in range(1, CONF_DECODER_SLOTS + 1):
        entity_id = options.get(CONF_DECODER_ENTITY.format(i), "").strip()
        source_num = options.get(CONF_DECODER_SOURCE.format(i), i)  # int
        pre_gain = options.get(CONF_DECODER_PRE_GAIN.format(i), 0)  # int

        if entity_id and entity_id.startswith("media_player."):
            decoder_map[entity_id] = int(source_num)  # always int — never f"Source N"
            pre_gain_map[entity_id] = int(pre_gain)
            reg_entry = ent_reg.async_get(entity_id)
            if reg_entry and reg_entry.platform in STREAM_INCOMPATIBLE_PLATFORMS:
                companion = async_find_streaming_companion(hass, entity_id)
                if companion:
                    LOGGER.info(
                        "MyHOME media player: decoder %s (%s) has streaming companion %s — dynamic DLNA bridge enabled",
                        entity_id,
                        reg_entry.platform,
                        companion,
                    )
                    companion_map[entity_id] = companion
                    async_delete_incompatible_decoder_issue(hass, config_entry.entry_id, entity_id)
                else:
                    stream_incompatible.add(entity_id)
                    async_create_incompatible_decoder_issue(
                        hass, config_entry.entry_id, entity_id, reg_entry.platform
                    )
            else:
                async_delete_incompatible_decoder_issue(hass, config_entry.entry_id, entity_id)

    # Clean up any previously flagged decoder issues that are no longer configured
    async_prune_incompatible_decoder_issues(hass, config_entry.entry_id, decoder_map)

    return DecoderPool(
        hass,
        decoder_map,
        pre_gain_map,
        stream_incompatible=stream_incompatible,
        companion_map=companion_map,
        store=decoder_pool_store(hass, config_entry.entry_id),
    )
