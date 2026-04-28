#!/bin/sh

set -e

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

FW="./firmware.bin"
rm -f "$FW"

# -----------------------
# SquashFS
# -----------------------
mkdir -p "$TMP/sqroot"
echo "squashfs test" > "$TMP/sqroot/hello.txt"

mksquashfs "$TMP/sqroot" "$TMP/rootfs.squashfs" -noappend -comp xz

# -----------------------
# JFFS2
# -----------------------
mkdir -p "$TMP/jffs2root"
echo "jffs2 config" > "$TMP/jffs2root/config.txt"

mkfs.jffs2 \
    -r "$TMP/jffs2root" \
    -o "$TMP/config.jffs2" \
    -e 0x10000

# -----------------------
# uImage
# -----------------------
echo "TEST_KERNEL_DATA" > "$TMP/kernel.bin"

mkimage \
    -A mips \
    -O linux \
    -T kernel \
    -C none \
    -a 0x80010000 \
    -e 0x80010000 \
    -n "test-kernel" \
    -d "$TMP/kernel.bin" \
    "$TMP/uImage.bin"

# -----------------------
# Build fake firmware layout
# -----------------------
append() {
    cat "$1" >> "$FW"
}

align() {
    SIZE=$(stat -c%s "$FW")
    PAD=$(( (0x1000 - (SIZE % 0x1000)) % 0x1000 ))
    dd if=/dev/zero bs=1 count=$PAD >> "$FW" 2>/dev/null
}

# SquashFS
START_SQ=0
append "$TMP/rootfs.squashfs"
align
END_SQ=$(stat -c%s "$FW")

# JFFS2
START_JFFS=$END_SQ
append "$TMP/config.jffs2"
align
END_JFFS=$(stat -c%s "$FW")

# uImage
START_UIMG=$END_JFFS
append "$TMP/uImage.bin"
align
END_UIMG=$(stat -c%s "$FW")

# -----------------------
# mtdparts output (offset, size)
# -----------------------
SIZE_SQ=$((END_SQ - START_SQ))
SIZE_JFFS=$((END_JFFS - START_JFFS))
SIZE_UIMG=$((END_UIMG - START_UIMG))

echo ""
echo "mtdparts="

printf "0x%x,0x%x,squashfs\n" "$START_SQ" "$END_SQ"
printf "0x%x,0x%x,jffs2\n" "$START_JFFS" "$END_JFFS"
printf "0x%x,0x%x,uImage\n" "$START_UIMG" "$END_UIMG"

echo ""
echo "Firmware: $FW"
