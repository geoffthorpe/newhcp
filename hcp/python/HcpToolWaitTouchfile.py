#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import sys
import time

sys.path.insert(1, '/hcp/common')
from HcpCommon import bail, log, hlog

if len(sys.argv) < 2:
	bail("'HcpToolWaitTouchfile' expects a path argument")

p = sys.argv[1]
log(f"HcpToolWaitTouchfile({p}) starting")

while not os.path.isfile(p):
	hlog(2, f"touchfile {p} doesn't exist yet")
	time.sleep(1)

log(f"HcpToolWaitTouchfile({p}) done")
