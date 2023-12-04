# Corsair power supply

## Overview

Based on [corsairmi](https://github.com/notaz/corsairmi)

Gather data from corsair power supply, and dump them in prometheus format.

## Compilation

```
make
```

## Configuration

Suggested, via [prometheus-exporter-exporter](https://github.com/QubitProducts/exporter_exporter)

### on corsair hosts

exporter-expotrer config:
```
## part of /etc/prometheus/exporter-exporter.yml

# exporter-exporter config
modules:
  corsair:
    method: exec
    timeout: 10s
    exec:
      command: /usr/local/lib/prometheus-exporter-exporter/corsairmi.sh
```

wrapper (security: ignore all arguments):
```
## /usr/local/lib/prometheus-exporter-exporter/corsairmi.sh

#! /bin/sh
sudo /usr/local/lib/prometheus-exporter-exporter/corsairmi
```

sudo config:
```
## /etc/sudoers.d/prometheus_corsairmi

prometheus ALL = NOPASSWD: /usr/local/lib/prometheus-exporter-exporter/corsairmi
```

### in prometheus

Prometheus config
```
## part of /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: corsair
    scrape_interval: 1m
    scrape_timeout: 30s
    metrics_path: /proxy
    scheme: http
    params:
      module:
      - corsair
    static_configs:
    - targets:
      # TODO: Configure the server list here
      - corsair-server:9999
      labels:
        rack_id: XXX    # TODO: Configure rack_id here
        in_scope: true  # TODO: Configure here, if in score or not
    relabel_configs:
    # copy target (shortname) as equipment
    - source_labels:
      - __address__
      separator: ;
      regex: ([^.:]*)([.:].*)?
      target_label: equipment
      replacement: ${1}
      action: replace
```
