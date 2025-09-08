#!/bin/bash
# Full disclosure, this script is modified from the ultra-useful
# example I found at; https://github.com/iximiuz/docker-to-linux

set -e

UID_HOST=$1
GID_HOST=$2
VM_DISK_SIZE_MB=$3

IMG=/crud/hcp_caboodle_vm.img

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

echo_blue "[Make partition]"
sfdisk ${IMG} <<EOF
label: dos
label-id: 0xdeadbeef
unit: sectors

linux-part : start=2048, type=83, bootable
EOF

echo_blue "\n[Format partition with ext4]"
losetup -D
LOOPDEVICE=$(losetup -f)
echo -e "\n[Using ${LOOPDEVICE} loop device]"
losetup -o $(expr 512 \* 2048) ${LOOPDEVICE} ${IMG}
mkfs.ext4 ${LOOPDEVICE}

echo_blue "[Copy directory structure to partition]"
mkdir -p /tmpmnt
mount -t auto ${LOOPDEVICE} /tmpmnt/
cp -a /poo/. /tmpmnt/

echo_blue "[Setup extlinux]"
extlinux --install /tmpmnt/boot/
cp /syslinux.cfg /tmpmnt/boot/syslinux.cfg
rm /tmpmnt/.dockerenv

echo_blue "[Unmount]"
umount /tmpmnt
losetup -D

echo_blue "[Write syslinux MBR]"
dd if=/usr/lib/syslinux/mbr/mbr.bin of=${IMG} bs=440 count=1 conv=notrunc

#echo_blue "[Convert to qcow2]"
#qemu-img convert -c ${IMG} -O qcow2 ${IMG}.qcow2

[ "${UID_HOST}" -a "${GID_HOST}" ] && chown ${UID_HOST}:${GID_HOST} ${IMG} #${IMG}.qcow2

#rm -r /os/${DISTR}.dir
