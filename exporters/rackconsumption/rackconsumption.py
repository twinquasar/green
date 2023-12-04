#! /usr/bin/env python3
"""
Generate prometheus stats from Celeste power consumption API

Usage:
    rackconsumption.py [-d] -c <config> [-o <outputfile>]
    rackconsumption.py --loop [-s] [-t=<timer>] [-d] -o <outputfile> -c <config>
    rackconsumption.py config-sample

Options:
    -c,--config=<config>  Configu9ration file
    -o,--output=<output>  Output file
    -d,--debug            Debug mode
    -l,--loop             Loop over and over
    -s,--systemd          Logs go to systemd, do not add timestamp
    -t,--timer=<timer>    Delay between loop starts in seconds [Default: 30]
"""

import os
import sys
import yaml
import json
import time
import http.client
import logging
import docopt

log = logging.getLogger(__name__)
_NAME = "rackconsumption"

_GREEN_LABEL = "green_rack_power_consumption_va"
_PROMETHEUS_PREFIX = "rackconsumption"
_FIELDS_INFO = {
    "current": {
        "label": "current",
        "help": "Rack current used (in A)",
    },
    "power": {
        "label": "power",
        "help": "Rack power used (in W)",
    },
    "consumption": {
        "label": "va",
        "help": "Rack consumption (in VA)",
    },
    "green": {
        "label": _GREEN_LABEL,
        "help": "Rack consumption (in VA)",
        "field": "consumption",
    },
}

_API = {
    "host": "api.celeste.fr",
    "url": "/v1/PacketPower/getConsomation",
}

_CONFIG_SAMPLE = """
token: <api-token>  # Required
racks:
  <rackid>:  # Rack or room id
    location: <locationName> # Required

    # To override, and not just take global client name
    client: <clientName>

# prefix used for output data names
prometheus_prefix: rackconsumption
api:
  # default values, only needed if you want to override them
  host: api.celeste.fr
  url: /v1/PacketPower/getConsomation
"""
_CONFIG_REQ = """
token: <api-token>
racks:
  <rackid>: # Rack or room ID
    location: <locationName>
"""


_TERM_COLORS = {
    "debug": "\033[90m",  # grey
    "info": "\033[32m",  # green
    "warning": "\033[33m",  # yellow
    "error": "\033[31m",  # red
    None: "\033[0m",  # end color
}


class CustomFormatter(logging.Formatter):
    """
    CustomFormatter

    Insert terminal color-code in logformat. To use if output isatty.
    """

    red = "\x1b[31;20m"
    green = "\x1b[32;20m"
    dblue = "\x1b[34;20m"
    grey = "\x1b[37;20m"
    purple = "\x1b[35;20m"
    lblue = "\x1b[36;20m"
    white = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    _DEFAULT_COLORS = {
        logging.DEBUG: grey,
        logging.INFO: lblue,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red,
    }

    def __init__(self, fmt=None, *args, colors=None, **kwargs):
        self._fmt = fmt
        self._colors = colors or self._DEFAULT_COLORS
        self._formatters = {}
        # super().__init__(fmt=fmt, *args, **kwargs)

    def format(self, record):
        if record.levelno not in self._formatters:
            color = None
            fmt = self._fmt
            for level, c in sorted(self._colors.items()):
                if level <= record.levelno:
                    color = c
            if color:
                fmt = f"{color}{fmt}{self.reset}"
            self._formatters[record.levelno] = logging.Formatter(fmt)
        return self._formatters[record.levelno].format(record)


def configure_logger(log_level, timestamp=True):
    """
    Base logging configuration to stderr - with color if isatty

    :param log_level: log_level to configure
    :param bool timestamp: Should output inlude timestamp (no if grabbed by systemd)
    """
    global log
    log = logging.getLogger(_NAME)

    rlog = logging.getLogger()
    rlog.setLevel(logging.DEBUG)

    if timestamp:
        _LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    else:
        # Direct to syslog, getting name first, level later
        _LOG_FORMAT = "[%(name)s] %(levelname)s %(message)s"
    handler = logging.StreamHandler()
    handler.setLevel(log_level)

    # Create formatters and add it to handlers
    if sys.stderr.isatty():
        format = CustomFormatter(_LOG_FORMAT)
    else:
        format = logging.Formatter(_LOG_FORMAT)
    handler.setFormatter(format)

    # Add handlers to the logger
    rlog.addHandler(handler)


def die(msg, exit_code=1):
    log.error(msg)
    exit(exit_code)


def load_config(configfile):
    """
    Load configuration, and do some sanity checks
    """
    log.debug(f"Loading configuration from {configfile!r}")
    try:
        with open(configfile) as fd:
            config = yaml.load(fd, Loader=yaml.SafeLoader)
    except Exception as err:
        die(f"Failed to load configuration: {err}")
    if "token" not in config:
        die("token: field required in config")
    if "api" not in config:
        config["api"] = {}
    if not isinstance(config["api"], dict):
        die("config: api must be a dict")
    if "host" not in config["api"]:
        config["api"]["host"] = _API["host"]
    if "url" not in config["api"]:
        config["api"]["url"] = _API["url"]
    if "racks" not in config:
        config["racks"] = {}
    if not isinstance(config["racks"], dict):
        die("config: racks must be a dict")
    for k, v in config["racks"].items():
        if not isinstance(v, dict):
            die(f"config: racks.{k}: sub items must be dict")
        if "location" not in v:
            die(f"config: racks.{k}: location required")
    return config


