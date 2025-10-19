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

usage()
{
	echo "Usage:  $0 <certoutput> <name>" >&2
}

if [[ $# -lt 2 ]]; then
	echo "Error, first four arguments must be provided:" >&2
	usage
	exit 1
fi
cert=$1
name=$2
shift 2

openssl genrsa \
	-out $tmpdir/private \
	4096
openssl rsa \
	-in $tmpdir/private \
	-pubout \
	-out $tmpdir/public
openssl req \
	-x509 \
	-new \
	-nodes \
	-sha256 \
	-out $tmpdir/cert \
	-key $tmpdir/private \
	-days 3650 \
	-subj "/CN=$name" \
	-addext "basicConstraints=critical,CA:TRUE" \
	-addext "keyUsage=critical,digitalSignature,cRLSign,keyCertSign" \
	-addext "extendedKeyUsage=serverAuth,clientAuth,codeSigning,emailProtection"

cat $tmpdir/cert > $cert
cat $tmpdir/private >> $cert
