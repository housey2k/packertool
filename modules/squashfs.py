#!/usr/bin/env python3
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

import modules.os_utils

def get_squashfs_repack_flags(path):
    result = subprocess.run(
        ["unsquashfs", "-s", path],
        capture_output=True,
        text=True,
        check=True
    )

    out = result.stdout

    comp = None
    block_size = None

    # compression
    m = re.search(r"Compression\s+(\w+)", out, re.IGNORECASE)
    if m:
        comp = m.group(1)

    # block size
    m = re.search(r"Block size\s+(\d+)", out, re.IGNORECASE)
    if m:
        block_size = m.group(1)

    # build CLI flags
    flags = []

    if comp:
        flags.append(f"-comp {comp}")

    if block_size:
        flags.append(f"-b {block_size}")

    return " ".join(flags)
    
def unpack(start, name, config, binFilePath):
    squashfsFilePath = os.path.join(config["unpack_raw"], f"{name}.squashfs") # raw squashfs file
    squashfsFolder = os.path.join(config["unpack_fs"], name) # folder for extracted squashfs
    
    print(f"Renaming {binFilePath} into {squashfsFilePath}")

    os.rename(binFilePath, squashfsFilePath) # rename from .bin into .squashfs
                
    print(f"Extracting squashfs partition into {squashfsFolder}")
                
    modules.os_utils.runCmd(["unsquashfs", "-d", squashfsFolder, squashfsFilePath])
                
    squashfs_flags = get_squashfs_repack_flags(squashfsFilePath) # flags being compression alg -comp and block size -b

    print(f"SquashFS flags: {squashfs_flags}")
                    
    modules.os_utils.writeFile("repack.cfg", f"{name}: {hex(start)}, squashfs, {squashfsFolder}, {squashfs_flags}\n", "# DO NOT EDIT\n")
                
    print(f"Deleting {squashfsFilePath}")
    os.remove(squashfsFilePath)
    
def repack(section, data, config):
    
    squashfs_location = os.path.join(config["repack_fs"], f"{section}.squashfs")
            
    print(f"Compressing squashfs {section}")
    #mksquashfs input_dir output_file args --noappend
    modules.os_utils.runCmd(["mksquashfs", data[2], squashfs_location, *data[3].split(), "-noappend"])
            
    modules.os_utils.write_sector(squashfs_location, config["out_file"], int(data[0], 16))
    print(f"Wrote {section} from {squashfs_location} starting at {data[0]} to {config["out_file"]}")