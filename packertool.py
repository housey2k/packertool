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

import modules.uimage
import modules.jffs2
import modules.squashfs
import modules.config_parser
import modules.os_utils

cfg_sample = """
source_file: firmware.bin # input file when unpack is used
out_file: firmware-repack.bin # output file when repack is used
unpack_raw: unpack_raw # output folder for binaries such as FSBL and U-Boot
unpack_fs: unpack_fs # output folder for compressed parts such as squashfs
repack_fs: repack_fs # ouput folder for compressing unpack_fs back into squashfs files and combining them and unpack_raw into out_file
binwalk_mode: false # binwalk mode automatically sets up mtdparts through the binwalk command, individual files and filesystems will be saved in numerical order
mtdparts: 0x0, 0x1, 1BL # partitions from your firmware, this is NOT COMPATIBLE with mtdparts from u-boot, format is BEGINh, ENDh, NAME
"""

repack_sample = """
# DO NOT EDIT
loader: 0x0, data, unpack_fs/loader
fdt: 0x10000, data, unpack_fs/fdt
fdt.restore: 0x30000, data, unpack_fs/fdt.restore
boot: 0x50000, data, unpack_fs/boot
romfs: 0xb0000, squashfs, -comp xz -b 262144, unpack_fs/romfs
usr: 0x420000, squashfs, -comp xz -b 65536, unpack_fs/usr
web: 0xba0000, squashfs, -comp xz -b 65536, unpack_fs/web
custom: 0xc10000, squashfs, -comp xz -b 262144, unpack_fs/custom
logo: 0xf60000, squashfs, -comp xz -b 4096, unpack_fs/logo
mtd: 0xf80000, data, unpack_fs/mtd

"""

    


    
def displayArgs():
    print("help           Show help")
    print("unpack         Unpack input firmware image")
    print("repack         Repack output firmware image")
    print("configurator   NOT IMPLEMENTED, EDIT \"packertool.cfg\"")
    print("dumpcfg        cfg parser test (optional args packertool/repack)")
    print("makecfg        Write example cfg file")
    
def unpack():
    config = modules.config_parser.readcfg("packertool.cfg")
    
    os.makedirs(config["unpack_raw"], exist_ok=True)
    os.makedirs(config["unpack_fs"], exist_ok=True)
    
    try:
        with open(config["source_file"], 'rb') as file:
            data = file.read()
            #print("File contents:")
            #print(data)
    except FileNotFoundError:
        print(f"source_file {config["source_file"]} not found")
        sys.exit(1)
    
    if config["binwalk_mode"] == True:
        print("binwalk_mode not implemented");
    else:
        mtdparts = config["mtdparts"]
        for start, end, name in zip(mtdparts[0::3], mtdparts[1::3], mtdparts[2::3]):
            start = int(start, 0)
            end = int(end, 0)
            
            print(f"Extracting {name} from {start} to {end}")
            print(f"start={start}, end={end}, size={end-start}")
            
            binFilePath = os.path.join(config["unpack_raw"], f"{name}.bin") #binary file extracted
            
            print(f"Saving to {binFilePath}")
            
            with open(binFilePath, "wb") as out:
                out.write(data[start:end])
                
            
            fileMagic = magic.from_file(binFilePath)
            
            print(f"File recognized as {fileMagic}")
            
            # DONE: Generate repack.cfg containing each partition's type (squashfs, jffs2, etc), block size, flags, etc
            # example below
            # # DO NOT EDIT
            # FSBL: data, unpack_raw/FSBL.bin
            # hsqs_part: squashfs, compression_alg, blocksize, unpack_fs/hsqs_part
            # jffs2_part: jffs2, idk how this works, what should i put here, i'll focus no squashfs first, unpack_fs/jffs2_part
            # ^ done, format ended up pretty different 
            
            #extractedFilePath = os.path.join(config["unpack_fs"], name)
            
            # TODO: jffs2 support
            
            # WIP: uImage support
            
            
            # DONE: Change repack.cfg format from "name: offset, type, flags, location" on squashfs and "name: offset, path, type" on raw to "name:offset, type, location, flags"
            # ^ now its standardized
            
            # TODO: Move file operations into /tmp to spare HDD/SSD cycles
            
            if "Squashfs filesystem" in fileMagic:  
                modules.squashfs.unpack(start, name, config, binFilePath)
            elif "jffs2 filesystem" in fileMagic:
                modules.jffs2.unpack(start, name, config, binFilePath)
            elif "u-boot legacy uImage" in fileMagic:
                modules.uimage.unpack(start, name, config, binFilePath)
            else:
                modules.os_utils.writeFile("repack.cfg", f"{name}: {hex(start)}, data, {binFilePath}, noflags \n", "# DO NOT EDIT\n")
        
        filesize = os.path.getsize(config["source_file"])
        modules.os_utils.writeFile("repack.cfg", f"filesize: {filesize}, fileend\n", "# DO NOT EDIT\n")
    
