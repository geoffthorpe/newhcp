#!/bin/bash
# Full disclosure, this script is modified from the ultra-useful
# example I found at; https://github.com/iximiuz/docker-to-linux

set -e

UID_HOST=$1
GID_HOST=$2
VM_DISK_SIZE_MB=$3

IMG=/crud/hcp_qemu_guest.img

echo "[Create disk image]"
[ -z "${VM_DISK_SIZE_MB}" ] && VM_DISK_SIZE_MB=1024
VM_DISK_SIZE_SECTOR=$(expr $VM_DISK_SIZE_MB \* 1024 \* 1024 / 512)
dd if=/dev/zero of=${IMG} bs=${VM_DISK_SIZE_SECTOR} count=512

echo "[Make partition]"
sfdisk ${IMG} <<EOF
label: dos
label-id: 0xdeadbeef
unit: sectors

linux-part : start=2048, type=83, bootable
EOF

echo "[Format partition with ext4]"
losetup -D
LOOPDEVICE=$(losetup -f)
echo -e "\n[Using ${LOOPDEVICE} loop device]"
losetup -o $(expr 512 \* 2048) ${LOOPDEVICE} ${IMG}
mkfs.ext4 ${LOOPDEVICE}

echo "[Copy directory structure to partition]"
mkdir -p /tmpmnt
mount -t auto ${LOOPDEVICE} /tmpmnt/
cp -a /poo/. /tmpmnt/

echo "[Setup extlinux]"
extlinux --install /tmpmnt/boot/
cp /syslinux.cfg /tmpmnt/boot/syslinux.cfg
rm /tmpmnt/.dockerenv

echo "[Unmount]"
umount /tmpmnt
losetup -D

echo "[Write syslinux MBR]"
dd if=/usr/lib/syslinux/mbr/mbr.bin of=${IMG} bs=440 count=1 conv=notrunc

[ "${UID_HOST}" -a "${GID_HOST}" ] && chown ${UID_HOST}:${GID_HOST} ${IMG}
