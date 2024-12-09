# vim: set expandtab shiftwidth=4 softtabstop=4:
import flask
from flask import request, abort, send_file, jsonify, make_response
import sys
import requests
import json

from HcpCommon import log, bail, hcp_config_extract

app = flask.Flask(__name__)
app.config["DEBUG"] = False

@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    return '''
<h1>Healthcheck</h1>
'''

@app.route('/v1/ext_keytab', methods=['POST'])
def my_ext_keytab():
    if not request.is_secure or not request.remote_user:
        return make_response('', 401)
    form_data = { 'principals': (None, json.dumps([request.remote_user])) }
    apiurl = hcp_config_extract('.keytab.kdc_api', must_exist = True)
    cacert = hcp_config_extract('.keytab.ca_cert', must_exist = True)
    client_cert = hcp_config_extract('.keytab.client_cert', must_exist = True)
    response = requests.post(apiurl + '/v1/ext_keytab',
                             files = form_data,
                             verify = cacert,
                             cert = client_cert,
                             timeout = 5)
    return response.content, response.status_code, response.headers.items()

if __name__ == "__main__":
    app.run()
