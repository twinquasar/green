# Green Power Consumption

This projects aim at being able have tools to graph:
* power production
* power consumption per equipment
* be able to match the power consumption per sector during its lifespan

## Individual power consupmiton scrappers : 

- [x] [ipmi on servers](exporters/ipmi/)
- [x] [corsair power supply](exporters/corsair/)
- [x] [jbod data60-redfish](exporters/data60-redfish/)

### Metrics format 

Metrics:
```
green_equipment_power_consumption_va{equipment="EQUIPMENTNAME", rack_id, in_scope="(true|false)"}
```

Labels:
- `equipment`: short hostname (no fqdn)
- `rack_id`: statically configured in prometheus configuration. Used to aggregate by rack

## Rack and solar panel

- [x] [rackconsumption](exporters/rackconsumption/)
- [ ] solar panels

###  metrics

Metrics:
```	
green_rack_power_consumption_va{rack_id, location_name, client_name}
green_solar_panel_power_production_va{location_name}
```

Labels:
- `rack_id`: must match equipments rack IDs
- `location_name`: used to matchs racks consumption and panel power production
- `client_name`: Client name if available

## Lotus

See [lotus-farcaster](https://github.com/s0nik42/lotus-farcaster)

- [x] miner
- [x] workers
- [x] storage

### Metrics
```
green_sector_resource(miner_id, sector_id, equipment="miner") 1
green_sector_resource(miner_id, sector_id, equipment="data-60-1") 1
green_sector_resource(miner_id, sector_id, equipment="firewall") 1
green_sector_resource(miner_id, sector_id, equipment="switchs") 1
green_sector_resource(miner_id, sector_id, equipment="worker-1") 1
green_sector_resource(miner_id, sector_id, equipment="data60-01" sector_file_type="(sealed|unsealed)") 1
```
