# vim: set expandtab shiftwidth=4 softtabstop=4:
import flask
from flask import request, abort, send_file, jsonify
import sys

from HcpCommon import log, bail, hcp_config_extract

app = flask.Flask(__name__)
app.config["DEBUG"] = False

@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    return '''
<h1>Healthcheck</h1>
'''

def _doresponse():
    def jsdict(obj):
        r = {}
        for i in obj:
            r[i] = obj[i]
        return r
    def jsheaders(hobj):
        r = []
        for key,value in hobj:
            r.append(f"{key}:{value}")
        return r
    def jsfdict(fobj):
        r = {}
        for i in fobj:
            f = fobj[i]
            r[i] = {
                    'name': f.name,
                    'filename': f.filename,
                    'length': f.length,
                    'content_type': f.content_type,
                    'headers': jsheaders(f.headers)
                    }
        return r
    def requestjson():
        try:
            return request.json
        except:
            return None
    req = {
        'args': jsdict(request.args),
        'cookies': jsdict(request.cookies),
        'content_type': request.content_type,
        'files': jsfdict(request.files),
        'form': jsdict(request.form),
        'full_path': request.full_path,
        'host': request.host,
        'host_url': request.host_url,
        'is_json': request.is_json,
        'is_secure': request.is_secure,
        'json': requestjson(),
        'max_forwards': request.max_forwards,
        'mimetype': request.mimetype,
        'mimetype_params': jsdict(request.mimetype_params),
        'origin': request.origin,
        'pragma': jsheaders(request.pragma),
        'referrer': request.referrer,
        'remote_user': request.remote_user,
        'root_url': request.root_url,
        'script_root': request.script_root,
        'url': request.url,
        'user_agent': request.user_agent.string,
        'values': jsdict(request.values),
        'want_form_data_parsed': request.want_form_data_parsed,
        'environ': [ f"{key}:{value}" for key,value in request.environ.items() ],
        'method': request.method,
        'scheme': request.scheme,
        'headers': jsheaders(request.headers)
    }
    return jsonify(req)

def doresponse():
    try:
        return _doresponse()
    except Exception as e:
        return jsonify(str(e))

@app.route('/get', methods=['GET'])
def my_get():
    return doresponse()

@app.route('/post', methods=['POST'])
def my_post():
    return doresponse()

if __name__ == "__main__":
    app.run()
