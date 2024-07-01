#!/bin/bash

set -e

echo "Running basic sanity test"

[[ -n $V ]] && OUT=/dev/stdout || OUT=/dev/null
[[ -n $Q ]] && ERR=/dev/null || ERR=/dev/stderr

do_run() {
	echo "$1"
	FLAGS=""
	if [[ $2 == "up" ]]; then
		FLAGS="$FLAGS -d"
	elif [[ $2 == "run" ]]; then
		FLAGS="$FLAGS --rm"
	elif [[ $2 == "down" ]]; then
		FLAGS="$FLAGS -v"
	elif [[ $2 == "exec" ]]; then
		true
	else
		echo "Error: unknown docker-compose cmd: $2" >&2
		exit 1
	fi

	[[ -n $Q ]] || echo "--> docker-compose $2 $FLAGS $3"
	docker-compose $2 $FLAGS $3 > $OUT 2> $ERR && \
		([[ -n $Q ]] || echo "--> SUCCESS") || \
		exit 1
}

do_exit() {
	(Q=1 do_run "Cleaning up" down "")
}

trap do_exit EXIT

do_run "Starting basic services" \
	up "emgmt emgmt_pol erepl arepl ahcp aclient_tpm kdc_primary_tpm kdc_secondary_tpm kdc_primary_pol kdc_secondary_pol"
do_run "Fail a premature attestation" \
	run "aclient /hcp/tools/run_client.sh -w"
do_run "Create and enroll TPMs for aclient, kdc_primary, kdc_secondary" \
	run "orchestrator /hcp/tools/run_orchestrator.sh -c -e aclient kdc_primary kdc_secondary"
do_run "Successful attestation" \
	run "aclient /hcp/tools/run_client.sh -R 10 -P 1"
do_run "Starting primary and secondary KDCs" \
	up "kdc_primary kdc_secondary"
do_run "Wait for secondary KDC to have realm replicated" \
	exec "kdc_secondary /hcp/kdcsvc/realm_healthcheck.py -R 10 -P 1"
