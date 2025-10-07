#!/bin/bash

if [[ -z $KRB5CCNAME ]]; then
	ME=$(whoami)
	if [[ -f /assets/pkinit-client-$ME.pem ]]; then
		echo "Auto-running kinit to get TGT for '$ME'" >&2
		exec /install-heimdal/bin/kinit -C FILE:/assets/pkinit-client-$ME.pem $ME bash "$@"
	else
		echo "No kinit/TGT available for '$ME'" >&2
	fi
fi

exec bash "$@"
