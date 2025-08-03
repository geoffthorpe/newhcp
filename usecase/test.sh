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

echo "Success"
