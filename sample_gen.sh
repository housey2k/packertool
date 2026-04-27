#!/bin/sh

set -e

OUT="./test_fw"
mkdir -p "$OUT"

# -----------------------
# SquashFS
# -----------------------
mkdir -p "$OUT/sqroot"
echo "squashfs test" > "$OUT/sqroot/hello.txt"

mksquashfs "$OUT/sqroot" "$OUT/rootfs.squashfs" -noappend -comp xz

# -----------------------
# JFFS2
# -----------------------
mkdir -p "$OUT/jffs2root"
echo "jffs2 config" > "$OUT/jffs2root/config.txt"

mkfs.jffs2 \
    -r "$OUT/jffs2root" \
    -o "$OUT/config.jffs2" \
    -e 0x10000

# -----------------------
# uImage
# -----------------------
echo "TEST_KERNEL_DATA" > "$OUT/kernel.bin"

mkimage \
    -A mips \
    -O linux \
    -T kernel \
    -C none \
    -a 0x80010000 \
    -e 0x80010000 \
    -n "test-kernel" \
    -d "$OUT/kernel.bin" \
    "$OUT/uImage.bin"

# -----------------------
# Build fake firmware layout
# -----------------------
FW="$OUT/firmware.bin"
rm -f "$FW"

append() {
    cat "$1" >> "$FW"
}

align() {
    SIZE=$(stat -c%s "$FW")
    PAD=$(( (0x1000 - (SIZE % 0x1000)) % 0x1000 ))
    dd if=/dev/zero bs=1 count=$PAD >> "$FW" 2>/dev/null
}

START_SQ=0x0
append "$OUT/rootfs.squashfs"
align
END_SQ=$(stat -c%s "$FW")

START_JFFS=$END_SQ
append "$OUT/config.jffs2"
align
END_JFFS=$(stat -c%s "$FW")

START_UIMG=$END_JFFS
append "$OUT/uImage.bin"
align
END_UIMG=$(stat -c%s "$FW")

# -----------------------
# mtdparts output
# -----------------------
echo ""
echo "mtdparts=custom:"
echo "0x$START_SQ,0x$END_SQ,squashfs"
echo "0x$START_JFFS,0x$END_JFFS,jffs2"
echo "0x$START_UIMG,0x$END_UIMG,uImage"

echo ""
echo "Firmware: $FW"
