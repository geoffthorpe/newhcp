#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import json
import os
import sys
import argparse

def write_service(fp, name, data, with_tpm = True):
    fp.write(f"    {name}:\n")
    fp.write('        extends: common_nontpm\n')
    fp.write(f"        hostname: {data['vars']['hostname']}\n")
    fp.write('        volumes:\n')
    if with_tpm:
        fp.write(f"          - tpmsocket_{name}:/tpmsocket_{name}\n")
    vols = data['volumes'] if 'volumes' in data else []
    for item in vols:
        fp.write(f"          - {item}\n")
    fp.write('        environment:\n')
    fp.write(f"          - HCP_CONFIG_FILE=/usecase/hosts/{name}.json\n\n")

def write_tpm(fp, name, data, with_tpm = True):
    fp.write(f"    {name}_tpm:\n")
    fp.write('        extends: common_tpm\n')
    fp.write(f"        hostname: tpm.{data['vars']['hostname']}\n")
    fp.write('        volumes:\n')
    if with_tpm:
        fp.write(f"          - tpm_{name}:/tpm_{name}\n")
        fp.write(f"          - tpmsocket_{name}:/tpmsocket_{name}\n")
    fp.write('        environment:\n')
    fp.write(f"          - HCP_CONFIG_FILE=/usecase/hosts/{name}.json\n\n")

if __name__ == '__main__':
    fleet_desc = 'Parser of fleet.json'
    fleet_epilog = """
TBD
"""
    parser = argparse.ArgumentParser(description=fleet_desc,
                                     epilog=fleet_epilog)
    fleet_help_input = 'path to JSON input, default = usecase/config/fleet.json'
    fleet_help_output = 'path to output, default = docker-compose.yml'
    parser.add_argument('--input', metavar = '<PATH>',
                        default = 'usecase/config/fleet.json',
                        help = fleet_help_input)
    parser.add_argument('--output', metavar = '<PATH>',
                        default = 'docker-compose.yml',
                        help = fleet_help_output)

    # Process the command-line
    args = parser.parse_args()

    _input = json.load(open(args.input, 'r'))
    hosts = [ x for x in _input['fleet'] ]
    with open(args.output, 'w') as fp:
        fp.write("""version: "2.4"

volumes:
    backend:
""")
        for host in hosts:
            fp.write(f"    tpm_{host}:\n")
            fp.write(f"    tpmsocket_{host}:\n")
        for item in _input['volumes']:
            fp.write(f"    {item}:\n")
        fp.write("""
networks:
    hcpnetwork:

services:
    common:
        image: hcp_caboodle:trixie
        init: true
        volumes:
          - ${TOP}/hcp:/hcp:ro
          - ./usecase:/usecase:ro
        environment:
          - HCP_LAUNCHER_TGTS=${HCP_LAUNCHER_TGTS:-}
          - HCP_NOTRACEFILE=1
          - VERBOSE=${VERBOSE:-0}
          - PYTHONPATH=/hcp/python
        healthcheck:
            test: /hcp/python/HcpToolHealthcheck.py
            timeout: 10s
            interval: 20s

    common_tpm:
        extends: common
        network_mode: "none"
        environment:
          - HCP_CONFIG_SCOPE=.tpm

    common_nontpm:
        extends: common
        networks:
          - hcpnetwork
        volumes:
          - ./_testcreds/ca_default:/ca_default:ro
          - ./_testcreds/verifier_asset:/verifier_asset:ro
          - ./_testcreds/cred_healthhttpsclient:/cred_healthhttpsclient:ro

    orchestrator:
        extends: common_nontpm
        hostname: orchestrator.hcphacking.xyz
        volumes:
          - ./_testcreds/cred_enrollclient:/cred_enrollclient:ro
""")
        for host in hosts:
            fp.write(f"          - tpm_{host}:/tpm_{host}\n")
        fp.write("""        environment:
          - HCP_CONFIG_FILE=/usecase/hosts/orchestrator.json

""")
        write_service(fp, 'attestsvc', _input['attestsvc'],
                      with_tpm = False)
        for host in hosts:
            write_service(fp, host, _input['fleet'][host])
            write_tpm(fp, host, _input['fleet'][host])
