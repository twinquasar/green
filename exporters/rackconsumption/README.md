# Rackconsumption - Celeste API

## Overview

Gather data from Celeste rackconsumption API.

## Configuration

Suggested, via [prometheus-exporter-exporter](https://github.com/QubitProducts/exporter_exporter)

### on a collector host

exporter-expotrer config:
```
## part of /etc/prometheus/exporter-exporter.yml

# exporter-exporter config
modules:
  rackconsumption:
    method: exec
    timeout: 10s
    exec:
      command: /usr/local/lib/prometheus-exporter-exporter/rackconsumption.sh
```

wrapper (security: ignore all arguments):
```
## /usr/local/lib/prometheus-exporter-exporter/rackconsumption.sh

#! /bin/sh
/usr/local/lib/prometheus-exporter-exporter/rackconsumption.py --config=/etc/prometheus/exporter-exporter-rackconsumption.yml
```

Config for rackconsumption API access, and additional info:
```
## /etc/prometheus/exporter-exporter-rackconsumption.yml
## For mor options, see: ./rackconsumption.py config-sample

token: <api-token>
racks:
  <rackid>: # Rack or room ID
    location: <locationName>
```

### in prometheus

Prometheus config
```
## part of /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: rackconsumption
    scrape_interval: 1m
    scrape_timeout: 30s
    metrics_path: /proxy
    scheme: http
    params:
      module:
      - rackconsumption
    static_configs:
    - targets:
      - localhost:9999  # TODO: Configure if exporter not on localhost
```
