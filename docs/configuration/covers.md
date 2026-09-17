The configuration remains similar to lights and switches.  
The specificity is the optional `advanced` boolean (defaulting to `False`), you need to set it to `True` if you have 'advanced' cover modules that keep track of and return position values. (Only "Céliane 67557", "Axolute H4661M2", "Livinglight LN4661M2" and the "F401" DIN module are capable of this)

# Configuration example

```yaml
  cover:
    living_shutter:
      where: '11'
      name: Living room shutter
      advanced: True
      manufacturer: Legrand
      model: 67557
    kitchen_shutter:
      where: '12'
      interface: '03'
      name: Kitchen shutter
      advanced: True
      manufacturer: Legrand
      model: 67557
    dining_room_shutter:
      where: '13'
      name: Dining room shutter
      advanced: True
      manufacturer: Legrand
      model: 67557
```

# Timed covers (v2)

Covers with `advanced: False` have no position feedback. From v2 the integration estimates position from `travel_time` (seconds for a full run, default `25`) and exposes `set_cover_position` on them.

```yaml
  cover:
    bedroom_shutter:
      where: '21'
      name: Bedroom shutter
      travel_time: 18
```

What the estimate is based on (measured on a MyHOMeServer1, [#302](https://github.com/OpenWebNet-HA/MyHOME/issues/302)):

- The clock starts when the direction frame is **written to the gateway**, not when Home Assistant queues it — with several covers commanded together the last frame can leave more than a second later.
- After the write the gateway relays a stop status (~0.1 s), the translation, and the real direction status when the motor starts (~0.55 s). These are echoes of our own command: the stop does not end the run, and the direction status re-anchors the clock to the actual motor start.
- `set_cover_position` times its run from that anchor; a stop is applied to the estimate when the stop frame is written.
- A wall-switch or scenario command in the opposite direction, or any command after the motor has started, is handled normally.

Full description: [Runtime Behaviour Notes ↗](https://github.com/OpenWebNet-HA/MyHOME/blob/v2-phase1-architecture/docs/configuration/runtime_behaviour.md#-timed-covers-clock-starts-at-the-write-echoes-are-not-keypad-presses).
