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
import time
import yaml

app = flask.Flask(__name__)
app.config["DEBUG"] = False

# This 'front-end' API for the enrollsvc will pre-process and then
# call the following 'backend' handlers to implement the real (storage,
# management, retrieval, ...). The backend app includes this module
# and then modifies these handlers;

# get_assets: the first argument is the ekpubhash of the successfully-attested
# host (or its TPM, rather) and the second argument is 'outdir', the path to a
# directory into which assets should be put using the /hcp/safeboot/api_seal
# command. The return is a list of 2-tuples of the form <outname,public>, where
# 'outname' is the output path of an asset directory, relative to 'outdir'.
# sealed asset should be called (and unsealed as), and 'public' is a boolean as
# to whether the asset should only be signed (True) or encrypted and signed
# (False).
backend_get_assets = None

# exception_unenrolled: this is an exception class that we can catch when
# calling the backend's 'get_assets' handler. We'll detect this exception to
# mean that the backend doesn't recognize the TPM and we'll return a '401
# Unauthorized' in that case.
backend_exception_unenrolled = None

# TODO: configure
PCRs='0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16'
MAX_TICKET_AGE=120

def debug(s):
    sys.stderr.write(f"{s}\n")

@app.route('/', methods=['GET'])
def home():
    return '''
<h1>Attestation Service API</h1>
<hr>
'''
@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    return '''
<h1>Healthcheck</h1>
'''

# Initiate consumes;
# - ekpubhash
# Initiate returns;
# - ekpubhash
# - PCRs
# - nonce
# - ticket, encrypted to server, containing;
#   - ekpubhash
#   - PCRs
#   - nonce
#   - issue time
@app.route('/v1/initiate', methods=['POST'])
def my_initiate():
    if 'ekpubhash' not in request.form:
        return make_response("Error: ekpubhash not in request", 400)
    result = {
        'ekpubhash': request.form['ekpubhash'],
        'PCRs': PCRs,
        'nonce': subprocess.run(['openssl', 'rand', '-hex', '16'],
                                capture_output = True,
                                text = True).stdout.strip()
    }
    ticket = result.copy()
    ticket['time'] = int(time.time())
    with tempfile.TemporaryDirectory() as tempdir:
        ticketjson = json.dumps(ticket)
        with open(f"{tempdir}/json", 'w') as fp:
            fp.write(ticketjson)
        c = subprocess.run(['openssl', 'aes-256-cbc', '-salt', '-pbkdf2',
                           '-e',
                           '-kfile', '/tmp/www-data-noncekey',
                           '-in', f"{tempdir}/json",
                           '-out', f"{tempdir}/encrypted"])
        if c.returncode != 0:
            return make_response("Error: ticket-encryption failed", 400)
        c = subprocess.run(['base64', '-w', '0', f"{tempdir}/encrypted"],
                           text = True, capture_output = True)
        if c.returncode != 0:
            return make_response("Error: ticket-encoding failed", 400)
        result['ticket'] = c.stdout.strip()
    resp = make_response(result, 200)
    resp.headers['Content-Type'] = 'application/json'
    return resp

