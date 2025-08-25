#!/bin/bash

source /hcp/common/hcp.sh

# Usage: callback <pre|post> <asset> <path>
if [[ $# != 3 ]]; then
	echo "Error, wrong number of arguments" >&2
	exit 1
fi
phase=$1
asset=$2
path=$3

if [[ $phase == "pre" ]]; then

	if [[ "$asset" == "keytab-http" ]]; then
		echo "keytab-http: chown to 'www-data', chmod to 0640"
		chown www-data "$path"
		chmod 0640 "$path"
	elif [[ $asset = pkinit-client-* ]] || [[ $asset = https-client-* ]]; then
		name=$(echo "$asset" | sed -e "s/^.*-client-//" | sed -e "s/.pem\$//")
		if [[ -n "$name" ]] && [[ -d "/home/$name" ]]; then
			echo "$asset: chown to '$name'"
			chown "$name" "$path"
		else
			echo "Ignoring"
		fi
	fi

elif [[ $phase == "post" ]]; then

	if [[ "$asset" == "https-server-$(hostname).pem" ]]; then
		if [[ -f "/run/$HOSTNAME/nginx.pid" ]]; then
			PID=$(cat "/run/$HOSTNAME/nginx.pid")
			if [[ -n $PID ]] && $(ps -p $PID > /dev/null 2>&1); then
				echo "sending SIGHUP to $PID"
				kill -s HUP $PID
			fi
		fi
	elif [[ $asset = pkinit-kdc-* ]]; then
		if ps -C kdc > /dev/null 2>&1; then
			# This is nuts. KDC should _at least_ support a PID
			# file so we know what to signal! Also, it should
			# support a continuity-preserving HUP handler, rather
			# than exiting and needing to be restarted!
			echo "sending SIGHUP to all 'kdc' processes?!?!"
			killall -s HUP kdc
		fi
	fi

else
	echo "Bad phase: $phase" >&2
	exit 1
fi
