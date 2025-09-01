#!/bin/bash

# This picks up things like TPM2TOOLS_TCTI
. /hcp/common/hcp.sh

# This script performs the attestation routine step-wise.

export ATTESTSVC_API_URL=https://attestsvc.hcphacking.xyz
export ATTESTSVC_API_CACERT=/ca_default


export API=/hcp/python/hcp/api/attest.py

tmp=
cleanup() { if [[ -d $tmp ]]; then rm -rf "$tmp"; fi }
trap cleanup EXIT
tmp=$(mktemp -d)

echo "Obtaining 'initial' from server..."
$API initiate "$tmp/initial"

echo "Producing quote from TPM..."
$API quote "$tmp/initial" "$tmp/quote"

echo "Completing attestation with server..."
$API complete "$tmp/initial" "$tmp/quote" "$tmp/bundle.tar.gz"

echo "Unsealing returned assets..."
mkdir -p /assets
$API unseal /verifier_asset "$tmp/bundle.tar.gz" /assets

echo "Done, listing /assets;"
ls -l /assets
