#!/bin/bash

# For interactive shells, don't "set -e", it can be (more than) mildly
# inconvenient to have the shell exit any time you run a command that returns a
# non-zero status code. It's good discipline for scripts though.
[[ -z $PS1 ]] && set -e

if [[ -f /_env/env ]]; then
	source /_env/env
fi

hcp_default_log_level=1
hcp_current_log_level=0

if [[ -n $VERBOSE ]]; then
	hcp_current_log_level=$VERBOSE
fi

hlog() {
	if [[ $1 -gt $hcp_current_log_level ]]; then
		return
	fi
	echo -E "$2" >&2
	sync
}

log() {
	hlog $hcp_default_log_level "$1"
}

bail() {
	hlog 0 "FAIL: $1"
	exit 1
}

# Our web-handling code (particularly for enrollsvc) relies heavily on
# processing that executes child processes synchronously. This includes using
# tpm tools, safeboot scripts, "genprogs", and so forth. Furthermore, the
# webhandlers are typically running as a low-priv userid to protect the fallout
# from a successful exploit of anything in that stack (uwsgi, nginx, flask, etc) and
# they defer "real work" via a curated sudo call to
# run those tasks as a different non-root user. Throughout this handling, we rely on
# two assumptions:
# 1 - if the operation is successful, then the response to the web request is
#     whatever got written to stdout (typically a JSON-encoding), and
# 2 - the concept of what "successful" means is conveyed via exit codes, and if
#     that results in failure then whatever is written to stdout is _not_ sent
#     to the client. (In this way output can be produced sequentially knowing
#     that if an error occurs later on the output doesn't need to be
#     "un-written".)
# We want to follow the http model, in that 2xx codes represent success, 4xx
# codes represent request problems, 5xx codes represent server issues, etc.
# This doesn't map well to the posix conventions for process exit codes. For
# one, we have more than one success code (we only need 200 and 201, but that's
# more than one). Also, exit codes are 8-bit, so we can't use the http status
# codes literally as process exit codes. We use the following conventions
# instead, and that's why we have the following functions and definitions.
#
#   http codes   ->   exit codes   ->   http codes
#       200               20               200   (most success cases)
#       201               21               201   (success creating a record)
#       400               40               400   (malformed input)
#       401               41               401   (authentication failure)
#       403               43               403   (authorization failure)
#       404               44               404   (resource not found)
#       500               50               500   (misc server failure)
#       xxx               49               500   (unexpected http code)
#                          0               200   (posix success, not http-aware)
#                         xx               500   (unexpected exit code)
#
declare -A ahttp2exit=(
	[200]=20, [201]=21,
	[400]=40, [401]=41, [403]=43, [404]=44,
	[500]=50)
declare -A aexit2http=(
	[20]=200, [21]=201,
	[40]=400, [41]=401, [43]=403, [44]=404,
	[50]=500, [49]=500, [0]=200)
aahttp2exit="${!ahttp2exit[@]}"
function http2exit {
	val=""
	for key in $aahttp2exit; do
		if [[ $1 == $key ]]; then
			val=${ahttp2exit[$key]}
			break
		fi
	done
	if [[ -n $val ]]; then
		echo $val
		return
	fi
	echo 49
}
aaexit2http="${!aexit2http[@]}"
function exit2http {
	val=""
	for key in $aaexit2http; do
		if [[ $1 == $key ]]; then
			val=${aexit2http[$key]}
			break
		fi
	done
	if [[ -n $val ]]; then
		echo $val
		return
	fi
	echo 500
}

# Until all the relevant code can migrate from bash to python, we need some
# equivalent functionality. This mimics the "hcp_config_*" functions in
# hcp.common.py.
function normalize_path {
	if [[ $1 =~ ^\. ]]; then
		mypath=$1
	else
		mypath=".$1"
	fi
	echo "$mypath"
}
function hcp_config_extract {
	if [[ -z $HCP_CONFIG_FILE ]]; then
		bail "!HCP_CONFIG_FILE"
	fi
	mypath=$(normalize_path "$1")
	result=$(cat "$HCP_CONFIG_FILE" | jq -r "$mypath")
	hlog 3 "hcp_config_extract: $HCP_CONFIG_FILE,$mypath"
	echo "$result"
}

function add_env_path {
	if [[ -n $1 ]]; then
		echo "$1:$2"
	else
		echo "$2"
	fi
}

function add_install_path {
	local D=$1
	if [[ ! -d $D ]]; then return; fi
	if [[ -d "$D/bin" ]]; then
		export PATH=$(add_env_path "$PATH" "$D/bin")
	fi
	if [[ -d "$D/sbin" ]]; then
		export PATH=$(add_env_path "$PATH" "$D/sbin")
	fi
	if [[ -d "$D/libexec" ]]; then
		export PATH=$(add_env_path "$PATH" "$D/libexec")
	fi
	if [[ -d "$D/lib" ]]; then
		export LD_LIBRARY_PATH=$(add_env_path \
			"$LD_LIBRARY_PATH" "$D/lib")
		if [[ -d "$D/lib/python/dist-packages" ]]; then
			export PYTHONPATH=$(add_env_path \
				"$PYTHONPATH" "$D/lib/python/dist-packages")
		fi
	fi

}

# The above stuff (apart from "set -e") is all function-definition, here we
# actually _do_ something when you source this file.

for i in $(find / -maxdepth 1 -mindepth 1 -type d -name "install-*"); do
	add_install_path "$i"
done

if [[ -z $HCP_CONFIG_FILE ]]; then
	echo "Auto-running launcher to get HCP environment" >&2
	exec /launcher /bin/bash "$@"
fi

envjson=$(hcp_config_extract ".env")
if [[ $envjson != 'null' ]]; then
	envjson_keys=$(echo "$envjson" | jq 'keys[]')
	for i in $envjson_keys; do
		j=$(echo "$i" | jq -r .)
		v=$(echo "$envjson" | jq -r ".$j")
		export $j="$v"
	done
fi
