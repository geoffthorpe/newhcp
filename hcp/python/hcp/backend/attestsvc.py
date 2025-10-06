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
import hcp.flask.attestsvc as attestsvc
from hcp.backend.common import *
import hcp.api.kdc as kapi
from hcp.common import hcp_config_extract

app = attestsvc.app

requests_verify = hcp_config_extract('.backend.cacert', must_exist = True)
requests_cert = hcp_config_extract('.backend.clientcert', must_exist = True)

domain = hcp_config_extract('.vars.domain', must_exist = True)

def add_secret(enrollpath, _input, output):
    c = subprocess.run(['/hcp/safeboot/api_seal',
                        f"{enrollpath}/ek.pub",
                        '/tmp/www-data-signer',
                        _input,
                        output])
    if c.returncode != 0:
        raise Exception("failed to seal secret")

def add_public(enrollpath, _input, output):
    c = subprocess.run(['/hcp/safeboot/api_seal',
                        '-s',
                        '/tmp/www-data-signer',
                        _input,
                        output])
    if c.returncode != 0:
        raise Exception("failed to seal public")

class UnenrolledTPM(Exception):
    pass

def my_get_assets(ekpubhash, outdir):
    enrollpath = ekpubhash2path(ekpubhash)
    if not os.path.isdir(enrollpath):
        raise UnenrolledTPM(f"attestation of un-enrolled TPM: {ekpubhash}")
    profile = {}
    if os.path.isfile(f"{enrollpath}/profile"):
        with open(f"{enrollpath}/profile") as fp:
            profile = json.loads(fp.read())
    result = []
    with tempfile.TemporaryDirectory() as tempdir:
        certgen = profile['certgen'] if 'certgen' in profile else []
        realm = profile['realm'] if 'realm' in profile else None
        krb5conf = profile['krb5conf'] if 'krb5conf' in profile else None
        ktgen = profile['ktgen'] if 'ktgen' in profile else None
        if ktgen:
            ktgenapi = ktgen.pop('api')
        hxcmd = ['hxtool', 'issue-certificate']
        hxcmd.append('--lifetime=' + str(profile['lifetime'] if 'lifetime' in profile else '1d'))
        hxcmd.append('--generate-key=' + (profile['key-type'] if 'key-type' in profile else 'rsa'))
        hxcmd.append('--key-bits=' + str(profile['key-bits'] if 'key-bits' in profile else '2048'))
        def do_cert(filename, arguments):
            cmd = hxcmd.copy() + arguments + \
                [ f"--certificate=FILE:{tempdir}/{filename}" ]
            c = subprocess.run(cmd)
            if c.returncode != 0:
                raise Exception(f"hxtool failed: {cmd}")
            add_secret(enrollpath, f"{tempdir}/{filename}", f"{outdir}/{filename}")
            result.append([f"{filename}", False])
        for certtype in certgen:
            if certtype == 'https-server':
                hostnames = profile['https-server-hostnames'] if \
                    'https-server-hostnames' in profile else [profile['hostname']]
                for hostname in hostnames:
                    do_cert(f"https-server-{hostname}.pem",
                            [ '--type=https-server', f"--hostname={hostname}",
                              f"--subject=UID={hostname}",
                              '--ca-certificate=FILE:/ca_default_private' ])
            elif certtype == 'https-client':
                clients = profile['https-clients'] if \
                    'https-clients' in profile else ['nobody']
                for client in clients:
                    do_cert(f"https-client-{client}.pem",
                            [ '--type=https-client',
                              '--ca-certificate=FILE:/ca_httpsclient_private',
                              f"--subject=UID={client}",
                              f"--email={client}@{domain}" ])
            elif certtype == 'pkinit-client':
                clients = profile['pkinit-clients'] if \
                    'pkinit-clients' in profile else ['nobody']
                for client in clients:
                    if not realm:
                        raise Exception("No realm for pkinit-client")
                    do_cert(f"pkinit-client-{client}.pem",
                            [ '--type=pkinit-client',
                              f"--subject=UID={client}",
                              '--ca-certificate=FILE:/ca_default_private',
                              f"--pk-init-principal={client}@{realm}" ])
            elif certtype == 'pkinit-kdc':
                if not realm:
                    raise Exception("No realm for pkinit-kdc")
                do_cert(f"pkinit-kdc-{realm}.pem",
                        [ '--type=pkinit-kdc',
                          '--subject=UID=default',
                          '--ca-certificate=FILE:/ca_default_private',
                          f"--pk-init-principal=krbtgt/{realm}@{realm}" ])
            elif certtype == 'pkinit-iprop':
                if not realm:
                    raise Exception("No realm for pkinit-iprop")
                do_cert(f"pkinit-iprop-{realm}.pem",
                        [ '--type=pkinit-client',
                          '--ca-certificate=FILE:/ca_default_private',
                          f"--pk-init-principal=iprop/{hostname}@{realm}",
                          f"--subject=CN=iprop" ])
            else:
                raise Exception(f"unrecognized certtype: {certtype}")
        if krb5conf:
            with open(f"{tempdir}/krb5.conf", 'w') as fp:
                fp.write('''
# Generated by /hcp/python/hcp/backend/attestsvc.py
[logging]
    default = STDERR
[libdefaults]
    default_realm = {realm}
    kdc_timesync = 1
    ccache_type = 4
    forwardable = true
    proxiable = true
    rdns = false
[realms]
    {realm} = {{
        kdc = {kdchost}:{kdcport}
        default_domain = {domain}
        pkinit_anchors = FILE:{pkinit_anchors}
        #pkinit_eku_checking = kpServerAuth
        #pkinit_kdc_hostname = {kdchost}
    }}
[domain_realm]
    {dotdomain} = {realm}
    {domain} = {realm}
'''.format(realm = realm, pkinit_anchors = krb5conf['pkinit_anchors'],
                        domain = krb5conf['domain'],
                        dotdomain = krb5conf['dotdomain'],
                        kdchost = krb5conf['kdchost'],
                        kdcport = krb5conf['kdcport']))
            add_public(enrollpath, f"{tempdir}/krb5.conf",
                       f"{outdir}/krb5.conf")
            result.append([f"krb5.conf", True])
        if ktgen:
            if not isinstance(ktgen, dict):
                raise Exception("ktgen should be a dict")
            for name in ktgen:
                princs = ktgen[name]
                if isinstance(princs, str):
                    princs = [ princs ]
                if not isinstance(princs, list):
                    raise Exception(f"ktgen[{name}] should be a str or list")
                retcode, _ = kapi.kdc_ext_keytab(ktgenapi, princs, False,
                                                 f"{tempdir}/keytab-{name}",
                                                 requests_verify = requests_verify,
                                                 requests_cert = requests_cert)
                if not retcode:
                    raise Exception(f"ktgen[{name}] failed")
                add_secret(enrollpath, f"{tempdir}/keytab-{name}",
                           f"{outdir}/keytab-{name}")
                result.append([f"keytab-{name}", False])
        return result

# Connect our hooks to the attestsvc
attestsvc.backend_get_assets = my_get_assets
attestsvc.backend_exception_unenrolled = UnenrolledTPM

if __name__ == "__main__":
    app.run()
