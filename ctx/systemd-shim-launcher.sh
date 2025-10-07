#!/bin/bash

set -e

source /_env/env

echo "HCP: backgrounding launcher" >&2
/hcp/python/hcp/tool/launcher.py "$@" &

echo "HCP: waiting for readiness" >&2
while [[ ! -f /hosthack/tmp/vm.workload.running ]]; do
	sleep 1
done

echo "HCP: ready, notifying systemd" >&2
systemd-notify --ready

echo "HCP: waiting for launcher to exit" >&2
wait

echo "HCP: launcher exited, taking down the VM" >&2
shutdown -h now
