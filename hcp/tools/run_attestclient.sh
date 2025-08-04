#!/bin/bash

source /hcp/common/hcp.sh

API=$(hcp_config_extract ".attester.api")
VERIFKEY=$(hcp_config_extract ".attester.verifier")
ASSETDIR=$(hcp_config_extract ".attester.assetdir")
CACERT=$(hcp_config_extract ".attester.cacert")

echo "            Running attestclient:"
echo "     (the attestsvc target)      API: $API"
echo "    (https CA, if required)   CACERT: $CACERT"
echo "      (asset-signature key) VERIFKEY: $VERIFKEY"
echo "(base directory for output) ASSETDIR: $ASSETDIR"

tmp=
cleanup() { if [[ -d $tmp ]]; then rm -rf "$tmp"; fi }
trap cleanup EXIT ERR
tmp=$(mktemp -d)

# TODO: this is a temporary and bad fix. The swtpm assumes that connections
# that are set up (tpm2_startup) but not gracefully terminated (tpm2_shutdown)
# are suspicious, and if it happens enough (3 or 4 times, it seems) the TPM
# locks itself to protect against possible dictionary attack. However our
# attestclient is calling a high-level util, so it is not clear where
# tpm2_startup is happening, and it is even less clear where to add a matching
# tpm2_shutdown. Instead, we rely on the swtpm having non-zero tolerance to
# preceed each run of the attestclient (after it has already failed at least
# once to call tpm2_shutdown), and we also rely on there being no dictionary
# policy in place to prevent us from simply resetting the suspicion counter!!
# On proper TPMs (e.g. GCE vTPM), this dictionarylockout call will actually
# fail so has to be commented out.
#
#tpm2_dictionarylockout --clear-lockout || true

export ATTESTSVC_API_URL="$API"
export ATTESTSVC_API_CACERT="$CACERT"

export PATH=/hcp/python:$PATH

echo "Obtaining 'initial' from server..."
HcpApiAttest.py initiate "$tmp/initial"
jq . "$tmp/initial"

echo "Producing quote from TPM..."
HcpApiAttest.py quote "$tmp/initial" "$tmp/quote"

echo "Completing attestation with server..."
HcpApiAttest.py complete "$tmp/initial" "$tmp/quote" "$tmp/bundle.tar.gz"

echo "Unsealing returned assets..."
mkdir -p "$ASSETDIR"
HcpApiAttest.py unseal --callback /hcp/tools/cb_attestclient.sh \
			"$VERIFKEY" "$tmp/bundle.tar.gz" "$ASSETDIR"

echo "Done"
touch "$ASSETDIR/touch"
