#!/bin/bash

# For interactive shells, don't "set -e", it can be (more than) mildly
# inconvenient to have the shell exit any time you run a command that returns a
# non-zero status code. It's good discipline for scripts though.
[[ -z $PS1 ]] && set -e

WHOAMI=$(whoami)

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
function hcp_config_extract_or {
	if [[ -z $HCP_CONFIG_FILE ]]; then
		bail "!HCP_CONFIG_FILE"
	fi
	# We need a string that will never occur and yet contains no odd
	# characters that will screw up 'jq'. Thankfully this is just a
	# temporary thing until bash->python is complete.
	s="astringthatneveroccursever"
	mypath=$(normalize_path "$1")
	result=$(cat "$HCP_CONFIG_FILE" | jq -r "$mypath // \"$s\"")
	if [[ $result == $s ]]; then
		result=$2
	fi
	log "hcp_config_extract_or: $HCP_CONFIG_FILE,$mypath,$2"
	echo "$result"
}

function hcp_config_user_init {
	USERNAME=$1
	if [[ ! -d /home/$USERNAME ]]; then
		bail "No directory at /home/$USERNAME"
	fi
	if [[ ! -f /home/$USERNAME/hcp_config ]]; then
		cat > /home/$USERNAME/hcp_config <<EOF
export HCP_CONFIG_FILE="$HCP_CONFIG_FILE"
EOF
		chown $USERNAME /home/$USERNAME/hcp_config
	fi
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

# Utility for adding a PEM file to the set of trust roots for the system. This
# can be called multiple times to update (if changed) the same trust roots, eg.
# when used inside an attestation-completion callback. As such, $2 and $3
# specify a CA-store subdirectory and filename (respectively) to use for the
# PEM file being added. If the same $2 and $3 arguments are provided later on,
# it is assumed to be an update to the same trust roots.
# $1 = file containing the trust roots
# $2 = CA-store subdirectory (can be multiple layers deep)
# $3 = CA-store filename
function add_trust_root {
	if [[ ! -f $1 ]]; then
		echo "Error, no '$1' found" >&2
		return 1
	fi
	echo "Adding '$1' as a trust root"
	if [[ -f "/usr/share/ca-certificates/$2/$3" ]]; then
		if cmp "$1" "/usr/share/ca-certificates/$2/$3"; then
			echo "  - already exists and hasn't changed, skipping"
			return 0
		fi
		echo "  - exists but has changd, overriding"
		cp "$1" "/usr/share/ca-certificates/$2/$3"
		update-ca-certificates
	else
		echo "  - no prior trust root, installing"
		mkdir -p "/usr/share/ca-certificates/$2"
		cp "$1" "/usr/share/ca-certificates/$2/$3"
		echo "$2/$3" >> /etc/ca-certificates.conf
		update-ca-certificates
	fi
}

# The above stuff (apart from "set -e") is all function-definition, here we
# actually _do_ something when you source this file.
# TODO: this should be removed, and instead we should consume 'env' properties
# from the configuration.

for i in $(find / -maxdepth 1 -mindepth 1 -type d -name "install-*"); do
	add_install_path "$i"
done
if [[ -z $HCP_CONFIG_FILE ]]; then
	echo "Auto-running launcher to get HCP environment" >&2
	exec /launcher bash
fi
if [[ -z $KRB5CCNAME ]]; then
	ME=$(whoami)
	if [[ -f /assets/pkinit-client-$ME.pem ]]; then
		echo "Auto-running kinit to get TGT for '$ME'" >&2
		exec kinit -C FILE:/assets/pkinit-client-$ME.pem $ME bash
	else
		echo "No kinit/TGT available for '$ME'" >&2
	fi
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
