#!/bin/bash

count=0
while true; do

	RES=$(kinit -C FILE:/pkinit_identity.pem alicia ssh -l alicia \
		sshd.x1.hcphacking.xyz echo "success") \
		&& [[ $RES == "success" ]] \
		|| (echo "fail" && exit 1) \
		|| exit 1
	sleep 1
	count=$((count+1))
	if [[ $count -eq 60 ]]; then
		echo "ssh client checks still succeeding"
		count=0
	fi

done
