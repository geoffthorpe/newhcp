#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import sys
import json
import subprocess
import time
import tempfile
import shutil
import argparse

from HcpCommon import bail, log, hlog, \
    hcp_config_extract, hcp_config_scope_get, hcp_config_scope_set, \
    hcp_config_scope_shrink
from HcpRecursiveUnion import union
import HcpApiEnroll
from HcpJsonExpander import _load as expandload

fleetconfpath = hcp_config_extract('.orchestrator.fleet', must_exist = True)
if not os.path.isfile(fleetconfpath):
    bail(f"No config at '{fleetconfpath}'")
with open(fleetconfpath, 'r') as fp:
    fleetconf = json.loads(fp.read())
fleetdefaults = fleetconf.pop('defaults') if 'defaults' in fleetconf else {}
fleet = fleetconf.pop('fleet') if 'fleet' in fleetconf else {}
fleethosts = [ name for name in fleet if name != '_']

class FleetHost:
    def post_exist(self):
        c = subprocess.run(['openssl', 'sha256', '-r', self.ekpub],
                           capture_output = True, text = True)
        if c.returncode != 0:
            raise Exception("Failed to hash ekpub")
        self.ekpubhash = c.stdout[0:64]
        retcode, result = HcpApiEnroll.enroll_query(self.api,
                                                    self.ekpubhash,
                                                    True,
                                                    requests_verify = self.api_cacert,
                                                    requests_cert = self.api_clientcert)
        if not retcode or 'entries' not in result:
            raise Exception("Failed to query enrollsvc")
        self.enrolled = len(result['entries']) > 0
    def __init__(self, name):
        if name == 'defaults':
            raise Exception("'defaults' is an illegal fleet host name")
        if name not in fleet:
            raise Exception(f"Unknown fleet host '{name}'")
        self.name = name
        self.profile = expandload(union(fleetdefaults, fleet[name]))
        self.api = self.profile['enroll_api']
        self.api_cacert = self.profile['enroll_api_cacert']
        self.api_clientcert = self.profile['enroll_api_clientcert'] \
            if 'enroll_api_clientcert' in self.profile else False
        self.tpm_create = self.profile['tpm_create']
        self.tpm_enroll = self.profile['tpm_enroll']
        self.tpm_path = self.profile['tpm_path']
        self.enroll_profile = self.profile['enroll_profile']
        self.ekpub = f"{self.tpm_path}/tpm/ek.pub"
        self.exists = os.path.isfile(self.ekpub)
        self.enrolled = False
        if self.exists:
            self.post_exist()
    def create(self):
        if self.exists:
            print(f"{self.name}: TPM already exists")
            return
        os.makedirs(f"{self.tpm_path}/tpm-temp", exist_ok = True)
        c = subprocess.run(['swtpm_setup', '--tpm2',
                            '--createek',
                            '--tpmstate', f"{self.tpm_path}/tpm-temp",
                            '--config', '/dev/null'],
                           capture_output = True)
        if c.returncode != 0:
            print(f"Error, swtpm_setup failed for '{self.name}'")
            return
        with tempfile.TemporaryDirectory() as sockdir:
            p = subprocess.Popen(['swtpm', 'socket', '--tpm2',
                                  '--tpmstate', f"dir={self.tpm_path}/tpm-temp",
                                  '--server', f"type=unixio,path={sockdir}/tpm",
                                  '--ctrl', f"type=unixio,path={sockdir}/tpm.ctrl",
                                  '--flags', 'startup-clear'],
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE)
            if p.poll() != None:
                print(f"Error, swtpm temp-start failed for '{self.name}'")
                return
            newenv = os.environ.copy()
            newenv['TPM2TOOLS_TCTI'] = f"swtpm:path={sockdir}/tpm"
            c = subprocess.run(['tpm2', 'createek',
                                f"--ek-context={self.tpm_path}/tpm-temp/ek.ctx",
                                f"--public={self.tpm_path}/tpm-temp/ek.pub",
                                '--key-algorithm=rsa'],
                               env = newenv,
                               capture_output = True)
            p.kill()
            if c.returncode != 0:
                print(f"Error, swtpm createek failed for '{self.name}'")
                return
        c = subprocess.run(['tpm2', 'print',
                            '-t', 'TPM2B_PUBLIC',
                            '-f', 'PEM',
                            f"{self.tpm_path}/tpm-temp/ek.pub"],
                           capture_output = True)
        if c.returncode != 0:
            print(f"Error, conversion TPM2B_PUBLIC to PEM failed for '{self.name}'")
            return
        shutil.move(f"{self.tpm_path}/tpm-temp",
                    f"{self.tpm_path}/tpm")
        self.exists = True
        self.post_exist()
        print(f"{self.name}: TPM created")
    def delete(self):
        if not self.exists:
            print(f"{self.name}: TPM doesn't exist")
            return
        shutil.rmtree(f"{self.tpm_path}/tpm")
        self.exists = False
        print(f"{self.name}: TPM deleted")
    def enroll(self):
        if not self.exists:
            print(f"{self.name}: TPM doesn't exist")
            return
        if self.enrolled:
            print(f"{self.name}: TPM already enrolled")
            return
        retcode, result = HcpApiEnroll.enroll_add(self.api,
                                                  self.ekpub,
                                                  profile = json.dumps(self.enroll_profile),
                                                  requests_verify  = self.api_cacert,
                                                  requests_cert = self.api_clientcert)
        if not retcode:
            raise Exception("Failed to get enrollsvc response")
        if 'ekpubhash' not in result:
            print(f"Error, TPM enrollment not processed for '{self.name}'")
            return
        print(f"{self.name}: TPM enrolled")
        self.enrolled = True
    def unenroll(self):
        if not self.exists:
            print(f"{self.name}: TPM doesn't exist")
            return
        if not self.enrolled:
            print(f"{self.name}: TPM isn't enrolled")
        retcode, result = HcpApiEnroll.enroll_delete(self.api,
                                                     self.ekpubhash,
                                                     True,
                                                     requests_verify = self.api_cacert,
                                                     requests_cert = self.api_clientcert)
        if not retcode or 'entries' not in result:
            raise Exception("Failed to get enrollsvc response")
        if len(result['entries']) == 0:
            print(f"Error, TPM unenrollment not processed for '{self.name}'")
            return
        print(f"{self.name}: TPM unenrolled")
        self.enrolled = False
    def status(self):
        if self.exists:
            if self.enrolled:
                status = 'exists, enrolled'
            else:
                status = 'exists, not enrolled'
        else:
            status = 'non-existant'
        print(f"{self.name}: TPM {status}")

