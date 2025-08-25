#!/bin/bash

# This picks up things like TPM2TOOLS_TCTI
. /hcp/common/hcp.sh

# This script can be run on 'host1' in the 'example1' scenario.
# It performs the attestation routine step-wise.

export ATTESTSVC_API_URL=https://attestsvc.hcphacking.xyz
export ATTESTSVC_API_CACERT=/ca_default/CA.cert

export PATH=/hcp/python:$PATH

tmp=
cleanup() { if [[ -d $tmp ]]; then rm -rf "$tmp"; fi }
trap cleanup EXIT
tmp=$(mktemp -d)

echo "Obtaining 'initial' from server..."
HcpApiAttest.py initiate "$tmp/initial"

echo "Producing quote from TPM..."
HcpApiAttest.py quote "$tmp/initial" "$tmp/quote"

echo "Completing attestation with server..."
HcpApiAttest.py complete "$tmp/initial" "$tmp/quote" "$tmp/bundle.tar.gz"

echo "Unsealing returned assets..."
mkdir -p /assets
HcpApiAttest.py unseal /assetverifier "$tmp/bundle.tar.gz" /assets

echo "Done, listing /assets;"
ls -l /assets
