#!/usr/bin/python3

import sys
import os
import subprocess
import time

from HcpCommon import log, bail, current_tracefile, hcp_config_extract

_period = hcp_config_extract('.keytabber.period', must_exist = True)
_retry = hcp_config_extract('.keytabber.retry', or_default = True, default = _period)
_until = hcp_config_extract('.keytabber.until', or_default = True)
try:
	period = int(_period)
	retry = int(_retry)
except ValueError as e:
	log(f"ERROR: .keytabber.{period,retry} ({_period},{_retry}) must be numbers")
	log(f"{e}")
	sys.exit(1)
cmd_args = [ '/hcp/tools/run_keytabclient.sh' ]

log(f"Starting keytabber")
log(f" - period={period}")
log(f" - cmd_args={cmd_args}")

while True:
	res = 0
	try:
		log("Running command")
		c = subprocess.run(cmd_args, stderr = current_tracefile,
				text = True)
		res = c.returncode
	except Exception as e:
		log(f"Warning, exception: {e}")
		res = -1
	log(f"Command exited with code={res}")
	if res == 0:
		if _until:
			open(_until, 'w')
		time.sleep(period)
	else:
		time.sleep(retry)