def repack():
    repack = modules.config_parser.readcfg("repack.cfg")
    config = modules.config_parser.readcfg("packertool.cfg")

    with open(config["out_file"], "wb") as f:
        f.seek(int(repack["filesize"][0]) - 1)
        f.write(b"\xff")
    print(f"Created {config["out_file"]}")
    
    os.makedirs(config["repack_fs"], exist_ok=True)
    
    for section, data in repack.items():
        #print(section, data)
        
        #format is now "name:offset, type, location, flags"
        # aka section:data[0], data[1], data[2], data[3]
        
        if data[1] == "data": # data[1] eq data type, can be data, squashfs, jffs2, etc
            data_location = os.path.join(config["repack_fs"], f"{section}.bin")
            
            print(f"Copying {section} from {data[2]} to {data_location}")
            
            shutil.copy(data[2], data_location)
            
            modules.os_utils.write_sector(data_location, config["out_file"], int(data[0], 16))
            print(f"Wrote {section} from {data_location} starting at {data[0]} to {config["out_file"]}")
            
        elif data[1] == "squashfs":
            modules.squashfs.repack(section, data, config)
        elif data[1] == "jffs2":
            modules.jffs2.repack(section, data, config)
        elif data[1] == "uimg":
            modules.uimage.repack(section, data, config)
        elif data[1] == "fileend":
            print(f"Reached EOF at {data[0]}")
        else:
            print(f"Unknown type {data[1]}, ignoring")
    
    
    
def configurator():
    print("Not implemented, edit packertool.cfg")
    
def dumpcfg(mode=None):
    print("Parsed output:")
    config = modules.config_parser.readcfg("packertool.cfg")
    pprint(config)
    
    print("Parsed output:")
    config = modules.config_parser.readcfg("packertool.cfg")
    pprint(config)


def makecfg():
    with open("packertool.cfg", "w", encoding="utf-8") as f:
        f.write(cfg_sample)
        
def clean():
    config = modules.config_parser.readcfg("packertool.cfg")
    
    for key in ["unpack_raw", "unpack_fs", "repack_fs"]:
        path = config[key]
        if path and os.path.isdir(path):
            shutil.rmtree(path)
            print(f"Deleted {path}.")
    if os.path.exists("repack.cfg"):
        os.remove("repack.cfg")
        print("Deleted repack.cfg.")
    print("Environment clean.")
    
# ----------------- Example -----------------
if __name__ == "__main__":
    
    print("packertool v0.0.6")
    print("Written with <3 by housey2k")
    print("Know your firmware!")
    print("This program is in early development, please help by contributing with more functionality")
    
    
    if len(sys.argv) < 2:
        print("No argument")
        displayArgs()
        sys.exit(1)
           
    if sys.argv[1] == "help":
        displayArgs()
        
    elif sys.argv[1] == "unpack":
        unpack()
        
    elif sys.argv[1] == "repack":
        repack()
        
    elif sys.argv[1] == "configurator":
        configurator()
        
    elif sys.argv[1] == "dumpcfg":
        arg = sys.argv[2] if len(sys.argv) > 2 else None
        dumpcfg(arg)
        
    elif sys.argv[1] == "makecfg":
        makecfg()
        
    elif sys.argv[1] == "clean":
        clean()
    elif sys.argv[1] == "unpack-safe":
        print("Not implemented")
        #unpack_safe()
        
    else:
        print(f"Unknown command: {sys.argv[1]}")
