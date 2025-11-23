#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

# This is the script invoked by docker (via docker-compose.yml) to determine if
# the container is healthy (exits with 0) or otherwise. You can also run it
# directly to see (on stdout) the healthcheck details.
#
# We interact with the launcher, which is where the healthcheck is actually
# performed, by setting a touchfile (/tmp/do_healthcheck) and then waiting for
# the corresponding output (/tmp/healthcheck) to be produced.

import time
import json
import sys
import os

try:
    os.remove('/tmp/healthcheck')
except FileNotFoundError:
    pass
with open('/tmp/do_healthcheck', 'w') as _:
    pass
# We'll just wait for the healthcheck result. If docker thinks the healthcheck
# is taking too long, it'll kill, so no need to deal with timeouts here.
while not os.path.exists('/tmp/healthcheck'):
    time.sleep(0.5)

with open('/tmp/healthcheck', 'r') as fp:
    hc = json.load(fp)

retcode = 0
for svc in hc:
    x = hc[svc]
    if 'healthy' in x:
        of = sys.stdout
        healthy = x['healthy']
        if not healthy:
            of = sys.stderr
            retcode = 1
        print(f"Service '{svc}' is {'' if healthy else 'not '}healthy",
              file = of)
        if 'cmd' in x:
            print(f"- cmd: {x['cmd']}", file = of)
        if 'stdout' in x:
            print(f"- stdout: {x['stdout']}", file = of)
        if 'stderr' in x:
            print(f"- stderr: {x['stderr']}", file = of)

sys.exit(retcode)
