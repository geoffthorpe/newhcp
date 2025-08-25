#!/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import argparse
import sys
import json

def union(a, b, noDictUnion = False, noListUnion = False, listDedup = False):
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

if __name__ == '__main__':
    # Main command
    parser = argparse.ArgumentParser(description = 'GSON recursive union',
                                     epilog = 'TBD')
    parser.add_argument('-i', '--input1', metavar = '<PATH>',
                        default = '-',
                        help = 'Specify first input file, \'-\' for stdin')
    parser.add_argument('-o', '--output', metavar = '<PATH>',
                        default = '-',
                        help = 'Specify output file, \'-\' for stdout')
    parser.add_argument('-u', '--underlay', action = 'store_true',
                        help = 'Input2 goes underneath input1, rather than over')
    parser.add_argument('--noDictUnion', action = 'store_true',
                        help = 'Choose between dicts rather than merging')
    parser.add_argument('--noListUnion', action = 'store_true',
                        help = 'Choose between lists rather than merging')
    parser.add_argument('--listDedup', action = 'store_true',
                        help = 'De-duplicate merged lists')
    parser.add_argument('input2', help = 'Second input file')

    args = parser.parse_args()
    fpin1 = sys.stdin if args.input == '-' else open(args.input1, 'r')
    fpin2 = open(args.input2, 'r')
    fpout = sys.stdout if args.output == '-' else open(args.output, 'w')
    _input1 = json.load(fpin1)
    _input2 = json.load(fpin2)
    if args.underlay:
        tmp = _input1
        _input1 = _input2
        _input2 = tmp
    print(json.dumps(union(_input1, _input2,
                           noDictUnion = args.noDictUnion,
                           noListUnion = args.noListUnion,
                           listDedup = args.listDedup)))
