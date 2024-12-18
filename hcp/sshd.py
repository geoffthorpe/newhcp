#!/usr/bin/python3

import os
import sys
import subprocess
import argparse
import time
import shutil

import HcpCommon as h

myinstance = h.hcp_config_extract(".id", must_exist = True)
myport = h.hcp_config_extract('.sshd.port', or_default = True, default = 22)
myxtra = h.hcp_config_extract('.sshd.xtra', or_default = True, default = [])
myhostname = h.hcp_config_extract('.sshd.hostname', or_default = True, default = 'localhost')

myetc = f"/etc/hcp/{myinstance}"
etcsshd = f"{myetc}/sshd"

etcsshdconfig = f"{etcsshd}/config"

try:
	verbosity = int(os.environ['VERBOSE'])
except:
	verbosity = 1

parser = argparse.ArgumentParser()
parser.add_argument("--healthcheck", action = "store_true",
		help = "check that sshd is running ok")
parser.add_argument("--hup", action = "store_true",
		help = "send SIGHUP to currently-running sshd")
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
	h.hlog(1, f"Running ssh-keyscan on localhost:{myport}")
	while True:
		c = subprocess.run(f"ssh-keyscan -p {myport} -t rsa {myhostname}".split(),
			capture_output = True)
		if c.returncode == 0:
			break
		h.hlog(1, f"Failed with code: {c.returncode}")
		h.hlog(2, f"Error output:\n{c.stderr}")
		if args.retries == 0:
			h.hlog(0, "Failure, giving up")
			break
		args.retries = args.retries - 1
		if args.pause > 0:
			h.hlog(2, f"Pausing for {args.pause} seconds")
			time.sleep(args.pause)
	sys.exit(c.returncode)

if args.hup:
	try:
		with open('/var/run/sshd.pid', 'r') as fp:
			pid=int(fp.read())
		print(f"Sending a HUP to sshd process PID={pid}")
		c = subprocess.run(f"kill -HUP {pid}".split())
	except:
		printf('Not sending HUP, no sshd PID file')
	sys.exit(0)

if os.path.exists(etcsshd):
	etcsshdold = f"{etcsshd}.old"
	if os.path.exists(etcsshdold):
		h.hlog(1, "Deleting really old config")
		shutil.rmtree(etcsshdold)
	h.hlog(1, "Moving old config")
	os.rename(etcsshd, etcsshdold)

os.makedirs(etcsshd, exist_ok = True)

ssh_algos = [ 'rsa', 'ecdsa', 'ed25519' ]
for a in ssh_algos:
	print(f"Generating sshd host key ({a})")
	subprocess.run([
		'ssh-keygen', '-N', '', '-t', a,
		'-f', f"{etcsshd}/hostkey_{a}" ])

print(f"Generating sshd config ({etcsshdconfig})")
myenv = {}
for i in [ 'KRB5_CONFIG', 'KRB5_KTNAME', 'HCP_CONFIG_FILE', 'HCP_CONFIG_SCOPE' ]:
	if i in os.environ:
		myenv[i] = os.environ[i]
if len(myenv) > 0:
	mysetenv = 'SetEnv'
	for i in myenv:
		mysetenv += f" {i}={myenv[i]}"
else:
	mysetenv = '# Not setting any environment variables'
with open(f"{etcsshdconfig}", 'w') as fp:
	fp.write('''
# Auto-generated by sshd/run.py
AcceptEnv LANG LC_*
ChallengeResponseAuthentication no
HostbasedAuthentication no
IgnoreRhosts yes
LoginGraceTime 120
LogLevel ERROR
#LogLevel VERBOSE
#LogLevel DEBUG2
PermitEmptyPasswords no
PermitRootLogin without-password
PermitUserEnvironment yes
PidFile /var/run/sshd.{_myinstance}.pid
PrintLastLog yes
PrintMotd no
Protocol 2
PubkeyAuthentication yes
StrictModes yes
Subsystem sftp /usr/lib/openssh/sftp-server
TCPKeepAlive yes
GSSAPIAuthentication yes
GSSAPICleanupCredentials yes
GSSAPIKeyExchange yes
GSSAPIStoreCredentialsOnRekey yes
GSSAPIStrictAcceptorCheck no
PasswordAuthentication no
UsePAM yes
X11DisplayOffset 10
X11Forwarding yes
{_mysetenv}
'''.format(_myinstance = myinstance, _mysetenv = mysetenv))
	for a in ssh_algos:
		fp.write(f"HostKey {etcsshd}/hostkey_{a}\n")
	for a in myxtra:
		fp.write(f"{a}\n")

subprocess.run(f"cat {etcsshdconfig}".split())

# sshd expects this directory to exist.
# TODO: can this be scoped to {etcsshd}?  If we try to run multiple sshd
# instances co-tenant, this might run into trouble.
os.makedirs('/run/sshd', mode=0o755, exist_ok = True)

print("Starting sshd")
p = subprocess.Popen(
	[
		'/usr/sbin/sshd', '-e', '-D',
		'-f', f"{etcsshdconfig}",
		'-p', f"{myport}"
	],
	text = True)

print("Done.")
p.wait()
