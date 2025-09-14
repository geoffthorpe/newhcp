#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import json
import os
import sys
import argparse
import copy

from gson.expander import expand

def docker_write_service(fp, name, data, with_sidecar = True, with_cotenant = False):
    is_vm = data['vm'] if 'vm' in data else False
    baseimg = 'common_vm' if is_vm else 'common_nontpm'
    print(f"Writing service '{name}' to docker compose file")
    fp.write(f"    {name}:\n")
    fp.write(f"        extends: {baseimg}\n")
    fp.write(f"        hostname: {data['hostname']}\n")
    vols = data['volumes'] if 'volumes' in data else []
    if with_sidecar or with_cotenant or len(vols) > 0:
        fp.write('        volumes:\n')
    if with_cotenant:
        fp.write(f"          - tpm_{name}:/tpm_{name}\n")
    elif with_sidecar:
        fp.write(f"          - tpmsocket_{name}:/tpmsocket_{name}\n")
    for item in vols:
        fp.write(f"          - {item}\n")
    fp.write('        environment:\n')
    mutate = f"{name}_runner" if is_vm else name
    fp.write(f"          - HCP_CONFIG_MUTATE=/_usecase/{mutate}.json\n\n")

def docker_write_sidecar(fp, name, data, with_tpm = True):
    print(f"Writing service '{name}_tpm' to docker compose file")
    fp.write(f"    {name}_tpm:\n")
    fp.write('        extends: common_tpm\n')
    fp.write(f"        hostname: tpm.{data['hostname']}\n")
    fp.write('        volumes:\n')
    if with_tpm:
        fp.write(f"          - tpm_{name}:/tpm_{name}\n")
        fp.write(f"          - tpmsocket_{name}:/tpmsocket_{name}\n")
    fp.write('        environment:\n')
    fp.write(f"          - HCP_CONFIG_MUTATE=/_usecase/{name}_tpm.json\n\n")

