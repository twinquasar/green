# IPMI - power consumption

## Overview

Gather data from servers supporting IPMI

## Configuration

Suggested, via [prometheus-ipmi-exporter](https://github.com/soundcloud/ipmi_exporter)

### on a collector host

ipmi-expotrer config:
```
## part of /etc/prometheus/ipmi_monitoring.yml
modules:
  power:
    # XXX: update credentials accordingly
    # User seems to need admin rights to be able to collect power info
    user: monitoring
    pass: S3cr3tCr3d3nt1als
    driver: "LAN_2_0"
    # Note: user seems not to be enough for dcmi - power info - need admin
    #privilege: "user"

    timeout: 10000
    # We only need dcmi to get power info
    collectors:
    - dcmi
```

And tell ipmi exporter to use that configuration file:
```
# /etc/default/prometheus-ipmi-exporter 
ARGS="--config.file=/etc/prometheus/ipmi_monitoring.yml"
```


### in prometheus

Prometheus config
```
## part of /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: ipmi
    scrape_interval: 1m
    scrape_timeout: 30s
    metrics_path: /ipmi
    scheme: http
    params:
      module:
      - remote
    static_configs:
    - targets:
      # TODO: Configure the server IPMI addresses here
      - server-ipmi
      labels:
        rack_id: XXX    # TODO: Configure rack_id here
        in_scope: true  # TODO: Configure here, if in score or not
    relabel_configs:
    # target as param
    - source_labels:
      - __address__
      separator: ;
      regex: (.*)
      target_label: __param_target
      replacement: ${1}
      action: replace
    # target is also the instance name
    - source_labels:
      - __address__
      separator: ;
      regex: (.*)
      target_label: instance
      replacement: ${1}
      action: replace
    # call it on localhost exporter
    - separator: ;
      regex: .*
      target_label: __address__
      replacement: localhost:9290
      action: replace
    # copy instance shortname as equipment, then remove the -ipmi suffix if present
    - source_labels:
      - instance
      separator: ;
      regex: ([^.]*)(\..*)?
      target_label: equipment
      replacement: ${1}
      action: replace
    - source_labels:
      - equipment
      separator: ;
      regex: (.*)-ipmi
      target_label: equipment
      replacement: ${1}
      action: replace
    # Rename metric to have green power data
    metric_relabel_configs:
    - source_labels:
      - __name__
      regex: ipmi_dcmi_power_consumption_watts
      target_label: __name__
      replacement: ipmi_green_equipment_power_consumption_va
      action: replace
```
