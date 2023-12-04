# data60 JBOD - redfish API

## Overview

Gather data from redfish api on data60 JBOD.

## Configuration

Suggested, via [prometheus-exporter-exporter](https://github.com/QubitProducts/exporter_exporter)

### on a collector host

exporter-expotrer config:
```
## part of /etc/prometheus/exporter-exporter.yml

# exporter-exporter config
modules:
  redfish:
    method: exec
    timeout: 10s
    exec:
      command: /usr/local/lib/prometheus-exporter-exporter/data60-redfish-exporter.sh
```

wrapper (security: ensure exactly 1 argument, not starting with a dash):
```
## /usr/local/lib/prometheus-exporter-exporter/data60-redfish-exporter.sh

#! /bin/sh
# Check single arguments, not starting with a dash
case "$#-$1" in
  1--*) : ;;
  1-*) /usr/local/lib/prometheus-exporter-exporter/data60-redfish-exporter.py --config=/etc/prometheus/exporter-exporter-data60-redfish.yml "$1" ;;
esac
```

Config for data60 accesses:
```
# /etc/prometheus/exporter-exporter-data60-redfish.yml
devices:
  data60-name:      # Name of the device
    ips:            # IPs of the data60 management interfaces
    - 192.168.1.10
    - 192.168.1.11
    user: admin     # Credentials
    pass: xxx
```


### in prometheus

Prometheus config
```
## part of /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: redfish-data60
    scrape_interval: 1m
    scrape_timeout: 30s
    metrics_path: /proxy
    scheme: http
    params:
      module:
      - redfish

    static_configs:
    - targets:
      # TODO: Configure the data60 list here (must be present in previous config)
      - data60-1
      labels:
        rack_id: XXX    # TODO: Configure rack_id here
        in_scope: true  # TODO: Configure here, if in score or not
    relabel_configs:
    # target as param
    - source_labels:
      - __address__
      separator: ;
      regex: (.*)(:80)?
      target_label: __param_args
      replacement: ${1}
      action: replace
    # target is also the instance name
    - source_labels:
      - __param_args
      separator: ;
      regex: (.*)
      target_label: instance
      replacement: ${1}
      action: replace
    # call it on localhost exporter
    - separator: ;
      regex: .*
      target_label: __address__
      replacement: localhost:9999  # TODO: Configure if exporter not on localhost
      action: replace
    # copy instance (shortname) as equipment
    - source_labels:
      - instance
      separator: ;
      regex: ([^.]*)(\..*)?
      target_label: equipment
      replacement: ${1}
      action: replace
```
