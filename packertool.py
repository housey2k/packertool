import re
import sys
import os
import subprocess
import magic
import shutil
import struct

from pprint import pprint

from typing import Any, Dict

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
    
def get_uimage_repack_flags(path):
    with open(path, "rb") as f:
        data = f.read(64)

    if len(data) < 64:
        raise ValueError("Not a valid uImage (too small)")

    magic, hcrc, time, size, load, entry, dcrc, os, arch, img_type, comp = struct.unpack(
        ">IIIIIIIBBBB",
        data[:32]
    )

    name = data[32:64].split(b"\x00", 1)[0].decode(errors="ignore")

    # sanity check
    if magic != 0x27051956:
        raise ValueError("Not a uImage")

    arch_map = {
        8: "mips",
        2: "arm",
        3: "x86",
    }

    os_map = {
        5: "linux",
    }

    comp_map = {
        2: "gzip",
        3: "bzip2",
        4: "lzma",
        5: "lz4",
    }

    type_map = {
        2: "kernel",
        3: "ramdisk",
        7: "firmware",
    }

    arch_str = arch_map.get(arch, "unknown")
    os_str = os_map.get(os, "linux")
    comp_str = comp_map.get(comp, "none")
    type_str = type_map.get(img_type, "firmware")

    # build CLI flags (same style as your squashfs function)
    flags = []

    flags.append(f"-A {arch_str}")
    flags.append(f"-O {os_str}")
    flags.append(f"-T {type_str}")
    flags.append(f"-C {comp_str}")
    flags.append(f"-a 0x{load:x}")
    flags.append(f"-e 0x{entry:x}")

    if name:
        flags.append(f"-n \"{name}\"")

    return " ".join(flags)
    
    
def extract_uimage(path, out_path):
    import struct, lzma, gzip

    data = open(path, "rb").read()

    magic = struct.unpack(">I", data[0:4])[0]
    if magic != 0x27051956:
        raise ValueError("Not uImage")

    size = struct.unpack(">I", data[12:16])[0]
    comp = data[40]  # compression field in header

    payload = data[64:64+size]

    # YOU handle payload here
    if comp == 4:  # LZMA
        payload = lzma.decompress(payload)
    elif comp == 2:  # gzip
        payload = gzip.decompress(payload)

    with open(out_path, "wb") as f:
        f.write(payload)

    return payload
    
def write_sector(in_file, out_file, offset):
    with open(in_file, "rb") as f_in, open(out_file, "r+b") as f_out:
        data = f_in.read()
        f_out.seek(offset)
        f_out.write(data)
       
def writeFile(out_file, text, header = ""):
    file_exists = os.path.exists(out_file)    
    with open(out_file, "a") as f:
        if not file_exists:
            f.write(header)
            print(f"Created {out_file} and wrote {header}")
        f.write(text)
        print(f"Wrote {text} to {out_file}")  
def runCmd(args, check=True):
    print(f"Running command {args}")
    subprocess.run(args, check=check)
    print(f"Finished command")
    
def displayArgs():
    print("help           Show help")
    print("unpack         Unpack input firmware image")
    print("repack         Repack output firmware image")
    print("configurator   NOT IMPLEMENTED, EDIT \"packertool.cfg\"")
    print("dumpcfg        cfg parser test (optional args packertool/repack)")
    print("makecfg        Write example cfg file")
    
