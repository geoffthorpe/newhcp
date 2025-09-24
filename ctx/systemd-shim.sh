#!/bin/bash

set -e

cd /
if [[ -d /hosthack ]]; then
	ln -s /hosthack/_env
	source /_env/env
	hostname $HOSTNAME
	ln -s /hosthack/hcp
	ln -s /hosthack/usecase
	ln -s /hosthack/_usecase
	tpmname=$(cd hosthack && ls | grep tpm_ 2>/dev/null || true)
	if [[ -n "$tpmname" && -d "/hosthack/$tpmname" ]]; then
		ln -s /hosthack/$tpmname
	fi
	if [[ -f /hosthack/ca_default ]]; then
		ln -s /hosthack/ca_default
	fi
	if [[ -f /hosthack/verifier_asset ]]; then
		ln -s /hosthack/verifier_asset
	fi
	if [[ -f /hosthack/cred_healthhttpsclient ]]; then
		ln -s /hosthack/cred_healthhttpsclient
	fi
fi

/hcp/python/hcp/tool/launcher.py

# Once the launcher exits, that's our cue to tear down
shutdown -h now
