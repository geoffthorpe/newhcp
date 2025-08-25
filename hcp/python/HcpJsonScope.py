#!/usr/bin/python3
#
# A "scope" allows a new data structure to be crafted from an existing one.
#
# The general form of "scope" consists of an array (list) of objects (dicts),
# each of which contribute step-wise in constructing the new data structure,
# which starts out as a new/empty JSON object (dict). Each object in the array
# will specify exactly one method key ("set", "delete", "import", or "union")
# to build on that JSON object. The value for the method key, whose value is a
# jq-style path, specifies what path within the new object the method is being
# applied to. The "import" method is the only operation that uses the existing
# data structure (the "source" attribute indicates what path in the existing
# data structure should be copied into the new one), the remaining methods all
# act strictly within the new data structure.

import json
import os

from HcpJsonPath import valid_path, extract_path, overwrite_path, delete_path, \
		HcpJsonPathError
from HcpRecursiveUnion import union
import HcpJsonExpander as he

import sys
def log(s):
	pass

class HcpJsonScopeError(Exception):
	pass

# Method-handling for "scope" constructs.
def scope_valid_common(s, x, n):
	if not isinstance(s[n], str):
		raise HcpJsonScopeError(f"{x}: invalid '{n}' scope")
	try:
		valid_path(s[n])
	except HcpJsonPathError as e:
		raise HcpJsonScopeError(f"{x}: invalid '{n}' path\n{e}")
def scope_valid_set(s, x, n):
	log(f"FUNC scope_valid_set running; {s},{x},{n}")
	scope_valid_common(s, x, n)
	if len(s) != 2 or 'value' not in s:
		raise HcpJsonScopeError(f"{x}: '{n}' must have (only) 'value'")
def scope_valid_delete(s, x, n):
	log(f"FUNC scope_valid_delete running; {s},{x},{n}")
	scope_valid_common(s, x, n)
	if len(s) != 1:
		raise HcpJsonScopeError(f"{x}: '{n}' expects no attributes")
def scope_valid_import(s, x, n):
	log(f"FUNC scope_valid_import running; {s},{x},{n}")
	scope_valid_common(s, x, n)
	if len(s) != 2 or 'source' not in s:
		raise HcpJsonScopeError(f"{x}: '{n}' must have (only) 'source'")
	try:
		valid_path(s['source'])
	except HcpJsonPathError as e:
		raise HcpJsonScopeError(f"{x}: invalid '{n}' source\n{e}")
def scope_valid_union(s, x, n):
	log(f"FUNC scope_valid_union running; {s},{x},{n}")
	scope_valid_common(s, x, n)
	if len(s) != 3 or 'source1' not in s or 'source2' not in s:
		raise HcpJsonScopeError(
			f"{x}: '{n}' requires (only) 'source1' and 'source2'")
	try:
		if s['source1']:
			valid_path(s['source1'])
		valid_path(s['source2'])
	except HcpJsonPathError as e:
		raise HcpJsonScopeError(f"{x}: invalid '{n}' source(s)\n{e}")
def scope_valid_load(s, x, n):
	log(f"FUNC scope_valid_load running; {s},{x},{n}")
	scope_valid_common(s, x, n)
	if len(s) < 2 or 'path' not in s:
		raise HcpJsonScopeError(f"{x}: '{n}' must have (only) 'path'")
	if not os.path.isfile(s['path']):
		raise HcpJsonScopeError(f"{x}: invalid '{n}' path\n")
def scope_valid_vars(s, x, n):
	log(f"FUNC scope_valid_vars running; {s},{x},{n}")
	scope_valid_common(s, x, n)
	if len(s) != 1:
		raise HcpJsonScopeError(f"{x}: '{n}' has no parameters")
	# TODO: add path check to vars path
