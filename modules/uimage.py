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

def get_uimage_repack_flags(uimage_path):
    UIMAGE_MAGIC = 0x27051956

    data = open(uimage_path, "rb").read(64)
    if len(data) < 64:
        raise ValueError("Not a valid uImage")

    magic = struct.unpack(">I", data[0:4])[0]
    if magic != UIMAGE_MAGIC:
        raise ValueError("Not a uImage")

    size      = struct.unpack(">I", data[12:16])[0]
    load_addr = struct.unpack(">I", data[16:20])[0]
    entry     = struct.unpack(">I", data[20:24])[0]

    os_id   = data[28]
    arch_id = data[29]
    type_id = data[30]
    comp_id = data[31]

    name = data[32:64].split(b"\x00", 1)[0].decode(errors="ignore")

    OS = {5: "linux"}
    ARCH = {2: "arm", 3: "x86", 8: "mips"}
    TYPE = {2: "kernel", 4: "multi", 5: "firmware", 7: "filesystem"}
    COMP = {0: "none", 1: "gzip", 2: "bzip2", 3: "lzma", 4: "lzo", 5: "lz4", 6: "zstd"}

    flags = [
        f"-A {ARCH.get(arch_id, f'unknown:{arch_id}')}",
        f"-O {OS.get(os_id, f'unknown:{os_id}')}",
        f"-T {TYPE.get(type_id, f'unknown:{type_id}')}",
        f"-C {COMP.get(comp_id, f'unknown:{comp_id}')}",
        f"-a 0x{load_addr:08x}",
        f"-e 0x{entry:08x}",
    ]

    if name:
        flags.append(f'-n "{name}"')

    return " ".join(flags)
   

def extract_uimage(uimage_path, out_path, config):

    print("[+] inspecting image")

    #info = subprocess.run(
    #    ["dumpimage", "-l", uimage_path],
    #    capture_output=True,
    #    text=True
    #)

    #print(info.stdout)
    #if info.returncode != 0:
    #    print(info.stderr)
    #    return False
    
    if not modules.os_utils.runCmd(["dumpimage", "-l", uimage_path]):
        return False


    print("[+] extracting payload")

    #result = subprocess.run(
    #    ["dumpimage", "-T", "firmware", "-p", "0", "-o", out_path, uimage_path],
    #    capture_output=True,
    #    text=True
    #)

    #if result.returncode != 0:
    #    print(result.stderr)
    #    return False
    
    if not modules.os_utils.runCmd(["dumpimage", "-T", "firmware", "-p", "0", "-o", out_path, uimage_path]):
        return False;

    print("[+] extraction successful")
    return True
    
def make_uimage(flags, payload_path, out_path):
    UIMAGE_MAGIC = 0x27051956

    # --- parse flags ---
    import re

    def grab(flag):
        m = re.search(rf"{flag}\s+([^\s]+)", flags)
        return m.group(1) if m else None

    def grab_hex(flag):
        m = re.search(rf"{flag}\s+0x([0-9a-fA-F]+)", flags)
        return int(m.group(1), 16) if m else 0

    def grab_name():
        m = re.search(r'-n\s+"(.*?)"', flags)
        return m.group(1) if m else ""

    arch_s = grab("-A")
    os_s   = grab("-O")
    type_s = grab("-T")
    comp_s = grab("-C")

    load  = grab_hex("-a")
    entry = grab_hex("-e")
    name  = grab_name()

    # --- tables ---
    OS   = {"linux": 5}
    ARCH = {"arm": 2, "x86": 3, "mips": 8}
    TYPE = {"kernel": 2, "multi": 4, "firmware": 5, "filesystem": 7}
    COMP = {"none": 0, "gzip": 1, "bzip2": 2, "lzma": 3, "lzo": 4, "lz4": 5, "zstd": 6}

    arch_id = ARCH.get(arch_s, 0)
    os_id   = OS.get(os_s, 0)
    type_id = TYPE.get(type_s, 0)
    comp_id = COMP.get(comp_s, 0)

    payload = open(payload_path, "rb").read()
    size = len(payload)

    name_bytes = name.encode()[:32].ljust(32, b"\x00")

    # --- header (temporary CRCs) ---
    header = struct.pack(
        ">IIIIIIIBBBB32s",
        UIMAGE_MAGIC,
        0,
        int(time.time()),
        size,
        load,
        entry,
        0,
        os_id,
        arch_id,
        type_id,
        comp_id,
        name_bytes
    )

    # --- CRCs ---
    dcrc = zlib.crc32(payload) & 0xFFFFFFFF
    header = header[:24] + struct.pack(">I", dcrc) + header[28:]

    hcrc = zlib.crc32(header) & 0xFFFFFFFF
    header = header[:4] + struct.pack(">I", hcrc) + header[8:]

    # --- write final image ---
    with open(out_path, "wb") as f:
        f.write(header)
        f.write(payload)

    print(f"[+] wrote uImage -> {out_path}")
    
def unpack(start, name, config, binFilePath):
    uImgFilePath = os.path.join(config["unpack_raw"], f"{name}.uimg") # raw uImage file
    extImgPath = os.path.join(config["unpack_raw"], f"{name}.bin") # extracted uImage file
                
    print(f"Renaming {binFilePath} into {uImgFilePath}")
                
    os.rename(binFilePath, uImgFilePath)
                
    print(f"Reading uImage")
                
    uImg_flags = get_uimage_repack_flags(uImgFilePath)
                
    print(f"Unpacking uImage payload into {extImgPath}")
                
    uimage_extract_success = extract_uimage(uImgFilePath, extImgPath, config)
                
                
    if uimage_extract_success:
        print(f"Extraction succesfull")
        modules.os_utils.writeFile("repack.cfg", f"{name}: {hex(start)}, uimg, {extImgPath}, {uImg_flags} \n", "# DO NOT EDIT\n")
        print(f"Deleting {uImgFilePath}")
        os.remove(uImgFilePath)
    else:
        print("uImage extraction failed, saving as data + flags")
        modules.os_utils.writeFile("repack.cfg", f"{name}: {hex(start)}, data, {uImgFilePath}, {uImg_flags} \n", "# DO NOT EDIT\n")
        print(f"Not deleting {uImgFilePath}")
        
def repack(section, data, config):
    uimg_out_location = os.path.join(config["repack_fs"], f"{section}.uimg")
            
    #make_uimage(flags, payload_location, out_location)
    make_uimage(data[3], data[2], uimg_out_location)
            
    modules.os_utils.write_sector(uimg_out_location, config["out_file"], int(data[0], 16))
    print(f"Wrote {section} from {uimg_out_location} starting at {data[0]} to {config["out_file"]}")