#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import sys
import json
import subprocess
import time

# We set the current working directory to "/" for a couple of reasons;
# - We want/expect things to work independent of the current directory, so
#   setting it in this way neutralizes the effect of where the caller was when
#   they launched us.
# - When a subprocess drops privileges, the current working directory might be
#   one to which they have no access. E.g. if the shell command 'find' is then
#   executed, it would change working directory as part of its operation and
#   then try to change back - resulting in an error if the original working
#   directory was itself inaccessible.
os.chdir('/')
os.environ['PYTHONUNBUFFERED']='yes'

sys.path.insert(1, '/hcp/common')
from HcpCommon import bail, log, hlog, \
    hcp_config_extract, hcp_config_scope_get, hcp_config_scope_set, \
    hcp_config_scope_shrink

# Process an 'env' section (the object, once parsed from JSON), and derive a
# new environment object from an existing one by applying to it the 'pathadd',
# 'set', 'unset' subjections of the 'env'.
def derive_env(envobj, pathstr, baseenv):
    if not isinstance(envobj, dict):
        bail(f"'{pathstr}' must be a dict (not a {type(envobj)}")
    for s in envobj:
        if s not in [ 'pathadd', 'set', 'unset' ]:
            bail(f"'{pathstr}' supports pathadd/set/unset (not '{s}')")
        v = envobj[s]
        if not isinstance(v, dict):
            bail(f"'{pathstr}:{s}' must be a dict (not a {type(v)})")
        for e in v:
            if not isinstance(e, str):
                bail(f"'{pathstr}:{s}', '{e}' must be a str (not a {type(e)})")
            ev = v[e]
            if s == 'unset':
                if ev != None:
                    bail(f"'{pathstr}:{s}:{e}' must be None (not {type(ev)})")
    newenv = baseenv.copy()
    if 'unset' in envobj:
        es = envobj['unset']
        for k in es:
            if k in newenv:
                newenv.pop(k)
    if 'set' in envobj:
        es = envobj['set']
        for k in es:
            if isinstance(es[k], str):
                newenv[k] = es[k]
            else:
                newenv[k] = json.dumps(es[k])
    if 'pathadd' in envobj:
        ep = envobj['pathadd']
        for k in ep:
            if k in newenv and len(newenv[k]) > 0:
                newenv[k] = f"{newenv[k]}:{ep[k]}"
            else:
                newenv[k] = ep[k]
    return newenv

# Given an environment object, set the environment accordingly
def setenviron(e):
    # Unset what should disappear
    for k in os.environ:
        if k not in e:
            os.environ.pop(k)
    # Set what needs to be set
    for k in e:
        if k not in os.environ or os.environ[k] != e[k]:
            os.environ[k] = e[k]

def pre_subprocess(child):
    if 'env' in child:
        child['backupenv'] = os.environ.copy()
        setenviron(child['env'])
def post_subprocess(child):
    if 'env' in child:
        setenviron(child['backupenv'])

# Take the current environment, and if there is a global-scope 'env' section,
# apply that to it.
baseenv = os.environ.copy()
_env = hcp_config_extract('env', or_default = True)
if _env:
    baseenv = derive_env(_env, "env", baseenv)
    setenviron(baseenv)

hlog(2, "HCP healthcheck: starting")

_id = hcp_config_extract('id', or_default = True, default = 'unknown_id')
etcpath = f"/etc/hcp/{_id}"
if not os.path.isdir(etcpath):
    os.makedirs(etcpath, mode = 0o755)

services = hcp_config_extract('services', or_default = True, default = [])
if not isinstance(services, list):
    bail(f"'services' field should be a list (not a {type(services)})")

num_healthchecks = 0
for name in services:
    if not isinstance(name, str):
        bail(f"services fields should be str (not {type(service)})")
    service = hcp_config_extract(name, must_exist = True)
    if not isinstance(service, dict):
        bail(f"'{name}:healthcheck' should be dict (not {type(service)})")
    if 'healthcheck' not in service:
        hlog(2, f"HCP healthcheck: skipping {name}")
        continue
    hc = service['healthcheck']
    if isinstance(hc, str):
        hc = [ hc ]
    elif not isinstance(hc, list):
        bail(f"'{name}:healthcheck' should be str or list of str")
    pre_subprocess(service)
    p = subprocess.run(hc)
    post_subprocess(service)
    if p.returncode != 0:
        bail(f"'{name}:healthcheck' failed, code: {p.returncode}")
    num_healthchecks += 1

if not num_healthchecks:
    bail("no healthchecks")
hlog(2, "HCP healthcheck: done")
