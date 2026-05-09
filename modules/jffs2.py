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


def unpack(start, name, config, binFilePath):
    print("jffs2 is not currently supported, it will be treated as data")
    jffs2FilePath = os.path.join(config["unpack_raw"], f"{name}.jffs2") # raw jffs2 file
    print(f"Renaming {binFilePath} into {jffs2FilePath}")
    modules.os_utils.writeFile("repack.cfg", f"{name}: {hex(start)}, jffs2, {binFilePath}, noflags \n", "# DO NOT EDIT\n")
    

def repack(section, data, config):
    print("jffs2 is not currently supported, it will be treated as data")       
    data_location = os.path.join(config["repack_fs"], f"{section}.bin")    
    print(f"Copying {section} from {data[2]} to {data_location}")   
    shutil.copy(data[2], data_location)
    modules.os_utils.write_sector(data_location, config["out_file"], int(data[0], 16))
    print(f"Wrote {section} from {data_location} starting at {data[0]} to {config["out_file"]}")