#!/bin/bash
# Full disclosure, this script is modified from the ultra-useful
# example I found at; https://github.com/iximiuz/docker-to-linux

set -e

UID_HOST=$1
GID_HOST=$2
VM_DISK_SIZE_MB=$3

IMG=/crud/hcp_uml_guest.img

echo_blue() {
    local font_blue="\033[94m"
    local font_bold="\033[1m"
    local font_end="\033[0m"

    echo -e "\n${font_blue}${font_bold}${1}${font_end}"
}

echo_blue "[Create disk image]"
[ -z "${VM_DISK_SIZE_MB}" ] && VM_DISK_SIZE_MB=1024
VM_DISK_SIZE_SECTOR=$(expr $VM_DISK_SIZE_MB \* 1024 \* 1024 / 512)
dd if=/dev/zero of=${IMG} bs=${VM_DISK_SIZE_SECTOR} count=512

echo_blue "\n[Format image with ext4]"
mkfs.ext4 ${IMG}

echo_blue "\n[Mounting ext4 partition by loopback]"
losetup -D
LOOPDEVICE=$(losetup -f)
echo -e "\n[Using ${LOOPDEVICE} loop device]"
losetup ${LOOPDEVICE} ${IMG}
mkdir -p /tmpmnt
mount -t auto ${LOOPDEVICE} /tmpmnt/

echo_blue "[Copy directory structure to partition]"
cp -a /poo/. /tmpmnt/

#echo_blue "[Setup extlinux]"
#extlinux --install /tmpmnt/boot/
#cp /syslinux.cfg /tmpmnt/boot/syslinux.cfg
#rm /tmpmnt/.dockerenv

echo_blue "[Unmount]"
umount /tmpmnt
losetup -D

[ "${UID_HOST}" -a "${GID_HOST}" ] && chown ${UID_HOST}:${GID_HOST} ${IMG}
