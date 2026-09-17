There are 3 types of sensors that are available

# Power and energy sensors

* `who` is optional but must be `18` should you want to set it.
* `where` is a special case for those since power meters are always "5" followed by the sensor number assigned "[1-255]" for F520, the address should always be "7" followed by the sensor number assigned "[1-255]" for F522.  
* `class` is a required item that can be either `power` or `energy`

There is a subtle difference between setting the class to `power` and `energy.  
Setting it to `power` will create an entity displaying currently used power (in Watts) live as well as 3 entities displaying the energy (in Watt Hours). (one entity for the total energy of the counter, one for daily and one for monthly, the latter 2 are disabled by default)  
Setting it to `energy` will provide the same energy entities but not the live power (if that is something you're not interested in)

## Configuration example

```yaml
  sensor:
    general_power:
      where: '51'
      name: Total power
      class: power
      manufacturer: BTicino
      model: F520
    water_heater_power:
      where: '52'
      name: Water heater
      class: power
      manufacturer: BTicino
      model: F520
    washing_machine:
      where: '71'
      name: Washing machine
      class: power
      manufacturer: BTicino
      model: F522
```

# Temperature sensors

* `who` is optional but must be `4` should you want to set it.
* `where` is the address of the sensor. You can add secondary temperature sensors (with 3 digits as per OpenWebNet documentation, ie `105` is the 1st 'secondary sensor' of the 5th zone) or main temperature sensor (with 1 or 2 digit being the Zone number).
* `class` must be `temperature`. 

> **v2 behaviour for secondary sensors (`where` ≥ 100):** these probes push their readings on the bus (e.g. a 3455 behind an L4577 radio interface reports every few seconds) and reject explicit polls. The entity therefore starts receive-only and only sends a request if no reading arrived within the last 5 minutes. Zone sensors (1- or 2-digit `where`) are polled as before. ([#308](https://github.com/OpenWebNet-HA/MyHOME/issues/308))

## Configuration example

```yaml
  sensor:
    bedroom_temperature:
      where: '1'
      name: Bedroom temperature
      class: temperature
      manufacturer: BTicino
      model: L4692
    temperature_sensor:
      where: '105'
      name: Secondary sensor
      class: temperature
      manufacturer: BTicino
      model: L4692
```

# Illuminance sensors

* `who` is optional but must be `1` should you want to set it.
* `class` must be `illuminance` 

Illuminance sensors are only available if the sensor itself is configured in "scenario" mode, this is similar to the requirement of the "motion" binary sensor.

## Configuration example

```yaml
  sensor:
    office_illuminance:
      where: '0312'
      name: Office
      class: illuminance
      manufacturer: Legrand
      model: 048822
```