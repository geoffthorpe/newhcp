#!/bin/bash

set -e

tmpdir=
cleanup()
{
	if [[ -d $tmpdir ]]; then
		rm -rf $tmpdir
	fi
}
trap cleanup EXIT
tmpdir=$(mktemp -d)

email=
DNS=

usage()
{
	echo "Usage:  $0 <certoutput> <subject> <CAcert> <CAkey>" >&2
}

if [[ $# -lt 4 ]]; then
	echo "Error, first four arguments must be provided:" >&2
	usage
	exit 1
fi
cert=$1
subj=$2
CAcert=$3
CAkey=$4
shift 4

while [[ $# -gt 0 ]]; do
	if [[ $# -lt 2 ]]; then
		echo "Error, missing argument: $1" >&2
		exit 1
	fi
	case $1 in
	"email")
		email=$2
		;;
	"DNS")
		DNS=$2
		;;
	*)
		echo "Error, unrecognized argument: $1" >&2
		exit 1
	esac
	shift 2
done

cat > $tmpdir/conf << EOF
[extensions]
subjectAltName = @alt_section
[alt_section]
EOF
if [[ -n $email ]]; then
	echo "email = $email" >> $tmpdir/conf
fi
if [[ -n $DNS ]]; then
	echo "DNS = $DNS" >> $tmpdir/conf
fi

openssl genrsa -out $tmpdir/private 2048
openssl rsa -in $tmpdir/private -pubout -out $tmpdir/public
openssl x509 \
	-new \
	-out $tmpdir/cert \
	-CA $CAcert \
	-CAkey $CAkey \
	-force_pubkey $tmpdir/public \
	-days 3650 \
	-subj $subj \
	-extfile $tmpdir/conf \
	-extensions extensions

cat $tmpdir/cert > $cert
cat $tmpdir/private >> $cert
