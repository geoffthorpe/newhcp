#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4: 

import os
import sys
import subprocess
import argparse
import time
import shutil
import json

sys.path.insert(1, '/hcp/common')
import hcp_common as h

parser = argparse.ArgumentParser()
parser.add_argument("--healthcheck", action = "store_true",
               help = "check that webapi is running ok")
parser.add_argument("--hup", action = "store_true",
        help = "send SIGHUP to currently-running webapi")
parser.add_argument("-R", "--retries", type = int, default = 0,
        help = "for healthcheck, max # of retries")
parser.add_argument("-P", "--pause", type = int, default = 1,
        help = "for healthcheck, pause (seconds) between retries")
parser.add_argument("-v", "--verbose", default = 0, action = "count",
        help = "increase output verbosity")
parser.add_argument("-V", "--less-verbose", default = 0, action = "count",
        help = "decrease output verbosity")
parser.add_argument("-U", "--url", type = str, default = None,
        help = "URL for 'healthcheck'ing the API")
parser.add_argument("-A", "--curl-args", type = str, default = None,
        help = "Pre-URL arguments to 'curl'")
parser.add_argument("-C", "--config-section", type = str, default = "webapi",
        help = "Section name in the JSON config")
args = parser.parse_args()
myworld = h.hcp_config_extract(".", must_exist = True)

def param(field, _type, required = False, default = None,
        obj = myworld, objpath = ''):
    if field in obj:
        v = obj[field]
        if not isinstance(v, _type):
            h.bail(f"'{objpath}.{field}' must be {_type}, not {type(v)}")
        return v
    if required:
        h.bail(f"'{objpath}.{field}' missing but required")
    return default

myinstance = param('id', str, required = True)
mydomain = param('default_domain', str, required = True)
mywebapi = param(args.config_section, dict, required = True)

def webapi_param(field, _type, required = False, default = None):
    return param(field, _type, required = required, default = default,
            obj = mywebapi, objpath = f".{mywebapi}")

myservername = webapi_param('servername', str)
myport = webapi_param('port', int)
myhttps = webapi_param('https', dict)
myapp = webapi_param('app', str, required = True)
myappcfg = webapi_param('config', str)
myharakiri = webapi_param('harakiri', int, default = 600)
myclienttimeout = webapi_param('clienttimeout', int, default = 600)
myenv = webapi_param('uwsgi_env', dict, default = {})
myuid = webapi_param('uwsgi_uid', str, default = 'www-data')
mygid = webapi_param('uwsgi_gid', str, default = 'www-data')

if myhttps:
    def https_param(field, _type, required = True, default = None):
        return param(field, _type, required, default,
            obj = myhttps, objpath = f".{mywebapi}.https")
    myservercert = https_param('certificate', str)
    myauthentication = https_param('authentication', str)
    myCA = https_param('client_CA', str)
    mykerberos = False
    if myauthentication == 'clientcert':
        myhealthclient = https_param('healthclient', str)
    elif myauthentication == 'kerberos':
        mykerberos = True
    elif myauthentication != 'none':
        h.bail(f"Unrecognized 'authentication' value: {myauthentication}")

if not myservername:
    myservername = f"{myinstance}.{mydomain}"
if not myport:
    if myhttps:
        myport = 443
    else:
        myport = 80
myURL = f"{myservername}:{myport}/healthcheck"
mycurlargs = '-f -g --connect-timeout 2'
mykinit = []
if myhttps:
    myURL = f"https://{myURL}"
    if myauthentication == 'clientcert':
        mycurlargs = f"{mycurlargs} --cacert {myCA} --cert {myhealthclient}"
    elif myauthentication == 'kerberos':
        mycurlargs = f"{mycurlargs} --negotiate -u :"
        mykinit += [
            'kinit',
            '-C',
            'FILE:/etc/creds/unknown/healthcheck/pkinit/user-healthcheck-key.pem',
            'healthcheck' ]
else:
    myURL = f"http://{myURL}"
if not args.curl_args:
    args.curl_args = mycurlargs
if not args.url:
    args.url = myURL

myetc = f"/etc/hcp/{myservername}/webapi"
etcnginx = f"{myetc}/nginx"
etcuwsgi = f"{myetc}/uwsgi.ini"
etcjson = f"{myetc}/json"
myvarlog = f"/var/log/{myservername}"
lognginx = f"{myvarlog}/nginx"
myuwsgisock = f"/tmp/{myservername}.uwsgi.sock"

try:
    verbosity = int(os.environ['VERBOSE'])
except:
    verbosity = 1

verbosity = verbosity + args.verbose - args.less_verbose
h.current_loglevel = verbosity
os.environ['VERBOSE'] = f"{verbosity}"

if args.healthcheck:
    h.hlog(1, f"Running: curl {args.curl_args} {args.url}")
    while True:
        c = subprocess.run(mykinit + f"curl {args.curl_args} {args.url}".split(),
            capture_output = True)
        if c.returncode == 0:
            break
        h.hlog(1, f"Failed with code: {c.returncode}")
        h.hlog(2, f"Error output:\n{c.stderr}")
        if args.retries == 0:
            h.hlog(0, "Failure, giving up")
            break
        args.retries = args.retries - 1
        if args.pause > 0:
            h.hlog(2, f"Pausing for {args.pause} seconds")
            time.sleep(args.pause)
    sys.exit(c.returncode)

