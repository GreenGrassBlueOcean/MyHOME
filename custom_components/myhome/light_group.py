
import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    LightEntity,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event
from OWNd.message import OWNLightingCommand, OWNLightingEvent

from .const import DOMAIN
from .light import _color_modes_from_flags
from .myhome_device import MyHOMEEntity

LOGGER = logging.getLogger(__name__)



class MyHOMELightGroup(MyHOMEEntity, LightEntity):
    """Representation of a MyHOME Lighting Group."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        device_id: str,
        group: int,
        gateway: Any,
        members: list[str],
        dimmable: bool,
        color_temp: bool,
        rgb: bool,
        hs: bool,
        icon: str | None = None,
        icon_on: str | None = None,
    ) -> None:
        """Initialize the group."""
        super().__init__(
            hass=hass,
            name=name,
            platform="light",
            device_id=device_id,
            who="1",
            where=f"#{group}",
            manufacturer="BTicino S.p.A.",
            model="Lighting Group",
            gateway=gateway,
        )
        self._on_icon = icon_on
        self._off_icon = icon
        if icon is not None:
            self._attr_icon = icon
        self._group = group
        self._declared_members = members
        self._member_entity_ids: list[str] = []

        self._attr_assumed_state = not members
        self._attr_supported_color_modes, self._attr_color_mode = _color_modes_from_flags(dimmable, color_temp, rgb, hs)

        self._attr_extra_state_attributes = {
            "group": group,
            "members": members,
        }

        self._attr_is_on = False
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None
        self._attr_hs_color = None
        self._full_where = f"#{group}"

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()

        # Subscribe to group messages directly from the gateway bus
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"myhome_message_{self._gateway_handler.mac}",
                self._handle_bus_message,
            )
        )

        # Resolve members if any
        if self._declared_members:
            registry = er.async_get(self.hass)
            for w in self._declared_members:
                # The entity unique_id is `{mac}-1-{w}`
                unique_id = f"{self._gateway_handler.mac}-1-{w}"
                entity_id = registry.async_get_entity_id("light", DOMAIN, unique_id)
                if entity_id:
                    self._member_entity_ids.append(entity_id)
                else:
                    LOGGER.warning("Group %s could not resolve member WHERE %s (unique_id: %s)", self._full_where, w, unique_id)

            if self._member_entity_ids:
                self.async_on_remove(
                    async_track_state_change_event(
                        self.hass, self._member_entity_ids, self._async_member_changed
                    )
                )
                self._update_from_members()

    @callback
    def _handle_bus_message(self, msg: Any) -> None:
        """Handle group messages from the bus."""
        if getattr(msg, "who", None) != 1 or getattr(msg, "is_translation", False):
            return

        if not getattr(msg, "is_group", False) or str(getattr(msg, "group", "")) != str(self._group):
            return

        # Parse status from the frame (assumed mode only updates attributes, member mode ignores them)
        if isinstance(msg, OWNLightingEvent) and getattr(msg, "dimension", None) is None:
            if msg.is_on:
                self._attr_is_on = True
            elif msg.is_off:
                self._attr_is_on = False

        # Also parse dimension frames
        dim = getattr(msg, "dimension", None)
        vals = getattr(msg, "_dimension_value", [])
        if dim == 1 and vals:
            self._attr_brightness = int((int(vals[0]) / 100) * 255)
        elif dim == 14 and vals:
            self._attr_color_temp_kelvin = int(1000000 / int(vals[0]))
        elif dim == 12 and len(vals) >= 3:
            h = int(vals[0])
            s = int(vals[1])
            self._attr_hs_color = (h, s)

        if self._on_icon and self._off_icon:
                self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self.async_write_ha_state()

    @callback
    def _async_member_changed(self, event: Event) -> None:
        """Update state from members."""
        self._update_from_members()
        if self._on_icon and self._off_icon:
                self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        if not self._member_entity_ids:
            return super().available
        return super().available and getattr(self, "_attr_available", True)

    @callback
    def _update_from_members(self) -> None:
        """Calculate mean values from members."""
        if not self._member_entity_ids:
            return

        states = [
            self.hass.states.get(entity_id)
            for entity_id in self._member_entity_ids
        ]
        states = [s for s in states if s is not None]

        self._attr_available = any(s.state != "unavailable" for s in states)
        if not states:
            return

        self._attr_is_on = any(s.state == "on" for s in states)

        if self._attr_is_on:
            brightnesses = [s.attributes.get(ATTR_BRIGHTNESS) for s in states if s.state == "on" and s.attributes.get(ATTR_BRIGHTNESS) is not None]
            if brightnesses:
                self._attr_brightness = sum(brightnesses) / len(brightnesses)
            else:
                self._attr_brightness = None

            color_temps = [s.attributes.get(ATTR_COLOR_TEMP_KELVIN) for s in states if s.state == "on" and s.attributes.get(ATTR_COLOR_TEMP_KELVIN) is not None]
            if color_temps:
                self._attr_color_temp_kelvin = sum(color_temps) / len(color_temps)
            else:
                self._attr_color_temp_kelvin = None

            hs_colors = [s.attributes.get(ATTR_HS_COLOR) for s in states if s.state == "on" and s.attributes.get(ATTR_HS_COLOR) is not None]
            if hs_colors:
                # Naive average for hs colors
                h = sum(c[0] for c in hs_colors) / len(hs_colors)
                s = sum(c[1] for c in hs_colors) / len(hs_colors)
                self._attr_hs_color = (h, s)
            else:
                self._attr_hs_color = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the group on."""
        if "transition" in kwargs:
            raise HomeAssistantError("Group does not support software transition")

        cmd = None
        if ATTR_BRIGHTNESS in kwargs:
            level = int((kwargs[ATTR_BRIGHTNESS] / 255) * 100)
            cmd = OWNLightingCommand.set_brightness(self._full_where, level)
            if not self._member_entity_ids:
                self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
                self._attr_is_on = True
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            mired = int(1000000 / kwargs[ATTR_COLOR_TEMP_KELVIN])
            cmd = OWNLightingCommand.set_color_temperature(self._full_where, mired)
            if not self._member_entity_ids:
                self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                self._attr_is_on = True
        elif ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            cmd = OWNLightingCommand.set_hsv_color(self._full_where, int(h), int(s), 100)
            if not self._member_entity_ids:
                self._attr_hs_color = (h, s)
                self._attr_is_on = True
        else:
            cmd = OWNLightingCommand.switch_on(self._full_where)
            if not self._member_entity_ids:
                self._attr_is_on = True

        if cmd:
            await self._gateway_handler.send_command(cmd)
            if self._on_icon and self._off_icon:
                self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the group off."""
        await self._gateway_handler.send_command(OWNLightingCommand.switch_off(self._full_where))
        if not self._member_entity_ids:
            self._attr_is_on = False
            if self._on_icon and self._off_icon:
                self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state."""
        if self._member_entity_ids:
            return
        await self._gateway_handler.send_status_request(OWNLightingCommand.status(self._full_where))
        if "brightness" in self.supported_color_modes:
            await self._gateway_handler.send_status_request(OWNLightingCommand.get_brightness(self._full_where))
        if "color_temp" in self.supported_color_modes:
            await self._gateway_handler.send_status_request(OWNLightingCommand.get_color_temperature(self._full_where))
        if "hs" in self.supported_color_modes:
            await self._gateway_handler.send_status_request(OWNLightingCommand.get_hsv_color(self._full_where))
