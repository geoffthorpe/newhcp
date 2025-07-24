#!/bin/bash

while true; do

	kinit -C FILE:/pkinit_identity.pem alicia ssh -l alicia \
		sshd.x1.hcphacking.xyz echo "success" \
		|| (echo "fail" && exit 1) \
		|| exit 1
	sleep 1

done
