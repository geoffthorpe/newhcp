#!/bin/bash

while true; do
	kadmin --config-file=/x1_kdc/etc/kdc.conf -l \
		ext_keytab --keytab=/x1_backdoor/keytab.new \
		host/sshd.x1.hcphacking.xyz@HCPHACKING.XYZ \
		&& mv -f /x1_backdoor/keytab.new /x1_backdoor/keytab \
		&& ktutil --keytab=/x1_backdoor/keytab list \
		&& sleep 15 || (echo "fail" && exit 1) || exit 1
done
