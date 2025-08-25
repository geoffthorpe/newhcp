#!/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import argparse
import sys
import json
import gson.path as p

# Perform variable-expansion on a string. NB there's a special case for
# variables that aren't set to strings. E.g. if env['somevar'] is a dict or a
# list, then expanding the string "{somevar}" will actually expand to that
# non-string value.
def expand_str(s, env):
    for k in env:
        keystr = '{' + k + '}'
        v = env[k]
        if isinstance(v, str):
            s = s.replace(keystr, v)
        else:
            if s == keystr:
                return v
    return s

# Augment an environment using the given variables
def merge_env(env, varsobj):
    env = env.copy() if env else {}
    for k in varsobj:
        env[k] = varsobj[k]
    return env

# Perform variable-expansion on a set of variables!
def expand_vars(varsobj, env, varskey = 'vars'):
    newvarsobj = None
    while not varsobj == newvarsobj: # deep comparison
        if not newvarsobj:
            newvarsobj = varsobj
        varsobj = newvarsobj
        newenv = merge_env(env, varsobj)
        newvarsobj = expand(varsobj, newenv, varskey = varskey)
    return varsobj

# Perform variable-expansion on/within the given 'obj'
def expand(obj, env = None, varskey = 'vars'):
    if isinstance(obj, str):
        return expand_str(obj, env)
    if isinstance(obj, list):
        return [ expand(item, env = env, varskey = varskey) for item in obj ]
    if isinstance(obj, dict):
        retobj = {}
        varsobj = obj.pop(varskey) if varskey in obj else None
        if varsobj:
            varsobj = expand_vars(varsobj, env)
            env = merge_env(env, varsobj)
        for item in obj:
            newitem = expand(item, env = env, varskey = varskey)
            val = expand(obj[item], env = env, varskey = varskey)
            retobj[newitem] = val
        if varsobj and varskey not in retobj:
            retobj[varskey] = varsobj
        return retobj
    return obj

def build_env(obj, pathlist, env = None, varskey = 'vars'):
    env = env if env else {}
    while len(pathlist) > 0:
        if isinstance(obj, dict) and varskey in obj:
            varsobj = obj[varskey]
            for k in varsobj:
                env[k] = varsobj[k]
        step = pathlist.pop(0)
        obj = obj[step]
    return env

def expand_path(obj, path, env = None, varskey = 'vars', noParent = False):
    pathlist = p.path_deconstruct(path)
    before = p.path_get(obj, pathlist)
    env = build_env(obj, pathlist, env = env, varskey = varskey) \
          if not noParent else None
    after = expand(obj, env = env, varskey = varskey)
    obj = p.path_set(obj, pathlist, json.dumps(after))
    return obj

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'GSON expander',
                                     epilog = 'TBD')
    parser.add_argument('-i', '--input', metavar = '<PATH>',
                        default = '-',
                        help = 'Specify input file, \'-\' for stdin')
    parser.add_argument('-o', '--output', metavar = '<PATH>',
                        default = '-',
                        help = 'Specify output file, \'-\' for stdout')
    parser.add_argument('-c', '--compare', metavar = '<PATH>',
                        default = None,
                        help = 'Specify expected output, for comparison')
    parser.add_argument('-k', '--varskey', metavar = '<KEY>',
                        default = 'vars',
                        help = 'Use a different key name for var expansion')
    args = parser.parse_args()
    fpin = sys.stdin if args.input == '-' else open(args.input, 'r')
    fpout = sys.stdout if args.output == '-' else open(args.output, 'w')
    expected = json.load(open(args.compare, 'r')) if args.compare else None
    output = expand(json.load(fpin), varskey = args.varskey)
    json.dump(output, fpout)
    print() # newline is a courtesy to cmd-line usage
    if args.compare and not output == expected: # deep comparison
        print("Error, output mismatch", file = sys.stderr)
        sys.exit(-1)
