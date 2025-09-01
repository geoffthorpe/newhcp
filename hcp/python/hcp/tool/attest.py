#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import sys
import json
import tempfile

from hcp.common import hcp_config_extract
import hcp.api.attest as api

API = hcp_config_extract('.attester.api', must_exist = True)
verifkey = hcp_config_extract('.attester.verifier', must_exist = True)
assetdir = hcp_config_extract('.attester.assetdir', must_exist = True)
cacert = hcp_config_extract('.attester.cacert', must_exist = True)
callback = hcp_config_extract('.attester.callback', or_default = True)

print("""
            Running attestclient:
     (the attestsvc target)      API: {API}
    (https CA, if required)   cacert: {cacert}
      (asset-signature key) verifkey: {verifkey}
(base directory for output) assetdir: {assetdir}
""".format(API = API, verifkey = verifkey,
	   assetdir = assetdir, cacert = cacert))

def check_result(result, s):
    if not result:
        raise Exception(s)

with tempfile.TemporaryDirectory() as tempdir:
    pinitial = f"{tempdir}/initial"
    pquote = f"{tempdir}/quote"
    pbundle = f"{tempdir}/bundle.tar.get"

    print('Obtaining \'initial\' from server...')
    check_result(api.initiate(API, pinitial, requests_verify = cacert),
                 "Failed to get 'initial' from attestsvc")

    print('Producing quote from TPM...')
    check_result(api.quote(pinitial, pquote),
                 "Failed to product 'quote'")

    print('Completing attestation with server...')
    check_result(api.complete(API, pinitial, pquote, pbundle,
                              requests_verify = cacert),
                 "Attestation failed")

    print('Unsealing returned assets...')
    os.makedirs(assetdir, exist_ok = True)
    check_result(api.unseal(pbundle, assetdir, verifkey,
                            callback = callback),
                 "Failed to unseal assets")

    print('Done')
    open(f"{assetdir}/touch", 'w')
