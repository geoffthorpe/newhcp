#!/bin/bash

set -e

echo "Running basic sanity test"

[[ -n $V ]] && OUT=/dev/stdout || OUT=/dev/null
[[ -n $Q ]] && ERR=/dev/null || ERR=/dev/stderr

do_run() {
	echo "$1"
	[[ -n $Q ]] || echo "--> $2"
	$2 > $OUT 2> $ERR && \
		([[ -n $Q ]] || echo "--> SUCCESS") || \
		exit 1
}

do_exit() {
	(Q=1 do_run "Cleaning up" "docker-compose down -v")
}

trap do_exit EXIT

do_run "Starting basic services" \
	"docker-compose up -d emgmt emgmt_pol erepl arepl ahcp aclient_tpm"
do_run "Fail a premature attestation" \
	"docker-compose run aclient /hcp/tools/run_client.sh -w"
do_run "Create and enroll aclient's TPM" \
	"docker-compose run orchestrator /hcp/tools/run_orchestrator.sh -c -e aclient"
do_run "Successful attestation" \
	"docker-compose run aclient /hcp/tools/run_client.sh -R 10 -P 1"
