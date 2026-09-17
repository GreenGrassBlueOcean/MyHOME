The configuration is largely the same as lights, except here they cannot be dimmable, and you can specify the `class` if you wish to distinguish between `outlet` and `switch`.

# Configuration example

```yaml
  switch:
    bed_heater:
      where: '0211'
      name: Mattress heating pad
      class: outlet
      manufacturer: BTicino
      model: F411U2
    door_bell:
      where: '0515'
      interface: '02'
      name: Doorbell
      class: switch
      manufacturer: BTicino
      model: 3476
    hvac_relay_1:
      where: '08'
      name: HVAC relay 1
      class: switch
      manufacturer: Arnould
      model: 64391
```