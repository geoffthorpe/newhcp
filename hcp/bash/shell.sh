#!/bin/bash

if [[ -z $KRB5CCNAME ]]; then
	ME=$(whoami)
	if [[ -f /assets/pkinit-client-$ME.pem ]]; then
		echo "Auto-running kinit to get TGT for '$ME'" >&2
		if [[ -d /install-kstart ]]; then
			exec /install-kstart/bin/k5start -q -X X509_user_identity=FILE:/assets/pkinit-client-$ME.pem $ME -- bash "$@"
		else
			exec /install-heimdal/bin/kinit -C FILE:/assets/pkinit-client-$ME.pem $ME bash "$@"
		fi
	else
		echo "No kinit/TGT available for '$ME'" >&2
	fi
fi

exec bash "$@"