if __name__ == '__main__':

    # Wrapper command, using argparse
    _desc = 'Orchestrator tool for Enroll Service and SWTPM management'
    _epilog = """
    Using the fleet.json config file, this tool can manage swtpm instances
    and perform enroll/unenroll actions against the Enrollment Service
    management interface.
    """
    _help_create = 'The host\'s TPM will be created if it doesn\'t exist'
    _help_delete = 'The host\'s TPM will be deleted if it exists'
    _help_enroll = 'The host will be enrolled if it\'s not already'
    _help_unenroll = 'The host will be unenrolled if it\'s enrolled'
    _help_verbosity = 'Verbosity level, 0 means quiet, more than 0 means less quiet'
    _help_hostnames = 'Names matching stanzas found in fleet.json'
    parser = argparse.ArgumentParser(description = _desc,
                                     epilog = _epilog)
    parser.add_argument('-c', '--create', action='store_true', help = _help_create)
    parser.add_argument('-d', '--delete', action='store_true', help = _help_delete)
    parser.add_argument('-e', '--enroll', action='store_true', help = _help_enroll)
    parser.add_argument('-u', '--unenroll', action='store_true', help = _help_unenroll)
    parser.add_argument('-v', '--verbosity', help = _help_verbosity)
    parser.add_argument('hostnames', nargs='*', help = _help_hostnames)

    args = parser.parse_args()
    if args.verbosity:
        HcpApiEnroll.set_loglevel(int(args.verbosity))
    if args.create and args.delete:
        raise Exception("Cannot create and delete in the same command")
    if args.enroll and args.unenroll:
        raise Exception("Cannot enroll and unenroll in the same command")
    if len(args.hostnames) == 0:
        args.hostnames = fleethosts
    for host in args.hostnames:
        fh = FleetHost(host)
        if args.create:
            fh.create()
        if args.delete:
            fh.delete()
        if args.enroll:
            fh.enroll()
        if args.unenroll:
            fh.unenroll()
        if not args.create and not args.delete and not args.enroll and not args.unenroll:
            fh.status()
