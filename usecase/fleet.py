#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import json
import os
import sys
import argparse

from gson.expander import expand

def docker_write_service(fp, name, data, with_tpm = True):
    print(f"Writing service '{name}' to docker compose file")
    fp.write(f"    {name}:\n")
    fp.write('        extends: common_nontpm\n')
    fp.write(f"        hostname: {data['hostname']}\n")
    fp.write('        volumes:\n')
    if with_tpm:
        fp.write(f"          - tpmsocket_{name}:/tpmsocket_{name}\n")
    vols = data['volumes'] if 'volumes' in data else []
    for item in vols:
        fp.write(f"          - {item}\n")
    fp.write('        environment:\n')
    fp.write(f"          - HCP_CONFIG_FILE=/_usecase/{name}.json\n\n")

def docker_write_tpm(fp, name, data, with_tpm = True):
    print(f"Writing service '{name}_tpm' to docker compose file")
    fp.write(f"    {name}_tpm:\n")
    fp.write('        extends: common_tpm\n')
    fp.write(f"        hostname: tpm.{data['hostname']}\n")
    fp.write('        volumes:\n')
    if with_tpm:
        fp.write(f"          - tpm_{name}:/tpm_{name}\n")
        fp.write(f"          - tpmsocket_{name}:/tpmsocket_{name}\n")
    fp.write('        environment:\n')
    fp.write(f"          - HCP_CONFIG_FILE=/_usecase/{name}.json\n\n")

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
    if 'attestsvc' in hosts:
        raise Exception("'attestsvc' is not a valid fleet host id")
    if 'orchestrator' in hosts:
        raise Exception("'orchestrator' is not a valid fleet host id")
    if 'vars' not in _input or 'domain' not in _input['vars']:
        raise Exception("No 'domain'")
    domain = _input['vars']['domain']

    if args.show:
        print(' '.join(hosts + [ 'orchestrator', 'attestsvc' ]))

    elif args.host:
        if not os.path.isdir(args.hosts):
            raise Exception(f"Host config output directory ({args.hosts}) is not a directory")
        host = args.host
        # Produce {host}.json output
        if host != 'attestsvc' and host != 'orchestrator' and \
                                host not in hosts:
            raise Exception(f"'{host}' is not a known fleet host id")
        print(f"Producing '{host}' config file")
        if host in hosts:
            data = _input['fleet'][host]
        else: # host == attestsvc or host == orchestrator
            data = _input[host]
        hostname = data['hostname'] if 'hostname' in data else 'nada'
        servicenames = [ k for k in data['services']] \
            if 'services' in data else []
        if 'tpm' in servicenames:
            servicenames.pop(servicenames.index('tpm'))
        if 'xtra_services' in data:
            servicenames += data['xtra_services']
        # 'output' is the structure that gets jsonified at the end
        output = {
            'vars': {
                'id': host,
                'hostname': hostname
            },
            'mutate': [
                { 'method': 'load', 'jspath': '/usecase/proto/root.json' },
                { 'method': 'union' }
            ],
            'services': servicenames,
            'default_targets': [ 'setup-global', 'setup-local',
                                 'start-services', 'start-tool' ]
        }
        if 'attester' in data['services']:
            output['default_targets'] = [ 'start-attester' ] + output['default_targets']
        if 'vars' in _input:
            for k in _input['vars']:
                if k not in output['vars']:
                    output['vars'][k] = _input['vars'][k]
        # add a root prototype (merged into the top-level, rather than into
        # a named sub-object) if requested.
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
        # load and merge prototype defaults
        output['mutate'].append({
            'method': 'load',
            'register': 'd',
            'jspath': '/usecase/proto/defaults.json'})
        output['mutate'].append({
            'method': 'union',
            'regpath': 'vars',
            'srcregister': 'd',
            'underlay': True})
        # add per-service mutations
        services = data['services'] if 'services' in data else {}
        for service in services:
            _vars = services[service]
            # Merge any variables into the 'vars' sub-object
            if _vars:
                for k in _vars:
                    output['vars'][f"{service}_{k}"] = _vars[k]
            # Add the non-root prototype
            proto = f"/usecase/proto/{service}_sidecar.json" \
                if service == 'tpm' else f"/usecase/proto/{service}.json"
            output['mutate'].append({
                'method': 'load',
                'regpath': service,
                'jspath': proto})
        # add per-host environment includes
        env = data['env'] if 'env' in data else []
        for e in env:
            output['mutate'].append({
                'method': 'load',
                'register': 'e',
                'jspath': f"/usecase/proto/env_{e}.json"})
            output['mutate'].append({
                'method': 'union',
                'srcregister': 'e',
                'regpath': 'env'})
        # if there's an "args_for", put it in the output
        if 'args_for' in data:
            output['args_for'] = data['args_for']
        # perform parameter-expansion
        output['mutate'].append({ 'method': 'expand' })
        # Generate host config (and make it human-readable)
        with open(f"{args.hosts}/{host}.json", 'w') as fp:
            json.dump(output, fp, indent = 4)

    else:

        # Produce docker-compose.yml
        with open(args.docker, 'w') as fp:
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
        hostname: orchestrator.""")
            fp.write(domain)
            fp.write("""
        volumes:
          - ./_testcreds/cred_enrollclient:/cred_enrollclient:ro
""")
            for host in hosts:
                fp.write(f"          - tpm_{host}:/tpm_{host}\n")
            fp.write("""        environment:
          - HCP_CONFIG_FILE=/_usecase/orchestrator.json

""")
            docker_write_service(fp, 'attestsvc', _input['attestsvc'],
                                 with_tpm = False)
            for host in hosts:
                docker_write_service(fp, host, _input['fleet'][host])
                docker_write_tpm(fp, host, _input['fleet'][host])
