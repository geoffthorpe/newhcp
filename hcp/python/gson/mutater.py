#!/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import argparse
import os
import sys
import json
import copy
import gson.expander as x
import gson.path as p

def _internal(step):
    return step['register'] if 'register' in step else 'output', \
           step['regpath'] if 'regpath' in step else '.', \
           step['srcregister'] if 'srcregister' in step else 'origin', \
           step['srcregpath'] if 'srcregpath' in step else '.'

def method_expand(registers, step):
    regname, regpath, _, _ = _internal(step)
    varskey = step['varskey'] if 'varskey' in step else 'vars'
    noParent = step['noParent'] if 'noParent' in step else False
    registers[regname] = x.expand_path(registers[regname],
                                       regpath,
                                       varskey = varskey,
                                       noParent = noParent)

def method_load(registers, step):
    regname, regpath, _, _ = _internal(step)
    jspath = step['jspath']
    valjson = open(jspath, 'r').read()
    pathlist = p.path_deconstruct(regpath)
    current = registers[regname] if regname in registers else None
    registers[regname] = p.path_set(current, pathlist, valjson)

def method_set(registers, step):
    regname, regpath, _, _ = _internal(step)
    val = step['value']
    pathlist = p.path_deconstruct(regpath)
    current = registers[regname] if regname in registers else None
    registers[regname] = p.path_set(current, pathlist,
                                    json.dumps(val))

def method_copy(registers, step):
    regname, regpath, srcregname, srcregpath = _internal(step)
    pathlist = p.path_deconstruct(regpath)
    srcpathlist = p.path_deconstruct(srcregpath)
    val = p.path_get(registers[srcregname], srcpathlist)
    current = registers[regname] if regname in registers else None
    registers[regname] = p.path_set(current, pathlist,
                                    json.dumps(val))

def method_remove(registers, step):
    regname, regpath, _, _ = _internal(step)
    pathlist = p.path_deconstruct(regpath)
    if len(pathlist) == 0:
        registers.pop(regname)
    else:
        current = registers[regname] if regname in registers else None
        registers[regname] = p.path_remove(current, pathlist)

def method_union(registers, step):
    regname, regpath, srcregname, srcregpath = _internal(step)
    underlay = step['underlay'] if 'underlay' in step else False
    noDictUnion = step['noDictUnion'] if 'noDictUnion' in step else False
    noListUnion = step['noListUnion'] if 'noListUnion' in step else False
    listDedup = step['listDedup'] if 'listDedup' in step else False
    pathlist = p.path_deconstruct(regpath)
    srcpathlist = p.path_deconstruct(srcregpath)
    val = p.path_get(registers[srcregname], srcpathlist)
    current = registers[regname] if regname in registers else None
    registers[regname] = p.path_union(current, pathlist,
                                      json.dumps(val), underlay,
                                      noDictUnion = noDictUnion,
                                      noListUnion = noListUnion,
                                      listDedup = listDedup)

methods = {
    'expand': method_expand,
    'load': method_load,
    'set': method_set,
    'copy': method_copy,
    'remove': method_remove,
    'union': method_union
}

# Perform mutation on/within the given 'obj'
def mutate(obj, mutatekey = 'mutate'):
    if not isinstance(obj, dict) or mutatekey not in obj:
        return obj
    output = {}
    obj = copy.deepcopy(obj)
    mutate = obj.pop(mutatekey)
    if not isinstance(mutate, list):
        raise Exception("'mutate' field must be a list")
    registers = {
        'origin': obj,
        'output': None
    }
    for step in mutate:
        if not isinstance(step, dict):
            raise Exception("'mutate' steps must be dict objects")
        if 'method' not in step:
            continue
        method = step['method']
        if method not in methods:
            raise Exception(f"'mutate' doesn't recognize method: {method}")
        methods[method](registers, step)
    return registers['output']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'GSON mutater',
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
    parser.add_argument('-k', '--mutatekey', metavar = '<KEY>',
                        default = 'mutate',
                        help = 'Use a different key name for mutation')
    parser.add_argument('-C', '--changedir', metavar = '<DIR>',
                        default = None,
                        help = 'Perform operations relative to directory')
    args = parser.parse_args()
    if args.changedir:
        os.chdir(args.changedir)
    fpin = sys.stdin if args.input == '-' else open(args.input, 'r')
    fpout = sys.stdout if args.output == '-' else open(args.output, 'w')
    expected = json.load(open(args.compare, 'r')) if args.compare else None
    output = mutate(json.load(fpin), mutatekey = args.mutatekey)
    json.dump(output, fpout)
    print() # newline is a courtesy to cmd-line usage
    if args.compare and not output == expected: # deep comparison
        print("Error, output mismatch", file = sys.stderr)
        sys.exit(-1)
