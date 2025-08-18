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
import hcp.python.HcpApiKdc as kapi
from hcp.python.HcpCommon import hcp_config_extract

app = attestsvc.app

requests_verify = hcp_config_extract('.example1.cacert', must_exist = True)
requests_cert = hcp_config_extract('.example1.clientcert', must_exist = True)

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
        hxcmd = ['hxtool', 'issue-certificate',
                   '--ca-certificate=FILE:/ca_root_private/CA.pem']
        hxcmd.append('--lifetime=' + str(profile['lifetime'] if 'lifetime' in profile else '1d'))
        hxcmd.append('--generate-key=' + (profile['key-type'] if 'key-type' in profile else 'rsa'))
        hxcmd.append('--key-bits=' + str(profile['key-bits'] if 'key-bits' in profile else '2048'))
        for certtype in certgen:
            if certtype == 'https-server':
                hostnames = profile['https-server-hostnames'] if \
                    'https-server-hostnames' in profile else [profile['hostname']]
                for hostname in hostnames:
                    cmd = hxcmd.copy() + \
                        [ '--type=https-server', f"--hostname={hostname}",
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
                    if not realm:
                        raise Exception("No realm for pkinit-client")
                    cmd = hxcmd.copy() + \
                        [ '--type=pkinit-client',
                          f"--pk-init-principal={client}@HCPHACKING.XYZ",
                          f"--certificate=FILE:{tempdir}/pkinit-client-{client}.pem" ]
                    c = subprocess.run(cmd)
                    if c.returncode != 0:
                        raise Exception(f"hxtool failed: {cmd}")
                    add_secret(enrollpath, f"{tempdir}/pkinit-client-{client}.pem",
                               f"{outdir}/pkinit-client-{client}.pem")
                    result.append([f"pkinit-client-{client}.pem", False])
            elif certtype == 'pkinit-kdc':
                if not realm:
                    raise Exception("No realm for pkinit-kdc")
                cmd = hxcmd.copy() + \
                    [ '--type=pkinit-kdc',
                      f"--pk-init-principal=krbtgt/{realm}@{realm}",
                      f"--certificate=FILE:{tempdir}/pkinit-kdc-{realm}.pem" ]
                c = subprocess.run(cmd)
                if c.returncode != 0:
                    raise Exception(f"hxtool failed: {cmd}")
                add_secret(enrollpath, f"{tempdir}/pkinit-kdc-{realm}.pem",
                           f"{outdir}/pkinit-kdc-{realm}.pem")
                result.append([f"pkinit-kdc-{realm}.pem", False])
            elif certtype == 'pkinit-iprop':
                if not realm:
                    raise Exception("No realm for pkinit-iprop")
                cmd = hxcmd.copy() + \
                    [ '--type=pkinit-client',
                      f"--pk-init-principal=iprop/{hostname}@{realm}",
                      f"--subject=CN=iprop",
                      f"--certificate=FILE:{tempdir}/pkinit-iprop-{realm}.pem" ]
                c = subprocess.run(cmd)
                if c.returncode != 0:
                    raise Exception(f"hxtool failed: {cmd}")
                add_secret(enrollpath, f"{tempdir}/pkinit-iprop-{realm}.pem",
                           f"{outdir}/pkinit-iprop-{realm}.pem")
                result.append([f"pkinit-iprop-{realm}.pem", False])
            else:
                raise Exception(f"unrecognized certtype: {certtype}")
        if krb5conf:
            with open(f"{tempdir}/krb5.conf", 'w') as fp:
                fp.write('# Generated by /hcp/example1/attestsvc.py\n')
                for sectionname in krb5conf:
                    if sectionname == 'realms':
                        # We handle the realms section differently, see below
                        continue
                    section = krb5conf[sectionname]
                    if not isinstance(section, dict) or len(section) == 0:
                        continue
                    fp.write(f"[{sectionname}]\n")
                    for key in section:
                        v = section[key]
                        if isinstance(v, str):
                            fp.write(f"    {key} = {v}\n")
                        elif isinstance(v, list):
                            for i in v:
                                fp.write(f"    {key} = {i}\n")
                        else:
                            raise Exception(f"unhandled value type: {type(v)}")
                if 'realms' in krb5conf:
                    section = krb5conf['realms']
                    if isinstance(section, dict) and len(section) > 0:
                        fp.write('[realms]\n')
                        for realm in section:
                            fp.write(f"    {realm} = {{\n")
                            realmvals = section[realm]
                            for key in realmvals:
                                fp.write(f"        {key} = {realmvals[key]}\n")
                            fp.write('    }\n')
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
