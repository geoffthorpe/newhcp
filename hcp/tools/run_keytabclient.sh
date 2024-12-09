#!/bin/bash

source /hcp/common/hcp.sh

ID=$(hcp_config_extract ".id")
DOMAIN=$(hcp_config_extract ".default_domain")
URL=$(hcp_config_extract ".keytabclient.url")
GLOBAL=$(hcp_config_extract ".keytabclient.global")
# So longs as we're bash, parsing a JSON list will always be a
# whitespace-handling whack-a-mole. For now, we assume that the list of
# callbacks simply mustn't have spaces. If you want spaces, convert this script
# to python.
function set_callbacks {
	JSON_CALLBACKS=$1
	CALLBACKS=($(jq -r '.[]' <<< "$JSON_CALLBACKS"))
}
set_callbacks "$(hcp_config_extract_or '.keytabclient.callbacks' '[]')"
TFILE=$(hcp_config_extract ".keytabclient.touchfile" "")

retries=0
pause=1
VERBOSE=0
wantfail=0

usage() {
	((${1:-1} == 0)) || exec 1>&2
	pager=cat
	if [[ -t 0 && -t 1 && -t 2 ]]; then
		if [[ -z ${PAGER:-} ]] && type less >/dev/null 2>&1; then
			pager=less
		elif [[ -z ${PAGER:-} ]] && type more >/dev/null 2>&1; then
			pager=more
		elif [[ -n ${PAGER:-} ]]; then
			pager=$PAGER
		fi
	fi
	$pager <<EOF
Usage: $PROG [OPTIONS] [names ...]

  Runs the keytab client.

  Options:

    -h               This message
    -v               Verbose
    -w               'want failure', inverts success/failure.
    -R <num>         Number of retries before failure
        (default: $retries)
    -P <seconds>     Time between retries
        (default: $pause)
    -U <url>         Keytab URL
        (default: $(test -n "$URL" && echo "$URL" || echo "None"))
    -C <callbacks>   JSON list of callbacks to execute (eg. \"[ \\\"/bin/foo\\\", \\\"/your/cb\\\" ]\")"
        (default: $JSON_CALLBACKS )
    -Z <path>        Touchfile once complete
        (default: $TFILE)
EOF
	exit "${1:-1}"
}

while getopts +:R:P:U:T:A:C:Z:hvw opt; do
case "$opt" in
R)	retries="$OPTARG";;
P)	pause="$OPTARG";;
U)	URL="$OPTARG";;
C)	set_callbacks "$OPTARG";;
Z)	TFILE="$OPTARG";;
h)	usage 0;;
v)	((VERBOSE++)) || true;;
w)	wantfail=1;;
*)	echo >&2 "Unknown option: $opt"; usage;;
esac
done
shift $((OPTIND - 1))

if ((VERBOSE > 0)); then
	cat >&2 <<EOF
Starting $PROG:
 - retries=$retries
 - pause=$pause
 - wantfail=$wantfail
 - onlyenroll=$onlyenroll
 - onlycreate=$onlycreate
 - VERBOSE=$VERBOSE
 - URL=$URL
 - JSON_CALLBACKS=$JSON_CALLBACKS
 - TFILE=$TFILE
EOF
fi

if [[ -z $URL ]]; then
	echo "Error, no attestation URL configured" >&2
	exit 1
fi
if [[ $wantfail != 0 && $retries != 0 ]]; then
	echo "Error, using -w and setting -R non-zero are incompatible options" >&2
	exit 1
fi

if [[ ! -f /etc/krb5.conf && ! -f $KRB5_CONFIG ]]; then
	echo "Error, no krb5.conf found" >&2
	exit 1
fi

# We store some stuff we should clean up, and we also grab a global lockfile to
# prevent two of these clients running in parallel, so use a trap.
my_lockfile=/tmp/lockfile.attestclient.$ID
if ! lockfile -1 -r 0 $my_lockfile; then
	echo "Waiting for parallel clients to exit..."
	lockfile -1 -r 30 -l 120 -s 5 $my_lockfile
fi
echo "Running 'keytabclient'"
tmp_response=$(mktemp)
tmp_b64=$(mktemp)
trap 'rm -rf $my_lockfile $tmp_response $tmp_b64' EXIT ERR

while :; do
	ecode=0
	PRINC=host/$ID.$DOMAIN
	PRINCX=host.$ID.$DOMAIN
	if [[ $GLOBAL == "true" ]]; then
		INCRED=/etc/pkinit/sshd-key.pem
		OUTCRED=/etc/krb5.$PRINCX.keytab
	else
		INCRED=/etc/hcp/$ID/pkinit/sshd-key.pem
		OUTCRED=/etc/hcp/$ID/krb5.$PRINCX.keytab
	fi
	kinit -C FILE:$INCRED $PRINC \
		curl -F principals="[]" --cacert /enrollcertchecker/CA.cert \
			--negotiate -u : $URL/v1/ext_keytab > $tmp_response && \
		cat $tmp_response | jq -r .stdout > $tmp_b64 && \
		mkdir -p $(dirname $OUTCRED) && \
		base64 -d $tmp_b64 > $OUTCRED.tmp && \
		chmod 600 $OUTCRED.tmp && \
		mv $OUTCRED.tmp $OUTCRED || \
		ecode=$?
	if [[ $wantfail != 0 ]]; then
		if [[ $ecode == 0 ]]; then
			echo "Error, keytab retrieval succeeded but we wanted failure" >&2
			exit 1
		fi
		echo "Info, keytab retrieval failed, as we wanted" >&2
		exit 0
	fi
	if [[ $ecode != 0 ]]; then
		if [[ $retries == 0 ]]; then
			echo "Error, keytab retrieval failed $ecode;" >&2
			cat "$tmp_attest" >&2
			exit 1
		fi
		retries=$((retries-1))
		sleep $pause
		continue
	fi
	echo "Info, keytab retrieval succeeded"
	break
done
