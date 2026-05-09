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

def runCmd(args):
    print(f"Running command {args}")

    result = subprocess.run(
        args,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("Finished successfully")
        return True

    print("Command error")
    print(result.stderr)
    return False
    
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
    
    