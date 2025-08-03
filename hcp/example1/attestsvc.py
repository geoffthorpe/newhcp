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
from hcp.example1.common import *

app = attestsvc.app

def add_secret(enrollpath, _input, output):
    c = subprocess.run(['/hcp/safeboot/api_seal',
                        f"{enrollpath}/ek.pub",
                        '/tmp/www-data-signer',
                        _input,
                        output])
    if c.returncode != 0:
        raise Exception("failed to seal secret", 400)

def add_public(enrollpath, _input, output):
    c = subprocess.run(['/hcp/safeboot/api_seal',
                        '-s',
                        '/tmp/www-data-signer',
                        _input,
                        output])
    if c.returncode != 0:
        raise Exception("failed to seal secret", 400)

def my_get_assets(ekpubhash, outdir):
    enrollpath = ekpubhash2path(ekpubhash)
    if not os.path.isdir(enrollpath):
        raise Exception(f"attestation of un-enrolled TPM: {ekpubhash}")
    profile = {}
    if os.path.isfile(f"{enrollpath}/profile"):
        with open(f"{enrollpath}/profile") as fp:
            profile = json.loads(fp.read())
    result = []
    with tempfile.TemporaryDirectory() as tempdir:
        certgen = []
        if 'certgen' in profile:
            certgen = profile['certgen']
        basecmd = ['hxtool', 'issue-certificate',
                   '--ca-certificate=FILE:/enrollcertissuer/CA.pem']
        basecmd.append('--lifetime=' + str(profile['lifetime'] if 'lifetime' in profile else '1d'))
        basecmd.append('--generate-key=' + (profile['key-type'] if 'key-type' in profile else 'rsa'))
        basecmd.append('--key-bits=' + str(profile['key-bits'] if 'key-bits' in profile else '2048'))
        for certtype in certgen:
            if certtype == 'https-server':
                hostnames = profile['https-server-hostnames'] if \
                    'https-server-hostnames' in profile else [profile['hostname']]
                for hostname in hostnames:
                    cmd = basecmd.copy()
                    cmd = cmd + [ '--type=https-server', f"--hostname={hostname}",
                                  f"--certificate=FILE:{tempdir}/https-server-{hostname}.pem" ]
                    c = subprocess.run(cmd)
                    if c.returncode != 0:
                        raise Exception(f"hxtool failed: {cmd}")
                    add_secret(enrollpath, f"{tempdir}/https-server-{hostname}.pem",
                               f"{outdir}/https-server-{hostname}.pem")
                    result.append([f"https-server-{hostname}.pem", False])
            elif certtype == 'pkinit-client':
                clients = profile['pkinit-clients'] if \
                    'pkinit-clients' in profile else ['nobody']
                for client in clients:
                    cmd = basecmd.copy()
                    cmd = cmd + [ '--type=pkinit-client',
                                  f"--pk-init-principal={client}@HCPHACKING.XYZ",
                                  f"--certificate=FILE:{tempdir}/pkinit-client-{client}.pem" ]
                    c = subprocess.run(cmd)
                    if c.returncode != 0:
                        raise Exception(f"hxtool failed: {cmd}")
                    add_secret(enrollpath, f"{tempdir}/pkinit-client-{client}.pem",
                               f"{outdir}/pkinit-client-{client}.pem")
                    result.append([f"pkinit-client-{client}.pem", False])
            else:
                raise Exception(f"unrecognized certtype: {certtype}")
        return result

# Connect our hooks to the attestsvc
attestsvc.backend_get_assets = my_get_assets

if __name__ == "__main__":
    app.run()
