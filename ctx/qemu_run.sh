#!/bin/bash

# Copy the r/o VM image locally
cp /crud/hcp_caboodle_vm.img /myvm.img

# Create 1G swap file
dd if=/dev/zero of=/swapfile bs=1M count=1024
chmod 600 /swapfile
mkswap /swapfile

mkdir -p /_env

echo "export PYTHONPATH=$PYTHONPATH" > /_env/env
echo "export HCP_CONFIG_MUTATE=$HCP_CONFIG_MUTATE" >> /_env/env
echo "export HOSTNAME=$(hostname)" >> /_env/env

vde_switch --sock=/tmp/myswitch --daemon
# TODO: we should use vde_plug instead of slirpvde, apparently. But I couldn't
# get it to work.
slirpvde -sock=/tmp/myswitch -dhcp -daemon \
	-L 22:10.0.2.15:22 \
	-L 443:10.0.2.15:443
# vde_plug -d vde:///tmp/myswitch slirp:///tcpfwd=22:10.0.2.15:22/tcpfwd=443:10.0.2.15:443

mydrive="-drive file=/myvm.img,index=0,media=disk,format=raw "
mydrive+="-drive file=/swapfile,index=1,media=disk,format=raw "

# There are credentials that need to be mounted and sadly, the virtio mechanism only supports
# directories, not files. :-( We hack around this for now by mounting the entire filesystem and
# letting the VM create symlinks.
myvirtfs="-virtfs local,path=/,mount_tag=hosthack,security_model=passthrough,id=hosthack"

# Boot the VM image with 4G of RAM.
qemu-system-x86_64 -m 4G $mydrive $myvirtfs -nographic \
	-netdev vde,sock=/tmp/myswitch,id=myswitch -net nic,netdev=myswitch
