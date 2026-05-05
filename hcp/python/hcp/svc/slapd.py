#!/usr/bin/python3

import os
import sys
import subprocess
import argparse
import time
import shutil

import hcp.common as h

myinstance = h.hcp_config_extract(".vars.id", must_exist = True)

# TBD: make the following depend on myinstance, somehow
etcparent = '/etc/hcp'
myetc = f"{etcparent}/slapd.d"

try:
	verbosity = int(os.environ['VERBOSE'])
except:
	verbosity = 1

parser = argparse.ArgumentParser()
parser.add_argument("--healthcheck", action = "store_true",
		help = "check that slapd is running ok")
parser.add_argument("--hup", action = "store_true",
		help = "send SIGHUP to currently-running slapd")
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

if args.healthcheck:
	raise Exception('healthcheck not implemented')

if args.hup:
	raise Exception('hup not implemented')

if os.path.exists(myetc):
	etcold = f"{myetc}.old"
	if os.path.exists(etcold):
		h.hlog(1, "Deleting really old config")
		shutil.rmtree(etcold)
	h.hlog(1, "Moving old config")
	os.rename(myetc, etcold)

print(f"Generating slapd config ({myetc})")

shutil.copytree('/etc/ldap/slapd.d', myetc)
with open(f"{myetc}/cn=config/olcDatabase={{0}}config.ldif", 'a') as fp:
	fp.write('\nolcRootPW: {SSHA}/aoHSjQqNKpYCAL9yl7PYz5et1hz1odN\n')
copied = open(f"{myetc}/cn=config/olcDatabase={{1}}mdb.ldif", 'r').readlines()
with open(f"{myetc}/cn=config/olcDatabase={{1}}mdb.ldif", 'w') as fp:
	for line in copied:
		if line.startswith('olcRootPW:'):
			fp.write('olcRootPW: {SSHA}/aoHSjQqNKpYCAL9yl7PYz5et1hz1odN\n')
		else:
			fp.write(f"{line}\n")
subprocess.run(['chmod', '0755', f"{myetc}/cn=config.ldif"])
subprocess.run(['chmod', '-R', '0755', f"{myetc}/cn=config"])
subprocess.run(['ls', '-lR', '/etc/hcp'])

# slapd expects this directory to exist.
os.makedirs('/var/run/slapd', mode=0o755, exist_ok = True)

print("Starting slapd")
p = subprocess.Popen(
	[
		'slapd',
		'-h', 'ldap:///',
		'-g', 'openldap',
		'-u', 'openldap',
		'-F', myetc,
		'-d', '255'
	],
	text = True)

print("Done.")
p.wait()
