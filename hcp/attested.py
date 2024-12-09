#!/usr/bin/python3

import os
import sys
import subprocess
import argparse
import time
import shutil

sys.path.insert(1, '/hcp/common')
import HcpCommon as h

mytouchfile = h.hcp_config_extract(".attester.until", must_exist = True)

try:
	verbosity = int(os.environ['VERBOSE'])
except:
	verbosity = 1

parser = argparse.ArgumentParser()
parser.add_argument("-R", "--retries", type = int, default = 0,
		help = "for healthcheck, max # of retries")
parser.add_argument("-P", "--pause", type = int, default = 1,
		help = "for healthcheck, pause (seconds) between retries")
parser.add_argument("-v", "--verbose", default = 0, action = "count",
		help = "increase output verbosity")
parser.add_argument("-V", "--less-verbose", default = 0, action = "count",
		help = "decrease output verbosity")
args = parser.parse_args()
verbosity = verbosity + args.verbose - args.less_verbose
h.current_loglevel = verbosity
os.environ['VERBOSE'] = f"{verbosity}"

h.hlog(1, f"Running attested.py")
while not os.path.isfile(mytouchfile):
	h.hlog(1, f"Doesn't exist yet")
	if args.retries == 0:
		h.hlog(0, "Failure, giving up")
		sys.exit(1)
	args.retries = args.retries - 1
	if args.pause > 0:
		h.hlog(2, f"Pausing for {args.pause} seconds")
		time.sleep(args.pause)
