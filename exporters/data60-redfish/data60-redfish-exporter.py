#! /usr/bin/env python3
"""
Usage:
  data60-redfish-exporter.py [options] [-c <config>] <name>

Options:
    -c,--config=<config>     Configuration file [Default: config.yml]
    -l,--log-level=<level>  Log level [Default: info]
"""

import sys
import json
import logging
import http.client
import ssl
import yaml
import docopt
import base64

_NAME = "data60-redfish-exporter"
log = logging.getLogger(__name__)

_POWER_DATA_URI = "/redfish/v1/Chassis/Enclosure/Power"

_GREEN_LIGHT = "green_equipment_power_consumption_va"
_PROMETHEUS_PREFIX = "redfish"
_FIELDS_INFO = {
    "power_state": {
        "help": "Power supply state",
    },
    "power_health": {
        "help": "Power supply health",
    },
    "power_voltage": {
        "help": "Power supply measured voltage",
    },
    "power_current": {
        "help": "Power supply measured current",
    },
    "power_va": {
        "help": "Power supply computed va (from voltage and current)",
    },
    _GREEN_LIGHT: {
        "help": "Global power supply computed va (from voltage and current, summing all equipment power supplies)",
    },
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


def die(msg):
    log.error(msg)
    exit(msg)


def load_config(filename):
    try:
        with open(filename) as fd:
            data = yaml.load(fd, Loader=yaml.SafeLoader)
    except Exception as err:
        die(f"{filename}: failed to load config: {err}")
    try:
        devices = data["devices"].items()
    except:
        die("Config bad format. `devices` top-level dict not found")
    err = False
    for name, info in devices:
        if not isinstance(info, dict):
            log.error(f"devices:{name}: must be a dict")
            err = True
            continue
        for k in "user", "pass", "ips":
            if k not in info:
                log.error(f"devices:{name}: must be a dict")
                err = True
                continue
            v = info[k]
            if isinstance(v, str):
                if k == "ip":
                    info[k] = (v,)
                continue
            if k != "ips":
                log.error(f"devices:{name}: must be a string")
                err = True
            try:
                if all(isinstance(x, str) for x in v):
                    continue
            except:
                pass
            log.error(f"devices:{name}: must be a list of strings")
            err = True
    if err:
        die("Invalid config format")
    return data


def basic_auth(user, pwd):
    token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _get_raw1(ip, info, uri):
    conn = http.client.HTTPSConnection(ip, context=ssl._create_unverified_context())
    headers = {"Authorization": basic_auth(info["user"], info["pass"])}
    conn.request("GET", _POWER_DATA_URI, headers=headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    return json.loads(raw)


def _get_raw(name, info, uri):
    for ip in info["ips"]:
        try:
            raw = _get_raw1(ip, info, uri)
            break
        except Exception as err:
            log.warning(f"{name}: {ip}: failed to get data: {err}")
    else:
        log.error(f"{name}: failed to collect {uri}")
        return {}
    return raw


def _strip_prefix(info, prefix):
    if info.startswith(prefix):
        return info[len(prefix) :].strip()
    return info


def _compute_power_va(info):
    currs = {x["power_name"]: x["value"] for x in info["power_current"]}
    ret = []
    consumption = 0
    # AC/12V -> IN/OUT
    for info in info["power_voltage"]:
        k = info["power_name"]
        v = info["value"]
        if k in currs:
            ret.append(
                {
                    "power_name": k,
                    "value": v * currs[k],
                }
            )
            continue
        if k.endswith("AC"):
            kc = k[:-2] + "IN"
            ko = k + " IN"
        elif k.endswith("12V"):
            kc = k[:-3] + "OUT"
            ko = k + " OUT"
        else:
            kc = None
        if kc in currs:
            power = v * currs[kc]
            ret.append(
                {
                    "power_name": ko,
                    "value": power,
                }
            )
            if kc.endswith("IN"):
                consumption += power
    return ret, consumption


def _collect_power_data(name, info):
    raw = _get_raw(name, info, _POWER_DATA_URI)
    if not raw:
        return raw
    ret = {}
    ret["power_state"] = [
        {
            "power_supply_name": info["Name"],
            "value": info["Status"]["State"] and 1 or 0,
        }
        for info in raw["PowerSupplies"]
    ]
    ret["power_health"] = [
        {
            "power_supply_name": info["Name"],
            "value": info["Status"]["Health"] and 1 or 0,
        }
        for info in raw["PowerSupplies"]
    ]
    ret["power_voltage"] = [
        {
            "power_name": _strip_prefix(info["Name"], "VOLT "),
            "value": info["ReadingVolts"],
        }
        for info in raw["Voltages"]
    ]
    ret["power_current"] = [
        {
            "power_name": _strip_prefix(info["Name"], "CURR "),
            "value": info["ReadingAmps"],
        }
        for info in raw["Oem"]["WDC"]["Currents"]
    ]
    if len(ret["power_voltage"]) == len(ret["power_current"]):
        powers, consuption = _compute_power_va(ret)
        ret["power_va"] = powers
        ret[_GREEN_LIGHT] = ({"value": consuption},)
    return ret


def _collect_data(name, info):
    return _collect_power_data(name, info)


def collect_all_data(config):
    ret = {}
    for name, info in config["devices"].items():
        data = _collect_data(name, info)
        if data:
            ret[name] = data
    return ret


def dump_data(data):
    for field, finfo in _FIELDS_INFO.items():
        if not any(field in v for k, v in data.items()):
            continue
        label = f"{_PROMETHEUS_PREFIX}_{finfo.get('label', field)}"
        print(f"# HELP {label} {finfo['help']}")
        print(f"# TYPE {label} gauge")
        for name, blocks in data.items():
            if field not in blocks:
                continue
            for info in blocks[field]:
                opts = dict(info)
                # opts['instance'] = name
                value = opts.pop("value")
                if not isinstance(value, int):
                    value = f"{value:.2f}"
                opts_str = ",".join(f'{k}="{v}"' for k, v in opts.items())
                print(f"{label}{{{opts_str}}} {value}")


def run(configfile, name):
    config = load_config(configfile)
    if name not in config["devices"]:
        die(f"{name}: not found in config")
    info = config["devices"][name]
    data = _collect_data(name, info)
    if not data:
        die("Failed to get any data")
    dump_data({name: data})


if __name__ == "__main__":
    opts = docopt.docopt(__doc__)
    configure_logger(opts["--log-level"].upper())
    run(opts["--config"], opts["<name>"])