# Complete consumes;
# - ticket
# Complete returns;
@app.route('/v1/complete', methods=['POST'])
def my_complete():
    if 'initial' not in request.files:
        return make_response("Error: initial not in request", 400)
    if 'quote' not in request.files:
        return make_response("Error: quote not in request", 400)
    initial = request.files['initial']
    quote = request.files['quote']
    # TBD: there's not a lot of error handling ...
    # First, parse the 'initial'
    with tempfile.TemporaryDirectory() as tempdir:
        initial.save(f"{tempdir}/initial")
        with open(f"{tempdir}/initial", 'r') as fp:
            initialjson = fp.read()
        initial = json.loads(initialjson)
        ticket = initial['ticket']
        with open(f"{tempdir}/ticket.b64", 'w') as fp:
            fp.write(ticket)
        c = subprocess.run(['base64', '-d', f"{tempdir}/ticket.b64"],
                           capture_output = True)
        if c.returncode != 0:
            return make_response("Error: ticket-decoding failed", 400)
        with open(f"{tempdir}/ticket.enc", 'wb') as fp:
            fp.write(c.stdout)
        c = subprocess.run(['openssl', 'aes-256-cbc', '-salt', '-pbkdf2',
                           '-d',
                           '-kfile', '/tmp/www-data-noncekey',
                           '-in', f"{tempdir}/ticket.enc",
                           '-out', f"{tempdir}/ticket"])
        if c.returncode != 0:
            return make_response("Error: ticket-decryption failed", 400)
        with open(f"{tempdir}/ticket", 'r') as fp:
            ticketjson = fp.read()
        ticket = json.loads(ticketjson)
        if ticket['ekpubhash'] != initial['ekpubhash']:
            return make_response("Error: ticket has bad ekpubhash", 400)
        if ticket['nonce'] != initial['nonce']:
            return make_response("Error: ticket has bad nonce", 400)
        tickettime = ticket['time']
        now = int(time.time())
        if now < tickettime or now > (tickettime + MAX_TICKET_AGE):
            return make_response("Error: ticket is too old", 400);
        nonce = ticket['nonce']
        with open(f"{tempdir}/nonce", 'w') as fp:
            fp.write(nonce)
        nonce = f"{tempdir}/nonce"
        # Next, extract and verify the 'quote'
        quote.save(f"{tempdir}/quote")
        c = subprocess.run(['tar', '-zxf', f"{tempdir}/quote",
                            '-C', tempdir])
        if c.returncode != 0:
            return make_response("Error: quote-extraction failed", 400)
        c = subprocess.run(['openssl', 'sha256', '-r', f"{tempdir}/ek.pub"],
                           capture_output = True, text = True)
        if c.returncode != 0:
            return make_response("Error: ekpub hashing failed", 400)
        if ticket['ekpubhash'] != c.stdout[0:64]:
            return make_response("Error: ekpub doesn't match ticket", 400)
        c = subprocess.run(['tpm2', 'print',
                            '--type', 'TPMT_PUBLIC',
                            f"{tempdir}/ak.pub"],
                            text = True, capture_output = True)
        if c.returncode != 0:
            return make_response("Error: AK pub missing from quote", 400)
        if c.stdout.find('value: fixedtpm|stclear|fixedparent|sensitivedataorigin|userwithauth|restricted|sign') < 0:
            return make_response("Error: AK pub has wrong attributes", 400)
        c = subprocess.run(['tpm2', 'checkquote',
                            '--qualification', nonce,
                            '--message', f"{tempdir}/quote.out",
                            '--signature', f"{tempdir}/quote.sig",
                            '--pcr', f"{tempdir}/quote.pcr",
                            '--public', f"{tempdir}/ak.pub"],
                           capture_output = True)
        if c.returncode != 0:
            sys.stderr.write(f"WARNING: failed attestation from {initial['ekpubhash']}\n")
            return make_response("Error: unable to verify quote", 400)

        # TODO: hooks here to backend to evaluate the PCRs...
        c = subprocess.run(['tpm2', 'print',
                            '--type', 'TPMS_ATTEST',
                            f"{tempdir}/quote.out"],
                           capture_output = True, text = True)
        if c.returncode != 0:
            sys.stderr.write(f"WARNING: failed to parse quote\n")
            return make_response("Error: failed to parse quote", 400)
        with open(f"{tempdir}/quote.yaml", 'w') as fp:
            fp.write(c.stdout)
        with open(f"{tempdir}/quote.yaml", 'r') as fp:
            parsedquote = yaml.safe_load(fp)
        with open(f"{tempdir}/quote.json", 'w') as fp:
            json.dump(parsedquote, fp)
        if not os.path.isfile('/tmp/out.checkquote.tar.gz'):
            subprocess.run(['tar', 'zcf', '/tmp/out.checkquote.tar.gz', tempdir])

        # Now, produce the assets
        with tempfile.TemporaryDirectory() as outdir:
            manifest = []
            if backend_get_assets:
                if backend_exception_unenrolled:
                    try:
                        manifest = backend_get_assets(ticket['ekpubhash'], outdir)
                    except backend_exception_unenrolled:
                        return make_response("Error: unrecognized TPM", 401)
                else:
                    manifest = backend_get_assets(ticket['ekpubhash'], outdir)
            with open(f"{tempdir}/manifest", 'w') as fp:
                fp.write(json.dumps(manifest))
            c = subprocess.run(['/hcp/safeboot/api_seal',
                                '-s',
                                '/tmp/www-data-signer',
                                f"{tempdir}/manifest",
                                f"{outdir}/manifest"])
            if c.returncode != 0:
                return make_response("Error: failed to seal manifest", 400)
            c = subprocess.run(['tar', '-zcf', f"{tempdir}/tarball",
                                '-C', outdir,
                                '.'])
            return send_file(f"{tempdir}/tarball")

if __name__ == "__main__":
    app.run()
