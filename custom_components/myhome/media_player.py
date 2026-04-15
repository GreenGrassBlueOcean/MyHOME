"""Support for MyHome audio zones."""
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    DOMAIN as PLATFORM,
)

from homeassistant.const import CONF_MAC
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .ownd.message import (
    OWNSoundEvent,
    OWNSoundCommand,
)

from .const import (
    CONF_ENTITY,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the MyHOME media player platform dynamically via Discovery."""
    known_media_players = set()

    # Restore previously discovered entities from the Entity Registry so they
    # are available immediately on restart, even before the gateway responds.
    entity_registry = er.async_get(hass)
    existing_entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    restored_players = []

    gateway = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY]

    for entry in existing_entries:
        if entry.domain == PLATFORM:
            unique_id = entry.unique_id
            # unique_id format: "{mac}-{zone}#16"
            device_id = unique_id.replace(f"{config_entry.data[CONF_MAC]}-", "", 1)
            # device_id is "{zone}#16"
            zone = device_id.replace("#16", "")

            _player = MyHOMEMediaPlayer(
                hass=hass,
                name=f"Audio Zone {zone}",
                entity_name=None,
                device_id=device_id,
                who="16",
                where=zone,
                manufacturer="BTicino",
                model="Audio System",
                gateway=gateway,
            )
            known_media_players.add(device_id)
            restored_players.append(_player)

    if restored_players:
        async_add_entities(restored_players)

    @callback
    def async_add_media_player(message):
        """Add a media player from a discovered message."""
        if not hasattr(message, "zone") or not message.zone:
            return

        zone = message.zone
        unique_id = f"{zone}#16"

        if unique_id not in known_media_players:
            _player = MyHOMEMediaPlayer(
                hass=hass,
                name=f"Audio Zone {zone}",
                entity_name=None,
                device_id=unique_id,
                who=str(message.who),
                where=zone,
                manufacturer="BTicino",
                model="Audio System",
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            known_media_players.add(unique_id)
            async_add_entities([_player])
            _player.handle_event(message)

        async_dispatcher_send(hass, f"myhome_update_{config_entry.data[CONF_MAC]}_{unique_id}", message)

    @callback
    def _handle_media_player_message(msg):
        """Filter and forward media player messages."""
        if isinstance(msg, OWNSoundEvent):
            async_add_media_player(msg)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"myhome_message_{config_entry.data[CONF_MAC]}",
            _handle_media_player_message,
        )
    )

async def async_unload_entry(hass, config_entry):
    """Unload media player platform."""
    return True


class MyHOMEMediaPlayer(MyHOMEEntity, MediaPlayerEntity):
    """MyHome media player."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        manufacturer: str,
        model: str,
        gateway,
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._attr_name = entity_name
        self._attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
        )
        
        self._attr_state = MediaPlayerState.OFF
        self._attr_source_list = ["Source 1", "Source 2", "Source 3", "Source 4"]
        self._attr_source = None

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"myhome_update_{self._gateway_handler.mac}_{self.unique_id}",
                self.handle_event,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"myhome_message_{self._gateway_handler.mac}",
                self.handle_global_source_event,
            )
        )

    def handle_global_source_event(self, message):
        """Intercept global source change events to update UI."""
        if isinstance(message, OWNSoundEvent) and message.is_source_event:
            if message.is_on:
                self._attr_source = f"Source {message.source_id}"
                self.async_schedule_update_ha_state()

    async def async_update(self):
        """Update the entity."""
        await self._gateway_handler.send_status_request(OWNSoundCommand.status(self._where))

    async def async_turn_on(self, **kwargs):
        """Turn the media player on."""
        await self._gateway_handler.send(OWNSoundCommand.turn_on(self._where))

    async def async_turn_off(self, **kwargs):
        """Turn the media player off."""
        await self._gateway_handler.send(OWNSoundCommand.turn_off(self._where))

    async def async_volume_up(self):
        """Volume up."""
        await self._gateway_handler.send(OWNSoundCommand.volume_up(self._where))

    async def async_volume_down(self):
        """Volume down."""
        await self._gateway_handler.send(OWNSoundCommand.volume_down(self._where))

    async def async_select_source(self, source: str):
        """Select input source."""
        if source in self._attr_source_list:
            source_id = source.split(" ")[1]
            await self._gateway_handler.send(OWNSoundCommand.select_source(source_id))

    def handle_event(self, message: OWNSoundEvent):
        """Handle an event message."""
        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        if message.is_on:
            self._attr_state = MediaPlayerState.ON
        else:
            self._attr_state = MediaPlayerState.OFF

        self.async_schedule_update_ha_state()
