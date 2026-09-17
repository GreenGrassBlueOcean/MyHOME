There are 3 types of binary sensors that are supported

# Dry contacts

Here are the 3 configuration items you need to pay attention to:

* `who` is optional, but if you set it, it must be `25` for the dry contacts. If you don't set it, the configuration validator will set it to 25 by default in the background.
* `where` for these is one of a few special cases, as per specification, they are always "3" followed by the sensor number assigned "[1-201]".  
* `class` allows you to specify any supported Home-Assistant binary sensor `device_class`, this will affect the way the device is presented in the interface. It is highly recommended to set it!

## Configuration example

```yaml
  binary_sensor:
    garage_door:
      where: '31'
      name: Garage door
      class: garage_door
      manufacturer: BTicino
      model: 3477
```

# Motion sensors

The "motion" part of the light and motion sensors on WHO 1 are available if the sensor is configured in "scenario" mode.  
`who` **must** be "1" for these sensors.  
`class` **must** be "motion" for these sensors.

## Configuration example

```yaml
  binary_sensor:
    office_motion:
      who: '1'
      where: '0312'
      name: Office
      class: motion
      manufacturer: Legrand
      model: 048822
```

# Auxiliary sensors
Auxiliary sensors from the alarm system can also be added.  
`where` is the auxiliary sensor number "[0-9]".  
`who` must be "9" in the case of Auxiliary sensors.  
`class` allows you to specify any supported Home-Assistant binary sensor `device_class`, this will affect the way the device is presented in the interface.  It is highly recommended to set it!

## Configuration example

```yaml
  binary_sensor:
    motion_sensor:
      where: '1'
      who: '9'
      name: Motion living room
      class: motion
      manufacturer: BTicino
      model: L4610
```

# Device classes

Here is the list of device class strings used by Home Assistant for reference:

```python
class BinarySensorDeviceClass(StrEnum):
    """Device class for binary sensors."""

    # On means low, Off means normal
    BATTERY = "battery"

    # On means charging, Off means not charging
    BATTERY_CHARGING = "battery_charging"

    # On means carbon monoxide detected, Off means no carbon monoxide (clear)
    CO = "carbon_monoxide"

    # On means cold, Off means normal
    COLD = "cold"

    # On means connected, Off means disconnected
    CONNECTIVITY = "connectivity"

    # On means open, Off means closed
    DOOR = "door"

    # On means open, Off means closed
    GARAGE_DOOR = "garage_door"

    # On means gas detected, Off means no gas (clear)
    GAS = "gas"

    # On means hot, Off means normal
    HEAT = "heat"

    # On means light detected, Off means no light
    LIGHT = "light"

    # On means open (unlocked), Off means closed (locked)
    LOCK = "lock"

    # On means wet, Off means dry
    MOISTURE = "moisture"

    # On means motion detected, Off means no motion (clear)
    MOTION = "motion"

    # On means moving, Off means not moving (stopped)
    MOVING = "moving"

    # On means occupied, Off means not occupied (clear)
    OCCUPANCY = "occupancy"

    # On means open, Off means closed
    OPENING = "opening"

    # On means plugged in, Off means unplugged
    PLUG = "plug"

    # On means power detected, Off means no power
    POWER = "power"

    # On means home, Off means away
    PRESENCE = "presence"

    # On means problem detected, Off means no problem (OK)
    PROBLEM = "problem"

    # On means running, Off means not running
    RUNNING = "running"

    # On means unsafe, Off means safe
    SAFETY = "safety"

    # On means smoke detected, Off means no smoke (clear)
    SMOKE = "smoke"

    # On means sound detected, Off means no sound (clear)
    SOUND = "sound"

    # On means tampering detected, Off means no tampering (clear)
    TAMPER = "tamper"

    # On means update available, Off means up-to-date
    UPDATE = "update"

    # On means vibration detected, Off means no vibration
    VIBRATION = "vibration"

    # On means open, Off means closed
    WINDOW = "window"
```