def get_data(config):
    """
    Get raw consumption data from https api
    """
    log.debug("Fetching consumption raw data")
    token = config["token"]
    host = config["api"]["host"]
    url = config["api"]["url"]

    conn = http.client.HTTPSConnection(host)
    headers = {"Authorization": f"Bearer {token}"}
    conn.request("GET", url, headers=headers)
    try:
        raw = conn.getresponse().read().decode("utf-8")
        data = json.loads(raw)
    except Exception as err:
        die(f"Failed to get data from {host}: {err}")
    return data


def format_data(config, raw_data):
    """
    Convert raw_data to data we want to dump for prometheus
    """
    log.debug("Formating consumption data")
    ret = {
        "current": {},
        "power": {},
        "consumption": {},
    }
    for customer in raw_data:
        name = customer["clientName"].strip()
        for room, racks in customer["baies"].items():
            for rack in racks:
                rid = rack["baieId"]
                for key in rid, room:
                    if key in config["racks"]:
                        break
                else:
                    log.error(f"Rack: {rid}({room}): missing configuration")
                    continue
                cinfo = config["racks"][key]
                if "client" in cinfo:
                    name = cinfo["client"]
                info = {
                    "location_name": cinfo["location"],
                    # "client_id": customer["clientId"],
                    "rack_id": rack["baieId"],
                    "client_name": name,
                }
                fields = {
                    "current": rack["total"]["courantTotal"],
                    "power": rack["total"]["puissanceTotale"],
                    "consumption": rack["total"]["consommationTotale"] * 1000,
                }
                k = f"{customer['clientId']}/{rid}"
                for field, value in fields.items():
                    ret[field][k] = {
                        field: value,
                        "tags": info,
                    }
    if not any(ret.values()):
        die("No consumption value to dump")
    return ret


def dump_data(config, data, fd):
    """
    Dump data in prometheus format

    config - prometheus_prefix might be provided via config
    data - data from format_data to dump
    fd - stream to which to dump the info
    """
    log.debug("Dumping data")
    prefix = config.get("prometheus_prefix", _PROMETHEUS_PREFIX)
    lines = []
    for field, finfo in _FIELDS_INFO.items():
        if "field" in finfo:
            field = finfo["field"]
        name = f"{prefix}_{finfo['label']}"
        lines.append(f"# HELP {name} {finfo['help']}")
        lines.append(f"# TYPE {name} gauge")
        for _, info in sorted(data[field].items()):
            value = info[field]
            tags = ",".join(f'{k}="{v}"' for k, v in sorted(info["tags"].items()))
            lines.append(f"{name}{{{tags}}} {value}")
    for line in lines:
        print(line, file=fd)


def dump_to_file(config, data, outputfile):
    tmpfile = outputfile + ".tmp"
    log.debug("Dumping data to {tmpfile}")
    with open(tmpfile, "w") as fd:
        dump_data(config, data, fd)
    os.rename(tmpfile, outputfile)


def run(configfile, outputfile):
    """
    Get consumption, and dump it to outputfile if provided
    """
    config = load_config(configfile)
    raw_data = get_data(config)
    data = format_data(config, raw_data)
    if outputfile:
        dump_to_file(config, data, outputfile)
    else:
        dump_data(config, data, sys.stdout)


def run_loop(timer, configfile, outputfile):
    """
    Run in loop, every <timer> seconds
    """
    try:
        timer = int(timer)
    except ValueError:
        die(f"{timer}: timer must be a number")
    if timer <= 0:
        die(f"{timer}: timer must be > 0")
    config = load_config(configfile)
    next_run = time.time() + timer
    while True:
        raw_data = get_data(config)
        data = format_data(config, raw_data)
        dump_to_file(config, data, outputfile)
        now = time.time()
        delay = next_run - now
        if delay <= 0:
            log.warning(f"Running in loop mode, but {delay:.1f}s behind. Not sleeping")
            while next_run < now:
                next_run += timer
        else:
            log.debug(f"sleep {delay:.1f}s")
            time.sleep(delay)
            next_run += timer


def config_sample():
    """
    Show some config sample
    """
    print("#" * 72)
    print("# Minimun config requirements")
    print("#")
    print(_CONFIG_REQ.strip())
    print()
    print("#" * 72)
    print("# Other fields you might want to use")
    print("#")
    print(_CONFIG_SAMPLE.strip())
    exit(0)


if __name__ == "__main__":
    opts = docopt.docopt(__doc__)
    configure_logger("DEBUG" if opts["--debug"] else "INFO", not opts["--systemd"])
    if opts["config-sample"]:
        config_sample()
    if opts["--loop"]:
        run_loop(opts["--timer"], opts["--config"], opts["--output"])
    else:
        run(opts["--config"], opts["--output"])
