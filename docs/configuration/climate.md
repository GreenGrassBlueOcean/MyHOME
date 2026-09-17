Climate entities are developed for WHO 4

There are 3 distinct ways to configure this part depending on your setup.

# 99 zones central unit

In a 99 zones setup, the central unit needs to have the address `#0`, and all subordinate zones have their own number with and are NOT `standalone`.  
`zone` is the zone (equivalent to `where`)  
`heat` is an optional boolean defaulting to `True` you can set if your installation supports heating  
`cool` is an optional boolean defaulting to `False` you can set if your installation supports cooling  
`standalone` is an optional boolean defaulting to `False`, you can either ignore it or set it manually to `False` when you have a 99 zones setup

## Configuration example

```yaml
  climate:
    central_unit:
      zone: '#0'
      name: Central unit
      heat: True
      cool: False
      standalone: False
      manufacturer: BTicino
      model: 3550
    zone_1:
      zone: '1'
      name: Living room
      heat: True
      cool: False
      standalone: False
      manufacturer: BTicino
      model: F430/4
```

# 4 zones central unit

When you use a 4 zones central unit, the central unit itself acts as a separate zone, so it has a zone number configured; all subordinate zones are `standalone`.  
`zone` is the zone (equivalent to `where`)  
`heat` is an optional boolean defaulting to `True` you can set if your installation supports heating  
`cool` is an optional boolean defaulting to `False` you can set if your installation supports cooling  
`central`is an optional boolean defaulting to`False` that you need to set to `True` only for the zone that acts as the central unit in your 4 zones setup    
`standalone` is an optional boolean defaulting to `False` that you need to set to `True` for all subordinate zones in a 4 zones setup

## Configuration example

```yaml
  climate:
    central_unit:
      zone: '1'
      name: Central unit Living room
      heat: True
      cool: False
      central: True
      standalone: False
      manufacturer: BTicino
      model: HC4695
    zone_2:
      zone: '2'
      name: Bedroom
      heat: True
      cool: False
      standalone: True
      manufacturer: BTicino
      model: F430/4
```

# No central unit

With no central unit, all zones are set as `standalone`.  
`zone` is the zone (equivalent to `where`)  
`heat` is an optional boolean defaulting to `True` you can set if your installation supports heating  
`cool` is an optional boolean defaulting to `False` you can set if your installation supports cooling  
`standalone` is an optional boolean defaulting to `False` that you need to set to `True` for all zones when you don't have any central unit

## Configuration example

```yaml
  climate:
    zone_1:
      zone: '1'
      name: Living room
      heat: True
      cool: False
      standalone: True
      manufacturer: BTicino
      model: H4691
    zone_2:
      zone: '2'
      name: Bedroom
      heat: True
      cool: False
      standalone: True
      manufacturer: BTicino
      model: H4691
```