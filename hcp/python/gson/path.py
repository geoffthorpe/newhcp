#!/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import argparse
import sys
import json

def path_pop_member(path):
    member = ''
    while len(path) > 0 and path[0] != '.' and path[0] != '[':
        c = path[0]
        path = path[1:]
        if c == '\\' and len(path) > 0 and path[0] == '.':
            c = '.'
            path = path[1:]
        if c == '\\' and len(path) > 0 and path[0] == '[':
            c = '['
            path = path[1:]
        member += c
    return path, member

def path_pop_index(path):
    c = ''
    while len(path) > 0 and path[0] != ']':
        c += path[0]
        path = path[1:]
    try:
        index = int(c)
    except:
        raise Exception('Invalid index in GSON path')
    if len(path) == 0:
        raise Exception('Unclosed index in GSON path')
    if path[0] != ']':
        raise Exception('BUG')
    return path[1:], index

def path_deconstruct(path):
    l = []
    while len(path) > 0 and path != '.':
        if path[0] == '[':
            path, index = path_pop_index(path[1:])
            l.append(index)
        elif path[0] == '.':
            path, member = path_pop_member(path[1:])
            l.append(member)
        else:
            path, member = path_pop_member(path)
            l.append(member)
    return l

def path_exists(obj, pathlist):
    while len(pathlist) > 0:
        step = pathlist.pop(0)
        if step not in obj:
            return False
        obj = obj[step]
    return True

def path_get(obj, pathlist):
    while len(pathlist) > 0:
        step = pathlist.pop(0)
        obj = obj[step]
    return obj

# Compatibility interface from the old HcpJsonPath code. It would be preferable
# to get rid of this. Without 'must_exist' or 'or_default', this function
# returns a 2-tuple, which can lead to weird bugs caller-side if it's expecting
# a single output.
def extract_path(obj, path, must_exist = False, or_default = False,
                 default = None):
    def convert(exists, element):
        if not must_exist and not or_default:
            return (exists, element)
        if exists:
            return element
        if or_default:
            return default
        raise Exception("Non-existent path into object")
    pathlist = path_deconstruct(path)
    try:
        result = path_get(obj, pathlist)
    except:
        return convert(False, None)
    return convert(True, result)

def path_set(obj, pathlist, valjson):
    valobj = json.loads(valjson)
    if len(pathlist) == 0:
        return valobj
    retobj = obj
    while len(pathlist) > 1:
        step = pathlist.pop(0)
        obj = obj[step]
    step = pathlist.pop(0)
    obj[step] = valobj
    return retobj

def path_remove(obj, pathlist):
    if len(pathlist) == 0:
        return None
    retobj = obj
    while len(pathlist) > 1:
        step = pathlist.pop(0)
        obj = obj[step]
    step = pathlist.pop(0)
    obj.pop(step)
    return retobj

def union(a, b, noDictUnion, noListUnion, listDedup):
    ta = type(a)
    tb = type(b)
    if ta != tb:
        return b
    if ta == dict and not noDictUnion:
        result = a.copy()
        for i in b:
            if i in a:
                result[i] = union(a[i], b[i],
                                  noDictUnion, noListUnion, listDedup)
            else:
                result[i] = b[i]
        return result
    if ta == list and not noListUnion:
        c = a + b
        if listDedup:
            d = list()
            for i in c:
                if i not in d:
                    d.append(i)
            c = d
        return c
    return b

def cb_underlay(old, new, noDictUnion, noListUnion, listDedup):
    return union(new, old, noDictUnion, noListUnion, listDedup)

def cb_overlay(old, new, noDictUnion, noListUnion, listDedup):
    return union(old, new, noDictUnion, noListUnion, listDedup)

def path_union(obj, pathlist, valjson, underlay,
               noDictUnion = False,
               noListUnion = False,
               listDedup = True):
    valobj = json.loads(valjson)
    if obj == None:
        return valobj
    cb = cb_underlay if underlay else cb_overlay
    if len(pathlist) == 0:
        return cb(obj, valobj, noDictUnion, noListUnion, listDedup)
    retobj = obj
    while len(pathlist) > 1:
        step = pathlist.pop(0)
        obj = obj[step]
    step = pathlist.pop(0)
    tmp = obj[step] if step in obj else None
    obj[step] = cb(tmp, valobj, noDictUnion, noListUnion, listDedup)
    return retobj

if __name__ == '__main__':
    # Main command
    parser = argparse.ArgumentParser(description = 'GSON path manipulations',
                                     epilog = 'TBD')
    parser.add_argument('-i', '--input', metavar = '<PATH>',
                        default = '-',
                        help = 'Specify input file, \'-\' for stdin')
    parser.add_argument('-o', '--output', metavar = '<PATH>',
                        default = '-',
                        help = 'Specify output file, \'-\' for stdout')
    subparsers = parser.add_subparsers()
    # Subcommand 'parse'
    parser_a = subparsers.add_parser('parse',
                                     help = 'Parse the given path',
                                     epilog = 'TBD')
    parser_a.add_argument('path', help = 'JQ-style path to parse')
    parser_a.set_defaults(func = 'parse', fname = 'parse')
    # Subcommand 'get'
    parser_a = subparsers.add_parser('get',
                                     help = 'Retrieve the object at the given path',
                                     epilog = 'TBD')
    parser_a.add_argument('path', help = 'JQ-style path to retrieve')
    parser_a.set_defaults(func = 'get', fname = 'get')
    # Subcommand 'set'
    parser_a = subparsers.add_parser('set',
                                     help = 'Set the object at the given path',
                                     epilog = 'TBD')
    parser_a.add_argument('path', help = 'JQ-style path to set')
    parser_a.add_argument('jsonstr', help = 'encoded JSON to set with')
    parser_a.set_defaults(func = 'set', fname = 'set')
    # Subcommand 'union'
    parser_a = subparsers.add_parser('union',
                                     help = 'Combine the object at the given path',
                                     epilog = 'TBD')
    parser_a.add_argument('-u', '--underlay', action = 'store_true',
                          help = 'Opposite of the default \'overlay\' behavior')
    parser_a.add_argument('--noDictUnion', action = 'store_true',
                          help = 'Choose between dicts rather than merging')
    parser_a.add_argument('--noListUnion', action = 'store_true',
                          help = 'Choose between lists rather than merging')
    parser_a.add_argument('--listDedup', action = 'store_true',
                          help = 'De-duplicate merged lists')
    parser_a.add_argument('path', help = 'JQ-style path for union')
    parser_a.add_argument('jsonstr', help = 'encoded JSON to union with')
    parser_a.set_defaults(func = 'union', fname = 'union')

    args = parser.parse_args()
    pathlist = path_deconstruct(args.path)
    if args.func == 'parse':
        print(json.dumps(pathlist))
    else:
        fpin = sys.stdin if args.input == '-' else open(args.input, 'r')
        fpout = sys.stdout if args.output == '-' else open(args.output, 'w')
        _input = json.load(fpin)
        if args.func == 'get':
            print(json.dumps(path_get(_input, pathlist)))
        elif args.func == 'set':
            print(json.dumps(path_set(_input, pathlist, args.jsonstr)))
        elif args.func == 'union':
            print(json.dumps(path_union(_input, pathlist,
                                        args.jsonstr, args.underlay,
                                        noDictUnion = args.noDictUnion,
                                        noListUnion = args.noListUnion,
                                        listDedup = args.listDedup)))
        else:
            raise Exception('BUG')
