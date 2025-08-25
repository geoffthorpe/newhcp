#!/bin/bash

set -e

[[ -z $TOP ]] && echo "Fail: must export TOP=\$(pwd)!" && exit 1 || true

[[ -z $PROJECT ]] && export PROJECT=$(basename $(pwd)) && \
	echo "WARN: no PROJECT set, defaulting to '$PROJECT'"
DCFLAGS="-p $PROJECT"

echo "Running basic sanity test"

[[ -n $V ]] && OUT=/dev/stdout || OUT=/dev/null
[[ -n $Q ]] && ERR=/dev/null || ERR=/dev/stderr

do_run() {
	FLAGS=""
	_command=$1
	shift
	BACKQ=$Q
	BACKOUT=$OUT
	if [[ $_command == "up" ]]; then
		FLAGS="$FLAGS -d"
	elif [[ $_command == "run" ]]; then
		FLAGS="$FLAGS --rm"
	elif [[ $_command == "down" ]]; then
		FLAGS="$FLAGS -v"
	elif [[ $_command == "exec" ]]; then
		true
	elif [[ $_command == "execT" ]]; then
		_command="exec"
		FLAGS="$FLAGS -T"
		Q=yes
		OUT=/dev/stdout
	else
		echo "Error: unknown cmd: $_command" >&2
		exit 1
	fi

	[[ -n $Q ]] || echo "--> docker-compose $DCFLAGS $_command $FLAGS $@"
	docker-compose $DCFLAGS $_command $FLAGS $@ > $OUT 2> $ERR && \
		([[ -n $Q ]] || echo "--> SUCCESS") || \
		exit 1
	Q=$BACKQ
	OUT=$BACKOUT
}

do_exit() {
	(Q=1 do_run down "")
}

[[ -n $NOTRAP ]] || trap do_exit EXIT

echo "Destroying any existing state"
do_run down

echo "Starting core attestsvc and enrollsvc services"
do_run up attestsvc enrollsvc

echo "Creating TPMs"
do_run run orchestrator -c

# We cheat. By creating TPMs before enrolling them, we almost certainly
# guarantee that enrollsvc is ready before we talk to it. By rights,
# there should be a step here to wait for enrollsvc to be ready.
echo "Enrolling KDC TPMs"
do_run run orchestrator -e kdc_primary kdc_secondary

# KDCs need to be running before other hosts can attest (other hosts get
# keytabs during attestation...)
echo "Starting KDCs"
do_run up kdc_primary kdc_primary_tpm kdc_secondary kdc_secondary_tpm

# More cheating. By enrolling more TPMs after starting the KDCs, we give the
# KDCs plenty of time to be ready before we start hosts that will attest. By
# rights we should poll for the secondary to be ready.
echo "Enrolling the other TPMs"
do_run run orchestrator -e

echo "Starting other hosts"
do_run up shell shell_tpm alicia alicia_tpm \
	auth_certificate auth_certificate_tpm \
	auth_kerberos auth_kerberos_tpm


# Now we can't cheat, we have to wait. NB, by waiting for sshd launch, we
# implicitly wait for attestation.
echo "Waiting for alicia to be attested"
do_run exec alicia \
	/hcp/python/HcpToolWaitTouchfile.py /assets/pkinit-client-alicia.pem
echo "Waiting for shell to be attested and sshd running"
do_run exec shell \
	/hcp/python/HcpToolWaitTouchfile.py /run/sshd/started

# The next little blob of script requires some explanation.
# - we start a bash instance on 'alicia' and feed commands to it.
#   - load environment (so 'kinit' is in the PATH, etc)
#   - run 'kinit' using our PKINIT client cert to get a TGT. This is the
#     "single sign-on" (SSO) event. (Or "zero sign-on" if you prefer, because
#     the client cert is obtained non-interactively.)
#     - kinit runs a subcommand and stays alive as long as the subcommand is
#       running.
#     - kinit will reauthenticate over time, as required to update the TGT,
#       using newer client certs as they get updated by attestation.
#     - the subcommand run by kinit is an ssh connection to 'shell';
#       - the ssh-connection authenticates automatically using the TGT in
#         kinit, hence SSO.
#       - once authenticated, the ssh connection starts a bash shell on 'shell'
#         and we feed commands to it.
#         - Run 'hostname', the output will return through the ssh shell.
# - pass the output through 'xargs' (a trick to strip whitespace)
# - we confirm that all of the above generated "shell.hcphacking.xyz".
echo "Running an SSO ssh session alicia -> shell"
result=$(do_run execT alicia bash <<EOF
source /hcp/common/hcp.sh
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	ssh -l alicia shell.hcphacking.xyz bash <<DONE
hostname
DONE
EOF
)
result=$(echo $result|xargs)
if [[ $result != 'shell.hcphacking.xyz' ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

echo "Running a client-certificate authentication alicia -> auth_certificate"
result=$(docker-compose exec alicia curl --cacert /ca_default --cert /assets/https-client-alicia.pem https://certificate.auth.hcphacking.xyz/get | jq .is_secure)
if [[ $result != 'true' ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

echo "Running a kerberos-SPNEGO authentication alicia -> auth_kerberos"
result=$(do_run execT alicia bash <<EOF
source /hcp/common/hcp.sh
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	curl --cacert /ca_default --negotiate -u : https://kerberos.auth.hcphacking.xyz/get \
	| jq .is_secure
EOF
)
if [[ $result != 'true' ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

echo "Success"