def produce_host_config(host, _input, outputdir):
    if host != 'attestsvc' and host != 'orchestrator' and \
                            host not in hosts:
        raise Exception(f"'{host}' is not a known fleet host id")
    print(f"Producing '{host}' config file")
    in_fleet = host in _input['fleet']
    if in_fleet:
        data = _input['fleet'][host]
    else: # host == attestsvc or host == orchestrator
        data = _input[host]
    hostname = data['hostname'] if 'hostname' in data else 'nada'
    tpm_mode = data['tpm']
    if tpm_mode not in [ 'none', 'sidecar', 'cotenant', 'unmanaged' ]:
        raise Exception(f"Unrecognised tpm_mode: {tpm_mode}")
    is_vm = data['vm'] if 'vm' in data else False
    servicenames = [ k for k in data['services']] \
        if 'services' in data else []
    output = {
        'vars': {
            'id': host,
            'hostname': hostname,
            'domain': _input['vars']['domain'],
            'realm': _input['vars']['realm']
        },
        'mutate': [
            { 'method': 'load', 'jspath': '/usecase/proto/root.json' },
            { 'method': 'union' }
        ]
    }
    if is_vm:
        output_runner = {
            'vars': {
                'id': host,
                'hostname': hostname,
                'domain': _input['vars']['domain'],
                'realm': _input['vars']['realm']
            },
            'mutate': [
                { 'method': 'load', 'jspath': '/usecase/proto/root.json' },
                { 'method': 'union' },
                { 'method': 'load', 'register': 'd',
                  'jspath': '/usecase/proto/defaults.json' },
                { 'method': 'union', 'regpath': 'vars',
                  'srcregister': 'd', 'underlay': True },
                { 'method': 'load', 'regpath': 'qemu',
                  'jspath': '/usecase/proto/qemu.json' },
                { 'method': 'set', 'register': 'e',
                  'value': {
                      'VM_HCP_CONFIG_MUTATE': f"/_usecase/{host}.json"
                  } },
                { 'method': 'union', 'srcregister': 'e',
                  'regpath': 'env' }
            ]
        }
    if tpm_mode == 'sidecar':
        output_tpm = {
            'vars': {
                'id': f"tpm.{host}",
                'hostname': f"tpm.{hostname}",
                'machine': host,
                'domain': _input['vars']['domain'],
                'realm': _input['vars']['realm']
            },
            'mutate': [
                { 'method': 'load', 'jspath': '/usecase/proto/root.json' },
                { 'method': 'union' },
                { 'method': 'load', 'register': 'd',
                  'jspath': '/usecase/proto/defaults.json' },
                { 'method': 'union', 'regpath': 'vars',
                  'srcregister': 'd', 'underlay': True },
                { 'method': 'load', 'regpath': 'swtpm',
                  'jspath': '/usecase/proto/tpm_sidecar.json' },
                { 'method': 'expand' }
            ]
        }
    if 'vars' in _input:
        for k in _input['vars']:
            if k not in output['vars']:
                output['vars'][k] = _input['vars'][k]
    if 'rootproto' in data:
        for service in data['rootproto']:
            rp = data['rootproto'][service]
            if rp:
                for k in rp:
                    output['vars'][f"{service}_{k}"] = rp[k]
            output['mutate'].append({
                'method': 'load',
                'register': 'a',
                'jspath': f"/usecase/proto/{service}.json"})
            output['mutate'].append({
                'method': 'union',
                'srcregister': 'a'})
    output['mutate'].append({ 'method': 'load', 'register': 'd',
                              'jspath': '/usecase/proto/defaults.json'})
    output['mutate'].append({ 'method': 'union', 'regpath': 'vars',
                              'srcregister': 'd', 'underlay': True})
    if tpm_mode == 'cotenant':
        output['mutate'].append({ 'method': 'load', 'regpath': 'swtpm',
                                  'jspath': '/usecase/proto/tpm_cotenant.json'})
    services = data['services'] if 'services' in data else {}
    for service in services:
        _vars = services[service]
        # Merge any variables into the 'vars' sub-object
        if _vars:
            for k in _vars:
                output['vars'][f"{service}_{k}"] = _vars[k]
        output['mutate'].append({
            'method': 'load',
            'regpath': service,
            'jspath': f"/usecase/proto/{service}.json"})
    env = data['env'] if 'env' in data else []
    for e in env:
        output['mutate'].append({ 'method': 'load', 'register': 'e',
                                  'jspath': f"/usecase/proto/env_{e}.json"})
        output['mutate'].append({ 'method': 'union', 'srcregister': 'e',
                                  'regpath': 'env'})
    # if there is any of "args_for/result_from/foreground" in the input, put it
    # in the output too
    if 'args_for' in data:
        output['args_for'] = data['args_for']
    if 'result_from' in data:
        output['result_from'] = data['result_from']
    if 'foreground' in data:
        output['foreground'] = data['foreground']
    # perform parameter-expansion
    output['mutate'].append({ 'method': 'expand' })
    # Write the host config (the mutate input for it, in any case)
    with open(f"{outputdir}/{host}.json", 'w') as fp:
        json.dump(output, fp, indent = 4)
    if tpm_mode == 'sidecar':
        with open(f"{outputdir}/{host}_tpm.json", 'w') as fp:
            json.dump(output_tpm, fp, indent = 4)
    if is_vm:
        with open(f"{outputdir}/{host}_runner.json", 'w') as fp:
            json.dump(output_runner, fp, indent = 4)

