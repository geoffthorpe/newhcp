# vim: set expandtab shiftwidth=4 softtabstop=4:
import flask
from flask import request, abort, send_file, Response, make_response
import subprocess
import json
import os, sys
from stat import *
from markupsafe import escape
from werkzeug.utils import secure_filename
from pathlib import Path
import tempfile
import requests
import tempfile
import glob
import shutil
import hcp.attestsvc as attestsvc

app = attestsvc.app

# This will generate a glob-compatible wildcard string for any ekpubhash
# inputs that are less than 32 bytes (64 hex characters).
def ekpubhash2path(ekpubhash):
    ekpubhash = ekpubhash.strip()
    if len(ekpubhash) < 2:
        return f"/example/db/{ekpubhash[0:2]}*/*/*"
    if len(ekpubhash) < 4:
        return f"/example/db/{ekpubhash[0:2]}/{ekpubhash[0:4]}*/*"
    if len(ekpubhash) < 64:
        return f"/example/db/{ekpubhash[0:2]}/{ekpubhash[0:4]}/{ekpubhash}*"
    if len(ekpubhash) > 64:
        raise Exception('ekpubhash greater than 64 characters')
    return f"/example/db/{ekpubhash[0:2]}/{ekpubhash[0:4]}/{ekpubhash}"

def my_get_assets(ekpubhash, outdir):
    enrollpath = ekpubhash2path(ekpubhash)
    sys.stderr.write(f"FOO: {enrollpath}\n")
    if not os.path.isdir(enrollpath):
        return []
    sys.stderr.write(f"FOO: made it further\n")
    with tempfile.TemporaryDirectory() as tempdir:
        with open(f"{tempdir}/private", 'w') as fp:
            fp.write("This is a secret asset, should be encrypted")
        c = subprocess.run(['/hcp/safeboot/api_seal',
                            f"{enrollpath}/ek.pub",
                            '/tmp/www-data-signer',
                            f"{tempdir}/private",
                            f"{outdir}/secretfoo"])
        if c.returncode != 0:
            return make_response("Error: failed to seal secretfoo", 400)
        with open(f"{tempdir}/public", 'w') as fp:
            fp.write("This is a public asset, should only be signed")
        c = subprocess.run(['/hcp/safeboot/api_seal',
                            '-s',
                            '/tmp/www-data-signer',
                            f"{tempdir}/public",
                            f"{outdir}/publicinfo"])
        if c.returncode != 0:
            return make_response("Error: failed to seal publicinfo", 400)
        return [
            [ "secretfoo", False ],
            [ "publicinfo", True ]
        ]

attestsvc.backend_get_assets = my_get_assets

if __name__ == "__main__":
    app.run()
