import re
import sys
import os
import subprocess
import magic
import shutil
import struct
import gzip
import lzma
import bz2
import time
import zlib

from pprint import pprint

from typing import Any, Dict

def parse_firmware_config(text: str) -> Dict[str, Any]:
    """
    Parses a firmware config format like:
    key: value # comment
    """

    config = {}

    # matches: key : value # comment (comment optional)
    line_re = re.compile(r"""
        ^\s*
        (?P<key>[a-zA-Z0-9_]+)
        \s*:\s*
        (?P<value>[^#\n]+?)
        \s*
        (?:\#.*)?$
    """, re.VERBOSE)

    for line in text.splitlines():
        line = line.strip()

        # skip empty lines
        if not line:
            continue

        match = line_re.match(line)
        if not match:
            continue  # or raise error if you want strict parsing

        key = match.group("key").strip()
        value = match.group("value").strip()

        config[key] = _normalize_value(value)

    return config


def _normalize_value(value: str) -> Any:
    """
    Try to convert values into useful Python types.
    """

    # boolean-like
    if value.lower() in ("true", "false"):
        return value.lower() == "true"

    # integer (hex or decimal)
    if re.fullmatch(r"0x[0-9a-fA-F]+", value):
        return int(value, 16)

    if re.fullmatch(r"-?\d+", value):
        return int(value)

    # list-like (comma-separated or space-separated? here we assume comma)
    if "," in value:
        return [v.strip() for v in value.split(",")]

    return value
    
    
def readcfg(file):
    try:
        with open(file, 'r') as file:
            return parse_firmware_config(file.read())
    except FileNotFoundError:
        print("File not found, please call makecfg/unpack")
        sys.exit(1)