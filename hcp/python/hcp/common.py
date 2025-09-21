import os
import sys
import json
import psutil
import pwd
import glob
import subprocess
import getpass
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(1, '/hcp/python')

import gson.path as pat
import gson.mutater as mut

# Equivalent for the 'touch' command
def touch(p, *, makedirs = True):
	if makedirs:
		d = os.path.dirname(p)
		if not os.path.isdir(d):
			os.makedirs(d, mode = 0o755)
	with open(p, 'a'):
		os.utime(p, None)

# This is rudimentary: level 0 is for stuff that will go to stderr no matter
# what, level 1 is for stuff that should go to stderr if you actually want to
# debug anything, and level 2 is for stuff whose absence might be desirable if
# someone is debugging but wants less of a firehose.
#
# - def_loglevel is the log level to assume for callers to log()
# - current_loglevel is the maximum level to let through to stderr (anything
#   higher is dropped)
# - cfg_trace is an optional dict that will exist if a '.trace' field exists in
#   the current config. When it exists, we make decisions on where and how to
#   log.
def_loglevel = 1
current_loglevel = 0

if 'VERBOSE' in os.environ:
	current_loglevel = int(os.environ['VERBOSE'])

def hlog(level, s):
	global current_loglevel
	if level > current_loglevel:
		return
	print(s, file = sys.stderr)
	sys.stderr.flush()

def log(s):
	global def_loglevel
	hlog(def_loglevel, s)

def bail(s, exitcode = 1):
	hlog(0, f"FAIL: {s}")
	sys.exit(exitcode)

# Don't forget, this API shares semantics with pat.extract_path(). Most
# notably, it returns a 2-tuple by default;
#  (boolean success, {dict|list|str|int|None} resultdata)
# unless you set 'must_exist=True' or 'or_default=True'. If 'must_exist' is
# set, this returns only result data and throws an exception if the path
# doesn't exist. If 'or_default' is set, it likewise returns only result data
# and returns a default value if the path doesn't exist. (The default default
# (!) is 'None', but this can be altered by specifying 'default=<val>'.)
def hcp_config_extract(path, **kwargs):
	if 'HCP_CONFIG_FILE' not in os.environ:
		raise Exception("!HCP_CONFIG_FILE")
	if not path.startswith('.'):
		path = f".{path}"
	hlog(3, f"hcp_config_extract: {path}")
	with open(os.environ['HCP_CONFIG_FILE'], 'r') as fp:
		world = json.load(fp)
	return pat.extract_path(world, path, **kwargs)

def env_get(k):
	if not k in os.environ:
		bail(f"Missing environment variable: {k}")
	v = os.environ[k]
	if not isinstance(v, str):
		bail(f"Environment variable not a string: {k}:{v}")
	return v

def env_get_or_none(k):
	if not k in os.environ:
		return None
	v = os.environ[k]
	if not isinstance(v, str):
		return None
	if len(v) == 0:
		return None
	return v

def env_get_dir_or_none(k):
	v = env_get_or_none(k)
	if not v:
		return None
	path = Path(v)
	if not path.is_dir():
		return None
	return v

def env_get_dir(k):
	v = env_get(k)
	path = Path(v)
	if not path.is_dir():
		bail(f"Environment variable not a directory: {k}:{v}")
	return v

def env_get_file(k):
	v = env_get(k)
	path = Path(v)
	if not path.is_file():
		bail(f"Environment variable not a file: {k}:{v}")
	return v

def dict_val_or(d, k, o):
	if k not in d:
		return o
	return d[k]

def dict_pop_or(d, k, o):
	if k not in d:
		return o
	return d.pop(k)

# Given a datetime, produce a string of the form "YYYYMMDDhhmmss" that can
# be used in a filename/path. This gives 1-second granularity and gives
# useful outcomes when such strings get sorted alphabetically.
def datetime2hint(dt):
	s = f"{dt.year:04}{dt.month:02}{dt.day:02}"
	s += f"{dt.hour:02}{dt.minute:02}{dt.second:02}"
	return s

# See the comments for http2exit and exit2http in common/hcp.sh, this is simply
# a python version of the same.
ahttp2exit = {
	200: 20, 201: 21,
	400: 40, 401: 41, 403: 43, 404: 44,
	500: 50
}
aexit2http = {
	20: 200, 21: 201,
	40: 400, 41: 401, 43: 403, 44: 404,
	50: 500, 49: 500, 0: 200
}
def alookup(a, k, d):
	if k in a:
		v = a[k]
	else:
		v = d
	return v
def http2exit(x):
	return alookup(ahttp2exit, x, 49)
def exit2http(x):
	return alookup(aexit2http, x, 500)

def add_install_path(d):
	def _add_path(n, vs):
		current = ''
		if n in os.environ:
			current = os.environ[n]
		for v in vs:
			if not os.path.isdir(v):
				continue
			if len(current) > 0:
				current = f"{current}:{v}"
			else:
				current = v
		os.environ[n] = current
	_add_path('PATH',
		[ f"{d}/bin", f"{d}/sbin", f"{d}/libexec" ])
	_add_path('LD_LIBRARY_PATH',
		[ f"{d}/lib", f"{d}/lib/python/dist-packages" ])

installdirs = glob.glob('/install-*')
for i in installdirs:
	add_install_path(i)
