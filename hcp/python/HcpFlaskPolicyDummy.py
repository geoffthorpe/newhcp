# vim: set expandtab shiftwidth=4 softtabstop=4:
# TODO: I don't need most of these imports, copy-n-paste detritus. Clean up.
import flask
from flask import request, abort, send_file, jsonify
import subprocess
import json
import os, sys
from stat import *
from markupsafe import escape
from werkzeug.utils import secure_filename
import tempfile
import requests
from datetime import datetime

from HcpCommon import log, bail, hcp_config_extract

app = flask.Flask(__name__)
app.config["DEBUG"] = False

@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    return '''
<h1>Healthcheck</h1>
'''

@app.route('/run', methods=['POST'])
def my_common():
    dump = {}
    # The payload JSON is expected to be request.form['params']
    if 'params' in request.form:
        try:
            dump['params'] = json.loads(request.form['params'])
        except ValueError:
            return "Bad JSON input", 401

    # request.form['hookname'] is used to identify the caller
    hookname = None
    if 'hookname' in request.form:
        hookname = request.form['hookname']
        dump['hookname'] = hookname
    # request.form['request_uid'] is to correlate logging
    if 'request_uid' in request.form:
        request_uid = request.form['request_uid']
        dump['request_uid'] = request_uid

    now = datetime.now()
    path = '/tmp/pol.'
    if hookname:
        path = path + f"{hookname}."
    path = path + f"{now.year}.{now.month}.{now.day}.{now.hour}."
    path = path + f"{now.minute}.{now.second}.{now.microsecond}"
    with open(path, 'w') as fp:
        json.dump(dump, fp)
    return '{}'

if __name__ == "__main__":
    app.run()
