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
import hcp.flask.enrollsvc as enrollsvc
from hcp.backend.common import *

app = enrollsvc.app

def my_add(tempdir):
    # TBD: there's not a lot of error handling ...
    with open(f"{tempdir}/ekpubhash", 'r') as fp:
        ekpubhash = fp.read()
    enrollpath = ekpubhash2path(ekpubhash)
    result = {'ekpubhash': ekpubhash}
    if os.path.isdir(enrollpath):
        result['error'] = 'TPM EK already enrolled'
        return result, 409
    c = subprocess.run(['mkdir', '-p', f"{enrollpath}.tmp"])
    for f in glob.iglob('*', root_dir = tempdir):
        shutil.move(f"{tempdir}/{f}", f"{enrollpath}.tmp/")
    c = subprocess.run(['mv', f"{enrollpath}.tmp", enrollpath])
    # Success
    return result, 201

# Same function for query, delete, and reenroll
def my_qdr(op, ekpubhash, nofiles):
    respjson = { "entries": [] }
    prefix = ekpubhash
    did_anything = False
    for match in glob.iglob(ekpubhash2path(prefix)):
        did_anything = True
        c = subprocess.run(['basename', match],
                           stdout = subprocess.PIPE, text = True)
        matchhash = c.stdout.strip()
        newentry = {
            'ekpubhash': matchhash
        }
        if not nofiles:
            newentry['files'] = []
            for f in glob.iglob("*", root_dir = match):
                newentry['files'].append(f)
        respjson['entries'].append(newentry)
        if op == 'delete':
            c = subprocess.run(['rm', '-rf', match])
            if c.returncode != 0:
                return respjson, 500
        elif op == 'reenroll':
            pass # no work required
        elif op != 'query':
            raise Exception('unrecognized op')
    return respjson, 200 if op == 'query' or did_anything else 404

def my_query(ekpubhash, nofiles):
    return my_qdr('query', ekpubhash, nofiles)

def my_delete(ekpubhash, nofiles):
    return my_qdr('delete', ekpubhash, nofiles)

def my_reenroll(ekpubhash, nofiles):
    return my_qdr('reenroll', ekpubhash, nofiles)

def my_janitor():
    return {}, 200

# Connect our hooks to the enrollsvc
enrollsvc.backend_add = my_add
enrollsvc.backend_query = my_query
enrollsvc.backend_delete = my_delete
enrollsvc.backend_reenroll = my_reenroll
enrollsvc.backend_janitor = my_janitor

if __name__ == "__main__":
    app.run()