if __name__ == '__main__':
    fleet_desc = 'Parser of fleet.json'
    fleet_epilog = """
        This tool consumes the 'fleet.json' configuration and, by default,
        produces a corresponding docker-compose configuration (in YAML). If
        '--show' is specified, it instead prints the host-ids from the fleet
        configuration to stdout, space-separated. Otherwise, if the optional
        <host> argument is provided, it instead produces the configuration
        for that named host (in JSON).
"""
    parser = argparse.ArgumentParser(description=fleet_desc,
                                     epilog=fleet_epilog)
    fleet_help_input = 'path to JSON input, default = usecase/fleet.json'
    fleet_help_docker = 'path to docker-compose output, default = docker-compose.yml'
    fleet_help_hosts = 'path to directory for host configs, default = _crud/usecase'
    fleet_help_show = 'display the fleet host-ids (modifies no files)'
    fleet_help_host = 'name of host to produce config for (there is no default)'
    parser.add_argument('--input', metavar = '<PATH>',
                        default = 'usecase/fleet.json',
                        help = fleet_help_input)
    parser.add_argument('--docker', metavar = '<PATH>',
                        default = 'docker-compose.yml',
                        help = fleet_help_docker)
    parser.add_argument('--hosts', metavar = '<PATH>',
                        default = '_crud/usecase',
                        help = fleet_help_hosts)
    parser.add_argument('--show', action = 'store_true', help = fleet_help_show)
    parser.add_argument('host', nargs = '?', help = fleet_help_host)

    # Process the command-line
    args = parser.parse_args()

    # Load the input
    _input = json.load(open(args.input, 'r'))
    _input = expand(_input)
    hosts = [ x for x in _input['fleet'] ]
    for x in hosts:
        h = _input['fleet'][x]
        h['tpm'] = h['tpm'] if 'tpm' in h else 'sidecar'
    if 'attestsvc' in hosts:
        raise Exception("'attestsvc' is not a valid fleet host id")
    if 'orchestrator' in hosts:
        raise Exception("'orchestrator' is not a valid fleet host id")
    if 'vars' not in _input or 'domain' not in _input['vars']:
        raise Exception("No 'domain'")
    _input['attestsvc']['tpm'] = 'none'
    _input['orchestrator']['tpm'] = 'none'
    domain = _input['vars']['domain']

    if args.show:
        print(' '.join(hosts + [ 'orchestrator', 'attestsvc' ]))

    elif args.host:
        if not os.path.isdir(args.hosts):
            raise Exception(f"Host config output directory ({args.hosts}) is not a directory")
        produce_host_config(args.host, _input, args.hosts)

    else:

        # Produce docker-compose.yml
        with open(args.docker, 'w') as fp:
            fp.write("""version: "2.4"

volumes:
    backend:
""")
            for host in hosts:
                tpmmode = _input['fleet'][host]['tpm']
                if tpmmode != 'none' and tpmmode != 'unmanaged':
                    fp.write(f"    tpm_{host}:\n")
                if tpmmode == 'sidecar':
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
          - ./_crud/usecase:/_usecase:ro
        environment:
          - HCP_NOTRACEFILE=1
          - VERBOSE=${VERBOSE:-0}
          - PYTHONPATH=/hcp/python
        healthcheck:
            test: /hcp/python/hcp/tool/healthcheck.py
            timeout: 10s
            interval: 20s

    common_tpm:
        extends: common
        network_mode: "none"

    common_nontpm:
        extends: common
        networks:
          - hcpnetwork
        volumes:
          - ./_crud/testcreds/ca_default:/ca_default:ro
          - ./_crud/testcreds/verifier_asset:/verifier_asset:ro
          - ./_crud/testcreds/cred_healthhttpsclient:/cred_healthhttpsclient:ro

    common_vm:
        extends: common_nontpm
        image: hcp_caboodle_qemu:trixie
        volumes:
          - /tmp/.X11-unix:/tmp/.X11-unix:rw
          - ./_crud/testcreds/ca_default:/ca_default:ro
          - ./_crud/testcreds/verifier_asset:/verifier_asset:ro
          - ./_crud/testcreds/cred_healthhttpsclient:/cred_healthhttpsclient:ro
        environment:
          - DISPLAY=${DISPLAY}

    orchestrator:
        extends: common_nontpm
        hostname: orchestrator.""")
            fp.write(domain)
            fp.write("""
        volumes:
          - ./_crud/testcreds/cred_enrollclient:/cred_enrollclient:ro
""")
            for host in hosts:
                tpmmode = _input['fleet'][host]['tpm']
                if tpmmode != 'none' and tpmmode != 'unmanaged':
                    fp.write(f"          - tpm_{host}:/tpm_{host}\n")
            fp.write("""        environment:
          - HCP_CONFIG_MUTATE=/_usecase/orchestrator.json

""")
            docker_write_service(fp, 'attestsvc', _input['attestsvc'],
                                 with_sidecar = False, with_cotenant = False)
            for host in hosts:
                tpmmode = _input['fleet'][host]['tpm']
                docker_write_service(fp, host, _input['fleet'][host],
                                     with_sidecar = tpmmode == 'sidecar',
                                     with_cotenant = tpmmode == 'cotenant')
                if tpmmode == 'sidecar':
                    docker_write_sidecar(fp, host, _input['fleet'][host])
