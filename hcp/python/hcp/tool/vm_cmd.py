#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

# This script is used in the context of a runner in order to inject a command
# into the VM. If -i is used, stdin will be consumed (up to EOF) and passed to
# the injected command. The result contains all the detail, including the
# (string) stdout and stderr from the command.

import json
import sys
import os
import time

# Remove stale output (from prior commands)
if os.path.exists('/tmp/cmd'):
    os.remove('/tmp/cmd')

# Strip this command from sys.argv, the remaining arguments are the command to
# be executed within the VM.
sys.argv.pop(0)

instring = ''
if sys.argv[0] == '-i':
    instring = sys.stdin.read()
    sys.argv.pop(0)
elif sys.argv[0] == '--':
    sys.argv.pop(0)

cmd = {
    'cmd': sys.argv,
    'input': instring
}

with open('/tmp/do_cmd.tmp', 'w') as fp:
    json.dump(cmd, fp)
os.rename('/tmp/do_cmd.tmp', '/tmp/do_cmd')

while not os.path.exists('/tmp/cmd'):
    time.sleep(0.5)
with open('/tmp/cmd', 'r') as fp:
    res = json.load(fp)

if 'stdout' in res:
    print(res['stdout'], end='')
if 'stderr' in res:
    print(res['stderr'], end='', file = sys.stderr)
sys.exit(res['returncode'])