def scope_run_set(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_set starting; {s},{x},{n}")
	path = s[n]
	value = s['value']
	log(f"path={path}, value={value}")
	res = overwrite_path(datanew, path, value)
	log(f"FUNC scope_run_set ending; {res}")
	return res
def scope_run_delete(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_delete starting; {s},{x},{n}")
	path = s[n]
	log(f"path={path}")
	res = delete_path(datanew, path)
	log(f"FUNC scope_run_delete ending; {res}")
	return res
def scope_run_import(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_import starting; {s},{x},{n}")
	path = s[n]
	source = s['source']
	log(f"path={path}, source={source}")
	ok, value = extract_path(dataold, source)
	if not ok:
		raise HcpJsonScopeError(f"{x}: import: missing '{path}'")
	res = overwrite_path(datanew, path, value)
	log(f"FUNC scope_run_import ending; {res}")
	return res
def scope_run_union(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_union starting; {s},{x},{n}")
	path = s[n]
	source1 = s['source1']
	source2 = s['source2']
	log(f"path={path}, source1={source1}, source2={source2}")
	ok, value2 = extract_path(datanew, source2)
	if not ok:
		raise HcpJsonScopeError(f"{x}: union: missing '{source2}'")
	if source1 is not None:
		ok, value1 = extract_path(datanew, source1)
		if not ok:
			raise HcpJsonScopeError(
				f"{x}: union: missing '{source1}'")
		value = union(value1, value2)
	else:
		value = value2
	res = overwrite_path(datanew, path, value)
	log(f"FUNC scope_run_union ending; {res}")
	return res
def scope_run_load(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_load starting; {s},{x},{n}")
	path = s[n]
	fpath = s['path']
	log(f"path={path}, fpath={fpath}")
	value = json.load(open(fpath, 'r'))
	value = he.process_obj(env, value, currentpath = path,
			varskey = None, fileskey = None)
	res = overwrite_path(datanew, path, value)
	log(f"FUNC scope_run_load ending; {res}")
	return res
def scope_run_loadunion(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_loadunion starting; {s},{x},{n}")
	path = s[n]
	fpath = s['path']
	log(f"path={path}, fpath={fpath}")
	value = json.load(open(fpath, 'r'))
	value = he.process_obj(env, value, currentpath = path,
			varskey = None, fileskey = None)
	ok, evalue = extract_path(datanew, path)
	if ok:
		if n == 'loadunion':
			value = union(value, evalue)
		elif n == 'unionload':
			value = union(evalue, value)
		else:
			raise Exception("BUG")
	res = overwrite_path(datanew, path, value)
	log(f"FUNC scope_run_loadunion ending; {res}")
	return res
def scope_run_vars(s, x, n, datanew, dataold, env):
	log(f"FUNC scope_run_vars starting; {s},{x},{n}")
	path = s[n]
	ok, value = extract_path(datanew, path)
	if not ok:
		raise HcpJsonScopeError(f"{x}: vars: missing '{path}'")
	if isinstance(value, dict):
		for k in value:
			env[k] = value[k]
		delete_path(datanew, path)
	log(f"FUNC scope_run_vars ending")
	return datanew

scopemeths = {
	'set': { 'is_valid': scope_valid_set, 'run': scope_run_set },
	'delete': { 'is_valid': scope_valid_delete, 'run': scope_run_delete },
	'import': { 'is_valid': scope_valid_import, 'run': scope_run_import },
	'union': { 'is_valid': scope_valid_union, 'run': scope_run_union },
	'load': { 'is_valid': scope_valid_load, 'run': scope_run_load },
	'loadunion': { 'is_valid': scope_valid_load, 'run': scope_run_loadunion },
	'unionload': { 'is_valid': scope_valid_load, 'run': scope_run_loadunion },
	'vars': { 'is_valid': scope_valid_vars, 'run': scope_run_vars }
}

# Parse a "scope" list
def parse_scope(s, x):
	log("FUNC parse_scope starting; {scope}")
	# If 's' is a simple string, convert it to the general form.
	if isinstance(s, str):
		s = [ { "import": ".", "source": s } ]
	if not isinstance(s, list):
		raise HcpJsonScopeError(f"{x}: scope: bad type '{type(s)}'")
	# Iterate through the list of constructs for this scope
	for c in s:
		# Must have exactly one method. Note this logic closely follows
		# the 'if' handling in parse_filter().
		m = set(scopemeths.keys()).intersection(c.keys())
		if len(m) == 0:
			raise HcpJsonScopeError(
				f"{x}: scope: no method in {c}")
		if len(m) != 1:
			raise HcpJsonScopeError(
				f"{x}: scope: too many methods in {c} ({m})")
		m = m.pop()
		log(f"Processing method '{m}'")
		meth = scopemeths[m]
		meth['is_valid'](c, x, m)
		c['meth'] = m
	log("FUNC parse_scope ending")
	return s

# Run an already-parsed 'scope' against data, returning the transformed data
def run_scope(data, scope, x, scopemeths = scopemeths):
	log(f"FUNC run_scope starting; {x},{scope},{data}")
	result = {}
	env = {}
	for c in scope:
		methkey = c['meth']
		meth = scopemeths[methkey]
		result = meth['run'](c, x, methkey, result, data, env)
	log(f"FUNC run_scope ending")
	return result

if __name__ == '__main__':

	fp = sys.stdin
	if len(sys.argv) > 1:
		fp = open(sys.argv[1], 'r')

	j = json.load(fp)
	if isinstance(j, dict) and 'scope' in j:
		rb = j.pop('scope')
		parse_scope(rb, 'null')
		j = run_scope(j, rb, 'null')
	json.dump(j, sys.stdout)