if os.path.exists(myetc):
    myetc_old = f"{myetc}.old"
    if os.path.exists(myetc_old):
        h.hlog(1, "Deleting really old webapi config")
        shutil.rmtree(myetc_old)
    h.hlog(1, "Moving old webapi config")
    os.rename(myetc, myetc_old)
os.makedirs(myetc)

# Stand up an nginx HTTPS/TLS front-end iff there's a "myhttps" config
if myhttps:
    h.hlog(1, f"Converting template nginx config: {etcnginx}")
    shutil.copytree('/hcp/conf/nginx', etcnginx)
    with open(f"{etcnginx}/nginx.conf.template", "r") as _input:
        with open(f"{etcnginx}/nginx.conf", "w") as _output:
            while _output.write(_input.read().replace(
                    "{etcdir}", etcnginx).replace(
                    "{varlogdir}", lognginx).replace(
                    "{varrunpid}", f"/run/{myservername}/nginx.pid").replace(
                    "{port}", f"{myport}").replace(
                    "{servername}", myservername).replace(
                    "{servercert}", myservercert).replace(
                    "{CAcert}", myCA).replace(
                    "{uwsgisock}", myuwsgisock).replace(
                    "{sslverify}",
                    'on' if myauthentication == 'clientcert' else 'off').replace(
                    "{authgss}",
                    'on' if myauthentication == 'kerberos' else 'off')) > 0:
                pass
    if myauthentication == 'kerberos':
        keytab = f"/etc/krb5.HTTP.{myservername}.keytab"
        if not os.path.exists(keytab):
            h.bail(f"FAIL: keytab ({keytab}) doesn't exist")
        subprocess.run([ 'chgrp', 'www-data', keytab])
        subprocess.run([ 'chmod', '0640', keytab])
    # Create log directory
    h.hlog(1, f"Creating nginx log dir: {lognginx}")
    os.makedirs(lognginx, exist_ok = True)
    # Create pid directory
    h.hlog(1, f"Creating nginx pid dir: /run/{myservername}")
    os.makedirs(f"/run/{myservername}", exist_ok = True)
    h.hlog(1, "Starting nginx")
    subprocess.run([ 'nginx', '-c', f"{etcnginx}/nginx.conf" ])

# Duplicate the HCP_CONFIG_FILE so its readable by the app, and if a
# ".webapi.config" is specified, duplicate that too.
os.makedirs(etcjson)

hcpcfg_old = os.environ['HCP_CONFIG_FILE']
hcpcfg_new = f"{etcjson}/hcp_config_file"

if myappcfg:
    newappcfg = f"{etcjson}/app_config_file"
    h.hlog(1, f"Migrating app config: {myappcfg} -> {newappcfg}")
    shutil.copyfile(myappcfg, newappcfg)
    os.chmod(newappcfg, 0o444)
    # Replace {myappcfg} with {newappcfg}
    myworld[args.config_section]['config'] = newappcfg
h.hlog(1, f"Migrating HCP config: {os.environ['HCP_CONFIG_FILE']} -> {hcpcfg_new}")
with open(hcpcfg_new, 'w') as fp:
    json.dump(myworld, fp)
os.chmod(hcpcfg_new, 0o444)
os.environ['HCP_CONFIG_FILE'] = hcpcfg_new

# Produce the uwsgi config
h.hlog(1, f"Converting template uwsgi config: {etcuwsgi}")
with open(etcuwsgi, 'w') as fp:
    fp.write('''[uwsgi]
master = true
processes = 2
threads = 2
uid = {myuid}
gid = {mygid}
wsgi-file = {myapp}
callable = app
die-on-term = true
route-if = equal:${{PATH_INFO}};/healthcheck donotlog:
harakiri = {myharakiri}
'''.format(myuid = myuid, mygid = mygid, myapp = myapp, myharakiri = myharakiri))
    for k in myenv:
        fp.write(f"env = {k}={myenv[k]}\n")
    if myhttps:
        fp.write('''socket = {myuwsgisock}
socket-timeout = {myclienttimeout}
chmod-socket = 660
vacuum = true
'''.format(myuwsgisock = myuwsgisock, myclienttimeout = myclienttimeout))
    else:
        fp.write('''plugin = http
http = :{myport}
http-timeout = {myclienttimeout}
stats = :{mystats}
'''.format(myport = myport, myclienttimeout = myclienttimeout,
        mystats = myport + 1))

bin_uwsgi_python = shutil.which('uwsgi_python3')
if not bin_uwsgi_python:
    # On debian buster+bullseye+bookworm we have a '37' (but no '3')
    # On debian trixie we have a "312"
    bin_uwsgi_python = shutil.which('uwsgi_python312')
if not bin_uwsgi_python:
    bin_uwsgi_python = shutil.which('uwsgi_python37')
h.hlog(1, f"Starting uwsgi")
subprocess.run([ bin_uwsgi_python, '--ini', etcuwsgi ])
