"""Support for MyHome covers."""
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as PLATFORM,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)

from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .ownd.message import (
    OWNAutomationEvent,
    OWNAutomationCommand,
)

from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_WHO,
    CONF_WHERE,
    CONF_BUS_INTERFACE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_ADVANCED_SHUTTER,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the MyHOME cover platform dynamically via Discovery."""
    known_covers = set()

    # Restore previously discovered entities from the Entity Registry so they
    # are available immediately on restart, even before the gateway responds.
    entity_registry = er.async_get(hass)
    existing_entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    restored_covers = []

    gateway = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY]

    for entry in existing_entries:
        if entry.domain == PLATFORM:
            unique_id = entry.unique_id
            # unique_id format: "{mac}-{device_id}", device_id is "{where}" or "{where}#4#{interface}"
            device_id = unique_id.replace(f"{config_entry.data[CONF_MAC]}-", "", 1)
            if "#4#" in device_id:
                parts = device_id.split("#4#")
                where = parts[0]
                interface = parts[1] if len(parts) > 1 else None
            else:
                where = device_id
                interface = None

            _cover = MyHOMECover(
                hass=hass,
                name=f"Cover {where}",
                entity_name=None,
                device_id=device_id,
                who="2",
                where=where,
                interface=interface,
                advanced=False,
                manufacturer="BTicino",
                model="Shutter / Cover",
                gateway=gateway,
            )
            known_covers.add(device_id)
            restored_covers.append(_cover)

    if restored_covers:
        async_add_entities(restored_covers)

    @callback
    def async_add_cover(message):
        """Add a cover from a discovered message."""
        if not hasattr(message, "where") or not message.where:
            return

        # Skip groups, areas and general for now, as they represent many physical devices
        if getattr(message, "is_group", False) or getattr(message, "is_area", False) or getattr(message, "is_general", False):
            return

        where = message.where
        interface = getattr(message, "interface", None)
        unique_id = f"{where}#4#{interface}" if interface else str(where)

        if unique_id not in known_covers:
            # We found a new cover!
            _cover = MyHOMECover(
                hass=hass,
                name=f"Cover {where}",
                entity_name=None,
                device_id=unique_id,
                who=str(message.who),
                where=where,
                interface=interface,
                advanced=False,  # Can be handled by OptionsFlow overrides later
                manufacturer="BTicino",
                model="Shutter / Cover",
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            known_covers.add(unique_id)
            async_add_entities([_cover])
            _cover.handle_event(message)
            
        async_dispatcher_send(hass, f"myhome_update_{config_entry.data[CONF_MAC]}_2_{unique_id}", message)

    @callback
    def _handle_cover_message(msg):
        """Filter and forward cover messages."""
        if isinstance(msg, OWNAutomationEvent):
            async_add_cover(msg)

    # Listen to all incoming gateway messages
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"myhome_message_{config_entry.data[CONF_MAC]}",
            _handle_cover_message,
        )
    )

async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    """Unload cover platform."""
    return True


class MyHOMECover(MyHOMEEntity, CoverEntity):
    device_class = CoverDeviceClass.SHUTTER

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        advanced: bool,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
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

        self._interface = interface
        self._full_where = f"{self._where}#4#{self._interface}" if self._interface is not None else self._where

        self._attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if advanced:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION
        self._gateway_handler = gateway

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }
        if self._interface is not None:
            self._attr_extra_state_attributes["Int"] = self._interface

        self._attr_current_cover_position = None
        self._attr_is_opening = None
        self._attr_is_closing = None
        self._attr_is_closed = None

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"myhome_update_{self._gateway_handler.mac}_2_{self._full_where}",
                self.handle_event,
            )
        )

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(OWNAutomationCommand.status(self._full_where))

    async def async_open_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Open the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.raise_shutter(self._full_where))

    async def async_close_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Close cover."""
        await self._gateway_handler.send(OWNAutomationCommand.lower_shutter(self._full_where))

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self._gateway_handler.send(OWNAutomationCommand.set_shutter_level(self._full_where, position))

    async def async_stop_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Stop the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._full_where))

    @callback
    def handle_event(self, message: OWNAutomationEvent):
        """Handle an event message."""
        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        self._attr_is_opening = message.is_opening
        self._attr_is_closing = message.is_closing
        if message.is_closed is not None:
            self._attr_is_closed = message.is_closed
        if message.current_position is not None:
            self._attr_current_cover_position = message.current_position

        self.async_schedule_update_ha_state()
