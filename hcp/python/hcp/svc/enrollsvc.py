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

app = flask.Flask(__name__)
app.config["DEBUG"] = False

# This 'front-end' API for the enrollsvc will pre-process and then
# call the following 'backend' handlers to implement the real (storage,
# management, retrieval, ...). The backend app includes this module
# and then modifies these handlers;

# add: the sole argument is the 'tempdir', where the ek.pub, ekpubhash,
# hostname, and profile files have been written. Should return a 2-tuple of
# a JSON-serializable object and an http status code.
backend_add = None

# query/delete/reenroll: the first argument is the 'ekpubhash' prefix to
# identify the TPM(s) to operate on, and the second argument is a 'nofiles'
# boolean. The return value should be a 2-tuple as with the 'add' API. The
# JSON-serializable object should have an 'entries' array, each item of which
# is an object containing an 'ekpubhash' string, and optionally (if 'nofiles'
# was False) a 'files' array containing the files registered with the
# enrollment.
backend_query = None
backend_delete = None
backend_reenroll = None

# janitor: called whenever the enrollsvc /v1/janitor endpoint is hit. No
# arguments are provided, the return value is a 2-tuple.
backend_janitor = None

@app.route('/', methods=['GET'])
def home():
    return '''
<h1>Enrollment Service Management API</h1>
<hr>

<h2>To add a new host entry;</h2>
<form method="post" enctype="multipart/form-data" action="/v1/add">
<table>
<tr><td>ekpub</td><td><input type=file name=ekpub></td></tr>
<tr><td>profile</td><td><input type=text name=profile></td></tr>
</table>
<input type="submit" value="Enroll">
</form>

<h2>To query host entries;</h2>
<form method="get" action="/v1/query">
<table>
<tr><td>ekpubhash prefix</td><td><input type=text name=ekpubhash></td></tr>
</table>
<input type="submit" value="Query">
</form>

<h2>To delete host entries;</h2>
<form method="post" action="/v1/delete">
<table>
<tr><td>ekpubhash prefix</td><td><input type=text name=ekpubhash></td></tr>
</table>
<input type="submit" value="Delete">
</form>

<h2>To reenroll a host entry;</h2>
<form method="post" action="/v1/reenroll">
<table>
<tr><td>ekpubhash</td><td><input type=text name=ekpubhash></td></tr>
</table>
<input type="submit" value="Reenroll">
</form>

<h2>To find host entries by hostname regex;</h2>
<form method="get" action="/v1/find">
<table>
<tr><td>hostname regex</td><td><input type=text name=hostname_regex></td></tr>
</table>
<input type="submit" value="Find">
</form>

<h2>To trigger the janitor (looks for known issues, regenerates the
hn2ek table, etc);</h2>
<form method="get" action="/v1/janitor">
<input type="submit" value="Janitor">
</form>

<h2>To retrieve the asset-signing trust anchor;</h2>
<a href="/v1/get-asset-signer">Click here</a>
'''
@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    return '''
<h1>Healthcheck</h1>
'''

@app.route('/v1/add', methods=['POST'])
def my_add():
    if 'ekpub' not in request.files:
        return make_response("Error: ekpub not in request", 400)
    form_ekpub = request.files['ekpub']
    form_profile = request.form['profile'] if 'profile' in request.form else None

    # TBD: there's not a lot of error handling ...
    result = {}
    with tempfile.TemporaryDirectory() as tempdir:
        # Here's the ek.pub
        form_ekpub.save(f"{tempdir}/ek.pub")
        # Here's the ekpubhash
        c = subprocess.run(['openssl', 'sha256', '-r', f"{tempdir}/ek.pub"],
                           stdout = subprocess.PIPE, text = True)
        ekpubhash = c.stdout[0:64]
        with open(f"{tempdir}/ekpubhash", 'w') as fp:
            fp.write(ekpubhash)
        # Here's the profile
        if form_profile:
            with open(f"{tempdir}/profile", 'w') as fp:
                fp.write(form_profile)

        # Invoke backend logic
        result, resultcode = backend_add(tempdir)

    resp = make_response(result, resultcode)
    resp.headers['Content-Type'] = 'application/json'
    return resp

@app.route('/v1/query', methods=['GET'])
def my_query():
    if 'ekpubhash' not in request.args:
        return make_response("Error: ekpubhash not in request", 400)
    ekpubhash = request.args['ekpubhash']
    nofiles = 'nofiles' in request.args
    # Invoke backend logic
    result, resultcode = backend_query(ekpubhash, nofiles)
    resp = make_response(result, resultcode)
    resp.headers['Content-Type'] = 'application/json'
    return resp

@app.route('/v1/delete', methods=['POST'])
def my_delete():
    if 'ekpubhash' not in request.form:
        return make_response("Error: ekpubhash not in request", 400)
    ekpubhash = request.form['ekpubhash']
    nofiles = 'nofiles' in request.args
    # Invoke backend logic
    result, resultcode = backend_delete(ekpubhash, nofiles)
    resp = make_response(result, resultcode)
    resp.headers['Content-Type'] = 'application/json'
    return resp

@app.route('/v1/reenroll', methods=['POST'])
def my_reenroll():
    if 'ekpubhash' not in request.form:
        return make_response("Error: ekpubhash not in request", 400)
    ekpubhash = request.form['ekpubhash']
    nofiles = 'nofiles' in request.args
    # Invoke backend logic
    result, resultcode = backend_reenroll(ekpubhash, nofiles)
    resp = make_response(result, resultcode)
    resp.headers['Content-Type'] = 'application/json'
    return resp

@app.route('/v1/janitor', methods=['GET'])
def my_janitor():
    # Invoke backend logic
    result, resultcode = backend_janitor(ekpubhash, nofiles)
    resp = make_response(result, resultcode)
    resp.headers['Content-Type'] = 'application/json'
    return resp

if __name__ == "__main__":
    app.run()
