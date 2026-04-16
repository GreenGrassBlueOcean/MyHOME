"""Support for common values for MyHome devices."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gateway import MyHOMEGatewayHandler

from homeassistant.helpers.entity import Entity
from homeassistant.const import CONF_ENTITIES


from .const import DOMAIN, CONF_PLATFORMS, CONF_ENTITIES


class MyHOMEEntity(Entity):
    def __init__(
        self,
        hass,
        name: str,
        platform: str,
        device_id: str,
        who: str,
        where: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        self._hass = hass
        self._platform = platform
        self._who = who
        self._where = where
        self._device_id = device_id
        self._attr_unique_id = f"{gateway.mac}-{self._who}-{self._device_id}"
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._gateway_handler = gateway
        self._attr_has_entity_name = False
        
        # Pull from customize.yaml dynamically
        _customs = self._hass.data.get(DOMAIN, {}).get("customizations", {})
        _predicted_id = f"{platform.lower()}.{name.lower().replace(' ', '_')}"
        self._attr_name = _customs.get(_predicted_id, {}).get("friendly_name", name)
        
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{gateway.mac}-{self._who}-{self._device_id}")},
            "name": self._attr_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway_handler.unique_id),
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        pass
