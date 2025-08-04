#!/bin/bash

source /hcp/common/hcp.sh

echo "cb_attestclient.sh $1"

HOSTNAME=$(hostname)
if [[ "$1" == "https-server-$HOSTNAME.pem" ]]; then
	if [[ -f "/run/$HOSTNAME/nginx.pid" ]]; then
		PID=$(cat "/run/$HOSTNAME/nginx.pid")
		if [[ -n $PID ]] && $(ps -p $PID > /dev/null 2>&1); then
			echo "sending SIGHUP to $PID"
			kill -sHUP $PID
		fi
	fi
fi
