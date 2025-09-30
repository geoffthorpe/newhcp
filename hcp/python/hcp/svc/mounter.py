#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4: 

import sys
import os
import subprocess
import time

from hcp.common import hcp_config_extract

_mounts = hcp_config_extract('.mounter.mounts', or_default = True)
hostip = os.environ['HOSTIP'] if 'HOSTIP' in os.environ else None

print(f"Starting mounter")
print(f" - mounts={_mounts}")

if _mounts:
    print('Updating /etc/fstab')
    with open('/etc/fstab', 'a') as fp:
        for tgt in _mounts:
            src = _mounts[tgt]
            print(f"  {tgt}  <--  {src}")
            opts = 'sec=krb5p'
            if hostip:
                opts = opts + f",clientaddr={hostip}"
            fp.write(f"{src} {tgt} nfs {opts} 0 0\n")
    print('Running \'systemctl daemon-reload\'')
    subprocess.run(['systemctl', 'daemon-reload'])
    print('Running \'mount -a\'')
    subprocess.run(['mount', '-a'])
else:
    print('Nothing to mount')
