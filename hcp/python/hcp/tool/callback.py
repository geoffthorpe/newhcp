#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import sys
import json
import tempfile
import subprocess
import pwd

sys.argv.pop(0)
if len(sys.argv) != 3:
    raise Exception("hcp.tool.callback should receive 3 arguments")

phase = sys.argv[0]
asset = sys.argv[1]
path = sys.argv[2]
hostname = os.environ['HOSTNAME']

def getuid(name):
    return pwd.getpwnam(name).pw_uid

if phase == 'pre':

    if asset == 'keytab-http':
        print('keytab-http: chown to \'www-data\', chmod to 0640')
        os.chown(path, getuid('www-data'), -1)
        os.chmod(path, 0o640)
    elif asset.startswith('pkinit-client-') or asset.startswith('https-client-'):
        name = asset.removeprefix('pkinit-client-')
        name = name.removeprefix('https-client-')
        name = name.removesuffix('.pem')
        if name and os.path.isdir(f"/home/{name}"):
            print(f"{asset}: chown to '{name}'")
            os.chown(path, getuid(name), -1)
        else:
            print(f"{asset}: ignoring")

elif phase == 'post':

    if asset.startswith('https-server-'):
        if os.path.isfile(f"/run/{hostname}/nginx.pid"):
            pid = int(open(f"/run/{hostname}/nginx.pid", 'r').read())
            if pid:
                if subprocess.run(['ps', '-p', str(pid)],
                                  capture_output = True).returncode == 0:
                    print(f"sending SIGHUP to {pid}")
                    subprocess.run(['kill', '-s', 'HUP', str(pid)],
                                   capture_output = True)
    elif asset.startswith('pkinit-kdc-'):
        if subprocess.run(['ps', '-C', 'kdc'],
                          capture_output = True).returncode == 0:
            print('sending SIGHUP to all \'kdc\' processes?!?!')
            subprocess.run(['killall', '-s', 'HUP', 'kdc'],
                           capture_output = True)
    elif asset.startswith('keytab-'):
        if not os.path.exists('/etc/krb5.keytab'):
            print(f"linking /etc/krb5.keytab -> {asset}")
            subprocess.run(['ln', '-s', f"{os.getcwd()}/{asset}", '/etc/krb5.keytab'])
    elif asset == 'krb5.conf':
        if not os.path.exists('/etc/krb5.conf'):
            print(f"linking /etc/krb5.conf -> {asset}")
            subprocess.run(['ln', '-s', f"{os.getcwd()}/{asset}", '/etc/krb5.conf'])

else:
    raise Exception(f"Bad phase: {phase}")
