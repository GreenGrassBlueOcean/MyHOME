""" MyHOME integration. """
import asyncio

from .ownd.message import OWNCommand, OWNGatewayCommand
from .gateway import MyHOMEGatewayHandler

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.const import CONF_HOST, CONF_MAC

from .const import (
    ATTR_GATEWAY,
    ATTR_MESSAGE,
    CONF_DECODER_ENTITY,
    CONF_DECODER_PRE_GAIN,
    CONF_DECODER_SLOTS,
    CONF_DECODER_SOURCE,
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITIES,
    CONF_GATEWAY,
    CONF_WORKER_COUNT,
    CONF_FILE_PATH,
    CONF_GENERATE_EVENTS,
    DOMAIN,
    LOGGER,
)
PLATFORMS = ["light", "switch", "cover", "climate", "binary_sensor", "sensor", "media_player", "button"]


async def async_setup(hass, config):
    """Set up the MyHOME component."""
    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    LOGGER.error("configuration.yaml not supported for this component!")

    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    if entry.data[CONF_MAC] not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.data[CONF_MAC]] = {
            CONF_PLATFORMS: {p: {} for p in PLATFORMS},
            CONF_ENTITIES: {p: {} for p in PLATFORMS},
        }

    _generate_events = (
        entry.options.get(CONF_GENERATE_EVENTS, False)
    )

    # Migrating the config entry's unique_id if it was not formated to the recommended hass standard
    if entry.unique_id != dr.format_mac(entry.unique_id):
        hass.config_entries.async_update_entry(
            entry, unique_id=dr.format_mac(entry.unique_id)
        )
        LOGGER.warning("Migrating config entry unique_id to %s", entry.unique_id)
        
    entity_registry = er.async_get(hass)
    _mac = entry.data[CONF_MAC]
    
    _domain_to_who = {
        "light": "1",
        "cover": "2",
        "switch": "1",
        "media_player": "16",
    }
    
    registry_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    for reg_entry in registry_entries:
        parts = reg_entry.unique_id.split("-")
        # Old unique_id format: MAC-WHERE
        if len(parts) == 2 and parts[0] == _mac:
            where_part = parts[1]
            who = _domain_to_who.get(reg_entry.domain)
            if who:
                new_unique_id = f"{_mac}-{who}-{where_part}"
                if not entity_registry.async_get_entity_id(reg_entry.domain, DOMAIN, new_unique_id):
                    try:
                        entity_registry.async_update_entity(
                            reg_entry.entity_id, new_unique_id=new_unique_id
                        )
                        reg_entry = entity_registry.async_get(reg_entry.entity_id) # reload
                        LOGGER.info("Resurrecting orphaned MyHOME entity %s to new unique_id %s", reg_entry.entity_id, new_unique_id)
                    except ValueError as e:
                        LOGGER.warning("Could not auto-migrate entity %s to %s: %s", reg_entry.entity_id, new_unique_id, e)

    # Force alignment of entity_ids back to default light.light_69 and cover.cover_18 format!
    # Because a previous buggy implementation overrode _attr_name in the component,
    # HA generated dynamic friendly entity_ids (e.g. light.keuken_tafel).
    # We must revert them to match the dashboard and customize.yaml.
    registry_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    for reg_entry in registry_entries:
        parts = reg_entry.unique_id.split("-")
        if len(parts) >= 3 and parts[0] == _mac:
            where_part = "-".join(parts[2:]) # Handle #4# logic if any
            clean_where = where_part.split("#4#")[0]
            expected_entity_id = f"{reg_entry.domain}.{reg_entry.domain}_{clean_where}"
            if reg_entry.entity_id != expected_entity_id:
                try:
                    entity_registry.async_update_entity(reg_entry.entity_id, new_entity_id=expected_entity_id)
                    LOGGER.info("Restoring Entity ID %s back to %s", reg_entry.entity_id, expected_entity_id)
                except ValueError as e:
                    LOGGER.warning("Could not restore entity %s to %s: %s", reg_entry.entity_id, expected_entity_id, e)

    # Hack to forcefully absorb customize.yaml for users who deleted their integrations
    # and therefore lost the transparent entity_registry migration!
    import os
    from homeassistant.util.yaml.loader import load_yaml
    
    hass.data[DOMAIN]["customizations"] = {}
    customize_file = hass.config.path("customize.yaml")
    if os.path.isfile(customize_file):
        try:
            hass.data[DOMAIN]["customizations"] = load_yaml(customize_file) or {}
            LOGGER.info("Successfully loaded %s custom names from customize.yaml for recovery", len(hass.data[DOMAIN]["customizations"]))
        except Exception as e:
            LOGGER.error("Failed to parse customize.yaml for friendly_name recovery: %s", e)

    gateway = MyHOMEGatewayHandler(
        hass=hass, config_entry=entry, generate_events=_generate_events
    )
    hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY] = gateway

    try:
        tests_results = await gateway.test()
    except (asyncio.TimeoutError, ConnectionError, OSError) as e:
        LOGGER.warning("Gateway connection test failed: %s", e)
        tests_results = None

    if tests_results is None:
        raise ConfigEntryNotReady(
            f"Gateway could not be reached or connection failed at {entry.data[CONF_HOST]}. Home Assistant will natively retry caching."
        )

    if not tests_results.get("Success", False):
        if (
            tests_results.get("Message") == "password_error"
            or tests_results.get("Message") == "password_required"
        ):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_REAUTH},
                    data=entry.data,
                )
            )
        del hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY]
        return False

    _command_worker_count = (
        int(entry.options[CONF_WORKER_COUNT])
        if CONF_WORKER_COUNT in entry.options
        else 1
    )

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    gateway_device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, entry.data[CONF_MAC])},
        identifiers={
            (DOMAIN, hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].unique_id)
        },
        manufacturer=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].manufacturer,
        name=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].name,
        model=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].model,
        sw_version=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].firmware,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ── Register options reload listener (rebuilds decoder pool on UI save) ──
    async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Rebuild the decoder pool when the user saves new options via the UI.

        Releases all active decoder assignments first so that no zone is left
        with a stale claim.  The user will need to re-trigger playback after
        changing decoder config.
        """
        from .decoder_pool import DecoderPool

        mac = entry.data[CONF_MAC]
        old_pool = hass.data.get(DOMAIN, {}).get(mac, {}).get("decoder_pool")
        if old_pool:
            await old_pool.release_all()

        options = entry.options
        decoder_map: dict[str, int] = {}
        pre_gain_map: dict[str, int] = {}
        for i in range(1, CONF_DECODER_SLOTS + 1):
            entity_id = options.get(CONF_DECODER_ENTITY.format(i), "").strip()
            source_num = options.get(CONF_DECODER_SOURCE.format(i), i)
            pre_gain = options.get(CONF_DECODER_PRE_GAIN.format(i), 0)
            if entity_id and entity_id.startswith("media_player."):
                decoder_map[entity_id] = int(source_num)
                pre_gain_map[entity_id] = int(pre_gain)

        pool = DecoderPool(hass, decoder_map, pre_gain_map)
        hass.data[DOMAIN][mac]["decoder_pool"] = pool
        LOGGER.info(
            "MyHOME: decoder pool rebuilt after options update — %d decoder(s) configured",
            len(decoder_map),
        )

        # Signal all media player entities to re-publish supported_features
        # so Music Assistant picks up the new PLAY_MEDIA capability.
        from homeassistant.helpers.dispatcher import async_dispatcher_send
        async_dispatcher_send(hass, f"myhome_pool_updated_{mac}")

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    gateway.listening_worker = entry.async_create_background_task(
        hass, gateway.listening_loop(), name=f"myhome_{entry.entry_id}_listen"
    )
    for i in range(_command_worker_count):
        gateway.sending_workers.append(
            entry.async_create_background_task(
                hass, gateway.sending_loop(i), name=f"myhome_{entry.entry_id}_send_{i}"
            )
        )

    # Static entity pruning has been removed in favor of dynamic discovery.

    # Defining the services
    async def handle_sync_time(call):
        gateway = call.data.get(ATTR_GATEWAY, None)
        if gateway is None:
            _gw_keys = [k for k in hass.data[DOMAIN] if isinstance(k, str) and ":" in k]
            if not _gw_keys:
                LOGGER.error("No MyHOME gateways found, cannot sync time.")
                return False
            gateway = _gw_keys[0]
        else:
            mac = dr.format_mac(gateway)
            if mac is None:
                LOGGER.error(
                    "Invalid gateway mac `%s`, could not send time synchronisation message.",
                    gateway,
                )
                return False
            else:
                gateway = mac
        timezone = hass.config.as_dict()["time_zone"]
        if gateway in hass.data[DOMAIN]:
            await hass.data[DOMAIN][gateway][CONF_ENTITY].send(
                OWNGatewayCommand.set_datetime_to_now(timezone)
            )
        else:
            LOGGER.error(
                "Gateway `%s` not found, could not send time synchronisation message.",
                gateway,
            )
            return False

    hass.services.async_register(DOMAIN, "sync_time", handle_sync_time)

    async def handle_send_message(call):
        gateway = call.data.get(ATTR_GATEWAY, None)
        message = call.data.get(ATTR_MESSAGE, None)
        if gateway is None:
            _gw_keys = [k for k in hass.data[DOMAIN] if isinstance(k, str) and ":" in k]
            if not _gw_keys:
                LOGGER.error("No MyHOME gateways found, cannot send message `%s`.", message)
                return False
            gateway = _gw_keys[0]
        else:
            mac = dr.format_mac(gateway)
            if mac is None:
                LOGGER.error(
                    "Invalid gateway mac `%s`, could not send message `%s`.",
                    gateway,
                    message,
                )
                return False
            else:
                gateway = mac
        LOGGER.debug("Handling message `%s` to be sent to `%s`", message, gateway)
        if gateway in hass.data[DOMAIN]:
            if message is not None:
                own_message = OWNCommand.parse(message)
                if own_message is not None:
                    if own_message.is_valid:
                        LOGGER.debug(
                            "%s Sending valid OpenWebNet Message: `%s`",
                            hass.data[DOMAIN][gateway][CONF_ENTITY].log_id,
                            own_message,
                        )
                        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(own_message)
                else:
                    LOGGER.error(
                        "Could not parse message `%s`, not sending it.", message
                    )
                    return False
        else:
            LOGGER.error(
                "Gateway `%s` not found, could not send message `%s`.", gateway, message
            )
            return False

    hass.services.async_register(DOMAIN, "send_message", handle_send_message)

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""

    LOGGER.info("Unloading MyHome entry.")

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, platform)

    hass.services.async_remove(DOMAIN, "sync_time")
    hass.services.async_remove(DOMAIN, "send_message")

    gateway_handler = hass.data[DOMAIN][entry.data[CONF_MAC]].pop(CONF_ENTITY)
    del hass.data[DOMAIN][entry.data[CONF_MAC]]

    return await gateway_handler.close_listener()
