#!/bin/bash

# Copy the r/o VM image locally
cp /crud/hcp_caboodle_vm.img /myvm.img

# Create 1G swap file
dd if=/dev/zero of=/swapfile bs=1M count=1024
chmod 600 /swapfile
mkswap /swapfile

mkdir -p /_env

echo "export PYTHONPATH=$PYTHONPATH" > /_env/env
echo "export HCP_CONFIG_MUTATE=$VM_HCP_CONFIG_MUTATE" >> /_env/env
echo "export HOSTNAME=$(hostname)" >> /_env/env
echo "Set up VM 'env' file" >&2

vde_switch --sock=/tmp/myswitch --daemon
# TODO: we should use vde_plug instead of slirpvde, apparently. But I couldn't
# get it to work.
slirpvde -sock=/tmp/myswitch -dhcp -daemon \
	-L 22:10.0.2.15:22 \
	-L 443:10.0.2.15:443
# vde_plug -d vde:///tmp/myswitch slirp:///tcpfwd=22:10.0.2.15:22/tcpfwd=443:10.0.2.15:443
echo "Started VDE2 DHCP+DNS+NAT" >&2

mydrive="-drive file=/myvm.img,index=0,media=disk,format=raw "
mydrive+="-drive file=/swapfile,index=1,media=disk,format=raw "

# There are credentials that need to be mounted and sadly, the virtio mechanism only supports
# directories, not files. :-( We hack around this for now by mounting the entire filesystem and
# letting the VM create symlinks.
myvirtfs="-virtfs local,path=/,mount_tag=hosthack,security_model=passthrough,id=hosthack"

# The TPM2TOOLS_TCTI env-var will be of the form;
# TPM2TOOLS_TCTI=swtpm:path=/tpmsocket_<host>/tpm
#if [[ -n $TPM2TOOLS_TCTI ]]; then
#	tpmpath=$(echo "$TPM2TOOLS_TCTI" | sed -e "s/^.*path=//")
#	mytpm="-chardev socket,id=chrtpm,path=$tpmpath "
#	mytpm+="-tpmdev emulator,id=tpm0,chardev=chrtpm "
#	mytpm+="-device tpm-tis,tpmdev=tpm0"
#fi

# Boot the VM image with 4G of RAM.
cmd="qemu-system-x86_64 -m 4G -enable-kvm "
cmd+="$mydrive $myvirtfs -nographic "
#cmd+="$mytpm "
cmd+="-netdev vde,sock=/tmp/myswitch,id=myswitch -net nic,netdev=myswitch "
echo "Launching: $cmd" >&2
$cmd
