#!/bin/bash

set -e

[[ -z $TOP ]] && echo "Fail: must export TOP=\$(pwd)!" && exit 1 || true

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

[[ -n $NOTRAP ]] || trap do_exit EXIT

STARTSERVICES="policy emgmt erepl arepl ahcp aclient_tpm"
STARTSERVICES="$STARTSERVICES kdc_primary kdc_secondary"
STARTSERVICES="$STARTSERVICES kdc_primary_tpm kdc_secondary_tpm"
STARTSERVICES="$STARTSERVICES ssherver workstation1 bigbrother www"
STARTSERVICES="$STARTSERVICES ssherver_tpm workstation1_tpm www_tpm"
do_run "Starting basic services" \
	up "$STARTSERVICES"
do_run "Fail a premature attestation" \
	run "aclient /hcp/tools/run_client.sh -w"
do_run "Create and enroll TPMs for aclient, kdc_primary, kdc_secondary" \
	run "orchestrator /hcp/tools/run_orchestrator.sh -c -e aclient kdc_primary kdc_secondary"
do_run "Successful attestation" \
	run "aclient /hcp/tools/run_client.sh -R 10 -P 1"
do_run "Wait for secondary KDC to have realm replicated" \
	exec "kdc_secondary /hcp/kdcsvc/realm_healthcheck.py -R 10 -P 1"
do_run "Create and enroll remaining TPMs" \
	run "orchestrator /hcp/tools/run_orchestrator.sh -c -e"
do_run "Wait for ssherver to be ready" \
	exec "ssherver /hcp/sshd.py --healthcheck -R 10 -P 1"
do_run "Wait for workstation1 to be ready" \
	exec "workstation1 /hcp/attested.py -R 10 -P 1"
sso_cmd="/install-heimdal/bin/kinit -C FILE:/home/luser/.hcp/pkinit/user-luser-key.pem luser"
sso_cmd="$sso_cmd ssh -l luser -p 2222 ssherver.hcphacking.xyz echo"
sso_cmd="$sso_cmd \"This output indicates successful SSO+ssh\""
do_run "Do SSO login from workstation1 to ssherver as 'luser'" \
	exec "workstation1 $sso_cmd"
do_run "Wait for bigbrother to be ready" \
	exec "bigbrother /hcp/attested.py -R 10 -P 1"
sso_cmd="/install-heimdal/bin/kinit -C FILE:/root/.hcp/pkinit/user-root-key.pem root"
sso_cmd="$sso_cmd ssh -l root -p 2222 ssherver.hcphacking.xyz echo"
sso_cmd="$sso_cmd \"If root==\$(whoami) then success\""
do_run "Do SSO login from bigbrother to ssherver as 'root'" \
	exec "bigbrother $sso_cmd"