def unpack():
    try:
        with open('packertool.cfg', 'r') as file:
            config = parse_firmware_config(file.read())
    except FileNotFoundError:
        print("File not found, please call makecfg")
        sys.exit(1)
    
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
                
                squashfsFilePath = os.path.join(config["unpack_raw"], f"{name}.squashfs") # raw squashfs file
                squashfsFolder = os.path.join(config["unpack_fs"], name) # folder for extracted squashfs
                
                print(f"Renaming {binFilePath} into {squashfsFilePath}")

                os.rename(binFilePath, squashfsFilePath) # rename from .bin into .squashfs
                
                print(f"Extracting squashfs partition into {squashfsFolder}")
                
                runCmd(["unsquashfs", "-d", squashfsFolder, squashfsFilePath], True)
                
                squashfs_flags = get_squashfs_repack_flags(squashfsFilePath) # flags being compression alg -comp and block size -b

                print(f"SquashFS flags: {squashfs_flags}")
                    
                writeFile("repack.cfg", f"{name}: {hex(start)}, squashfs, {squashfsFolder}, {squashfs_flags}\n", "# DO NOT EDIT\n")
                
                print(f"Deleting {squashfsFilePath}")
                os.remove(squashfsFilePath)
                
            elif "jffs2 filesystem" in fileMagic:
                print("jffs2 is not supported, it will be treated as data")

                jffs2FilePath = os.path.join(config["unpack_raw"], f"{name}.jffs2") # raw jffs2 file
                
                print(f"Renaming {binFilePath} into {jffs2FilePath}")
                
                writeFile("repack.cfg", f"{name}: {hex(start)}, jffs2, {binFilePath}, noflags \n", "# DO NOT EDIT\n")
                
            elif "u-boot legacy uImage" in fileMagic:
                print("u-boot legacy uImage WIP")
                
                uImgFilePath = os.path.join(config["unpack_raw"], f"{name}.uimg") # raw jffs2 file
                extImgPath = os.path.join(config["unpack_raw"], f"{name}.bin") # extracted uImage file
                
                print(f"Renaming {binFilePath} into {uImgFilePath}")
                
                os.rename(binFilePath, uImgFilePath)
                
                print(f"Extracting uImage into {extImgPath}")
               
                extract_uimage(uImgFilePath, extImgPath)
                
                uImg_flags = get_uimage_repack_flags(uImgFilePath)

                print(f"uImage flags: {uImg_flags}")

                writeFile("repack.cfg", f"{name}: {hex(start)}, uimg, {extImgPath}, {uImg_flags} \n", "# DO NOT EDIT\n")
                
                print(f"Deleting {uImgFilePath}")
                os.remove(uImgFilePath)
                
            else:
                writeFile("repack.cfg", f"{name}: {hex(start)}, data, {binFilePath}, noflags \n", "# DO NOT EDIT\n")
        
        filesize = os.path.getsize(config["source_file"])
        writeFile("repack.cfg", f"filesize: {filesize}, fileend\n", "# DO NOT EDIT\n")
    
def repack():
    try:
        with open('repack.cfg', 'r') as file:
            repack = parse_firmware_config(file.read())
    except FileNotFoundError:
        print("File not found, please call unpack")
        sys.exit(1)
        
    try:
        with open('packertool.cfg', 'r') as file:
            config = parse_firmware_config(file.read())
    except FileNotFoundError:
        print("File not found, please call makecfg")
        sys.exit(1)

    with open(config["out_file"], "wb") as f:
        f.seek(int(repack["filesize"][0]) - 1)
        f.write(b"\xff")
    print(f"Created {config["out_file"]}")
    
    os.makedirs(config["repack_fs"], exist_ok=True)
    
    for section, data in repack.items():
        print(section, data)
        
        #format is now "name:offset, type, location, flags"
        # aka section:data[0], data[1], data[2], data[3]
        
        if data[1] == "data": # data type, can be data, squashfs, jffs2, etc
            write_sector(data[2], config["out_file"], int(data[0], 16))
            print(f"Wrote {section} from {data[2]} starting at {data[0]} to {config["out_file"]}")
            
        elif data[1] == "squashfs":
            squashfs_location = os.path.join(config["repack_fs"], f"{section}.squashfs")
            
            #mksquashfs input_dir output_file args --noappend
            runCmd(["mksquashfs", data[2], squashfs_location, *data[3].split(), "-noappend"], True)
            
            write_sector(squashfs_location, config["out_file"], int(data[0], 16))
            print(f"Wrote {section} from {squashfs_location} starting at {data[0]} to {config["out_file"]}")
            
        elif data[1] == "jffs2":
            print("jffs2 is not supported, it will be treated as data")
            write_sector(data[2], config["out_file"], int(data[0], 16))
            print(f"Wrote {section} from {data[2]} starting at {data[0]} to {config["out_file"]}")
        else:
            print(f"Unknown type {data[1]}, ignoring")
    
    
    
def configurator():
    print("Not implemented, edit packertool.cfg")
    
def dumpcfg(mode=None):

    # 1. explicit repack mode
    if mode == "repack":
        content = repack_sample
        print("Using repack_sample")

    # 2. explicit packertool sample mode
    elif mode == "packertool":
        content = cfg_sample
        print("Using cfg_sample")

    # 3. default behavior: try file, fallback to sample
    else:
        try:
            with open("packertool.cfg", "r") as f:
                content = f.read()
                print("Loaded packertool.cfg")
        except FileNotFoundError:
            content = cfg_sample
            print("Config not found, using cfg_sample")

    # 4. parse
    print("Parsed output:")
    config = parse_firmware_config(content)
    pprint(config)


def makecfg():
    with open("packertool.cfg", "w", encoding="utf-8") as f:
        f.write(cfg_sample)
        
def clean():
    try:
        with open('packertool.cfg', 'r') as file:
            config = parse_firmware_config(file.read())
    except FileNotFoundError:
        print("File not found, please call makecfg")
        sys.exit(1)
    
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
    
    print("packertool v0.0.2")
    print("Written with <3 by housey2k")
    print("Version 1.0.1")
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
        
    else:
        print(f"Unknown command: {sys.argv[1]}")