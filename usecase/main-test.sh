#!/bin/bash

set -e

[[ -z $TOP ]] && echo "Fail: must export TOP=\$(pwd)!" && exit 1 || true

[[ -z $PROJECT ]] && export PROJECT=$(basename $(pwd)) && \
	echo "WARN: no PROJECT set, defaulting to '$PROJECT'"
DCFLAGS="-p $PROJECT"

DOMAIN=$(jq -r .vars.domain usecase/fleet.json)

QEMUSUPPORT=$(make qemusupport > /dev/null 2>&1 && echo yes || echo no)
echo "QEMU support = $QEMUSUPPORT"

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
		FLAGS="$FLAGS -iT --rm"
	elif [[ $_command == "down" ]]; then
		FLAGS="$FLAGS -v --remove-orphans"
	elif [[ $_command == "exec" ]]; then
		true
	elif [[ $_command == "execT" ]]; then
		_command="exec"
		FLAGS="$FLAGS -iT"
		Q=yes
		OUT=/dev/stdout
	else
		echo "Error: unknown cmd: $_command" >&2
		exit 1
	fi

	[[ -n $Q ]] || echo "--> docker compose $DCFLAGS $_command $FLAGS $@"
	docker compose $DCFLAGS $_command $FLAGS $@ > $OUT 2> $ERR && \
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

echo "Creating TPMs"
do_run run orchestrator -a -c

echo "Starting core attestsvc service"
do_run up attestsvc

echo "Starting enrollsvc TPM"
do_run up enrollsvc_tpm

echo "Waiting for enrollsvc TPM to advertise ek.pub"
do_run run enrollsvc \
	/hcp/python/hcp/tool/waitTouchfile.py "/tpmsocket_enrollsvc/tpm.files/ek.pub"

echo "Self-enrolling enrollsvc TPM"
do_run run enrollsvc bash <<EOF
hash=\$(openssl sha256 -r "/tpmsocket_enrollsvc/tpm.files/ek.pub")
path="/backend/db/\${hash:0:2}/\${hash:0:4}/\${hash:0:64}"
if [[ ! -d "\$path" ]]; then
	mkdir -p "\$path"
	echo -n "\${hash:0:64}" > "\$path/ekpubhash"
	cp "/tpmsocket_enrollsvc/tpm.files/ek.pub" "\$path/"
	cat "/usecase/fleet.json" \
		| jq .defaults.enroll_profile \
		| sed -e "s/{hostname}/enrollsvc.$DOMAIN/g" \
		> "\$path/profile"
	chown -R www-data "/backend/db/\${hash:0:2}"
fi
EOF

echo "Starting enrollsvc service"
do_run up enrollsvc

echo "Waiting for enrollsvc availability"
do_run run orchestrator \
	/hcp/python/hcp/tool/waitWeb.py \
		--cacert /ca_default \
		--clientcert /cred_enrollclient \
		--retries 10 --pause 1 \
		https://enrollsvc.$DOMAIN/healthcheck

echo "Enrolling kdc TPM"
do_run run orchestrator -e kdc

# KDC needs to be running before other hosts can attest (other hosts get
# keytabs during attestation...)
echo "Starting kdc"
do_run up kdc kdc_tpm

echo "Waiting for kdc to be available"
do_run exec attestsvc \
	/hcp/python/hcp/tool/waitWeb.py \
		--cacert /ca_default \
		--clientcert /cred_kdcclient \
		--retries 10 --pause 1 \
		https://kdc.$DOMAIN/healthcheck

echo "Enrolling the remaining TPMs"
do_run run orchestrator -e

# Note, we have arbitrarily chosen 'alicia' and the two 'auth_*'
# machines to use contenant TPMs (no sidecars)
echo "Starting remaining hosts"
do_run up shell shell_tpm alicia auth_certificate auth_kerberos

# By waiting for sshd launch, we implicitly wait for attestation.
echo "Waiting for alicia to be attested"
do_run exec alicia \
	/hcp/python/hcp/tool/waitTouchfile.py /assets/pkinit-client-alicia.pem
echo "Waiting for shell to be attested and sshd running"
do_run exec shell \
	/hcp/python/hcp/tool/waitTouchfile.py /run/sshd/started

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
# - we confirm that all of the above generated "shell.$DOMAIN".
echo "Running an SSO ssh session alicia -> shell"
result=$(do_run execT alicia /launcher bash <<EOF
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	ssh -l alicia shell.$DOMAIN bash <<DONE
hostname
DONE
EOF
)
result=$(echo $result|xargs)
if [[ $result != shell.$DOMAIN ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

# This time, we ssh back to alicia from within the ssh session to shell
echo "Running an SSO ssh boomerang alicia -> shell -> alicia"
result=$(do_run execT alicia /launcher bash <<EOF
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	ssh -l alicia shell.$DOMAIN bash <<DONE
ssh alicia.$DOMAIN bash <<INNER
hostname
INNER
DONE
EOF
)
result=$(echo $result|xargs)
if [[ $result != alicia.$DOMAIN ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

echo "Running a client-certificate authentication alicia -> auth_certificate"
result=$(docker compose exec alicia curl --silent --cacert /ca_default --cert /assets/https-client-alicia.pem https://certificate.auth.$DOMAIN/get | jq .is_secure)
if [[ $result != 'true' ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

echo "Running a kerberos-SPNEGO authentication alicia -> auth_kerberos"
result=$(do_run execT alicia /launcher bash <<EOF
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	curl --silent --cacert /ca_default --negotiate -u : https://kerberos.auth.$DOMAIN/get \
	| jq .is_secure
EOF
)
if [[ $result != 'true' ]]; then
	echo "Error, unexpected output: $result" >&2
	exit 1
fi

if [[ $QEMUSUPPORT == 'yes' ]]; then
	echo "Starting nfs (QEMU)"
	do_run up nfs
	echo "Waiting for nfs to be available"
	do_run exec nfs \
		/hcp/python/hcp/tool/waitTouchfile.py /tmp/vm.workload.running
	echo "Starting barton (QEMU)"
	do_run up barton
	echo "Starting catarina (QEMU)"
	do_run up catarina
	echo "Waiting for barton to be available"
	do_run exec barton \
		/hcp/python/hcp/tool/waitTouchfile.py /tmp/vm.workload.running
	echo "Waiting for catarina to be available"
	do_run exec catarina \
		/hcp/python/hcp/tool/waitTouchfile.py /tmp/vm.workload.running
	echo "NFS check: write home directory via barton"
	FOO=$RANDOM
	do_run execT alicia su -w HCP_CONFIG_MUTATE - alicia <<EOF
ssh barton.hcphacking.xyz bash -c "true;echo $FOO > ~/dingdong"
EOF
	echo "NFS check: read home directory via catarina"
	result=$(do_run execT alicia su -w HCP_CONFIG_MUTATE - alicia <<EOF
ssh catarina.hcphacking.xyz bash -c "true;cat ~/dingdong"
EOF
)
	if [[ $result != $FOO ]]; then
		echo "Error, I expected: $FOO" >&2
		echo "       I received: $result" >&2
		exit 1
	fi
fi

echo "Success"
