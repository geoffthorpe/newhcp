#!/bin/bash

set -e

[[ -z $TOP ]] && echo "Fail: must export TOP=\$(pwd)!" && exit 1 || true

[[ -z $PROJECT ]] && export PROJECT=$(basename $(pwd)) && \
	echo "WARN: no PROJECT set, defaulting to '$PROJECT'"
DCFLAGS="-p $PROJECT"

DOMAIN=$(jq -r .vars.domain usecase/fleet.json)

echo "Running bringup"

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

echo "Success"
