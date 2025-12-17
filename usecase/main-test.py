#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import argparse
import json
import subprocess
import random
import string
import sys

os.environ['TOP'] = os.getcwd()
sys.path.append(os.getcwd())
from hcp.python.hcp.host.compose import Container, Composer


class TestFailure(Exception):
    pass

def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choices(characters, k=length))
    return random_string

if __name__ == '__main__':

    test_desc = 'Run the canonical test-case for newhcp'
    test_epilog = ''
    help_project = 'set the docker prefix used by compose'
    help_nonfs = 'disable the testing of kerberized NFS'
    help_nohost = 'disable the testing of host TPM'
    help_verbose = 'display more than just headings'
    help_quiet = 'don\'t even display headings'
    parser = argparse.ArgumentParser(description = test_desc,
                                     epilog = test_epilog)
    parser.add_argument('--project', metavar='<PREFIX>', help = help_project,
                        default = os.path.basename(os.getcwd()))
    parser.add_argument('--nonfs', action = 'store_true', help = help_nonfs)
    parser.add_argument('--nohost', action = 'store_true', help = help_nohost)
    parser.add_argument('--verbose', action = 'store_true', help = help_verbose)
    parser.add_argument('--quiet', action = 'store_true', help = help_quiet)

    args = parser.parse_args()

    def header(txt):
        # Eventually, do shell-fu to make the header pretty
        if not args.quiet:
            if args.verbose:
                print(f"\n#######\n## {txt}")
            else:
                print(txt)
    def bashscript(txt):
        if not args.quiet and args.verbose:
            print('----- start bash script input -----')
            print(txt)
            print('------ end bash script input ------')

    fleet = json.load(open('usecase/fleet.json'))
    DOMAIN = fleet['vars']['domain']

    composer = Composer(project = args.project,
                        verbose = args.verbose,
                        quiet = args.quiet)
    orchestrator = Container(composer, 'orchestrator')
    attestsvc = Container(composer, 'attestsvc')
    enrollsvc_tpm = Container(composer, 'enrollsvc_tpm')
    enrollsvc = Container(composer, 'enrollsvc')
    kdc_primary_tpm = Container(composer, 'kdc_primary_tpm')
    kdc_primary = Container(composer, 'kdc_primary')
    kdc_secondary_tpm = Container(composer, 'kdc_secondary_tpm')
    kdc_secondary = Container(composer, 'kdc_secondary')
    shell_tpm = Container(composer, 'shell_tpm')
    shell = Container(composer, 'shell')
    alicia = Container(composer, 'alicia')
    auth_certificate = Container(composer, 'auth_certificate')
    auth_kerberos = Container(composer, 'auth_kerberos')
    if not args.nonfs:
        nfs = Container(composer, 'nfs')
        barton = Container(composer, 'barton')
        catarina = Container(composer, 'catarina')
    if not args.nohost:
        hostside = Container(composer, 'hostside')

    header('Destroying any existing state')
    composer.down()

    header('Creating TPMs')
    orchestrator.run(['-a', '-c'])

    header('Starting core attestsvc service')
    attestsvc.up()

    header('Starting enrollsvc TPM')
    enrollsvc_tpm.up()

    header('Waiting for enrollsv TPM to advertise ek.pub')
    enrollsvc.run([
        '/hcp/python/hcp/tool/waitTouchfile.py',
        '/tpmsocket_enrollsvc/tpm.files/ek.pub' ])

    selfenrollbash = """
hash=$(openssl sha256 -r "/tpmsocket_enrollsvc/tpm.files/ek.pub")
path="/backend/db/${hash:0:2}/${hash:0:4}/${hash:0:64}"
if [[ ! -d "$path" ]]; then
    mkdir -p "$path"
    echo -n "${hash:0:64}" > "$path/ekpubhash"
    cp "/tpmsocket_enrollsvc/tpm.files/ek.pub" "$path/"
    cat "/usecase/fleet.json" \
        | jq .defaults.enroll_profile \
        | sed -e "s/{hostname}/enrollsvc.$DOMAIN/g" \
        > "$path/profile"
    chown -R www-data "/backend/db/${hash:0:2}"
fi
    """
    selfenrollbash = selfenrollbash.strip().replace('$DOMAIN', DOMAIN)
    header('Self-enrolling enrollsvc TPM')
    bashscript(selfenrollbash)
    enrollsvc.runT([ 'bash' ], input = selfenrollbash, text = True)

    header('Starting enrollsvc service')
    enrollsvc.up()

    header('Waiting for enrollsvc availability')
    orchestrator.run([
        '/hcp/python/hcp/tool/waitWeb.py',
        '--cacert', '/ca_default',
        '--clientcert', '/cred_enrollclient',
        '--retries', '10', '--pause', '1',
        f"https://enrollsvc.{DOMAIN}/healthcheck" ])

    header('Enrolling kdc TPMs')
    orchestrator.run(['-e', 'kdc_primary', 'kdc_secondary'])

    header('Starting KDCs')
    kdc_primary.up()
    kdc_secondary.up()
    kdc_primary_tpm.up()
    kdc_secondary_tpm.up()

    header('Waiting for kdc_secondary availability')
    attestsvc.exec([
        '/hcp/python/hcp/tool/waitWeb.py',
        '--cacert', '/ca_default',
        '--clientcert', '/cred_kdcclient',
        '--retries', '10', '--pause', '1',
        f"https://kdc_secondary.{DOMAIN}/healthcheck" ])

    header('Enrolling the remaining TPMs')
    orchestrator.run(['-e'])

    # Note, we have arbitrarily chosen 'alicia' and the two 'auth_*'
    # machines to use contenant TPMs (no sidecars)
    header('Starting remaining container workloads')
    shell.up()
    shell_tpm.up()
    alicia.up()
    auth_certificate.up()
    auth_kerberos.up()

    if not args.nonfs:
        header('Starting nfs (qemu/kvm virtual machine)')
        nfs.up()

    # By waiting for workload launch, we implicitly wait for attestation.
    header('Waiting for alicia to be attested')
    alicia.exec([
	'/hcp/python/hcp/tool/waitTouchfile.py',
        '/tmp/workload.running' ])
    header('Waiting for shell to be attested and sshd running')
    shell.exec([
	'/hcp/python/hcp/tool/waitTouchfile.py',
        '/tmp/workload.running' ])

    # The next little blob of script requires some explanation.
    # - we start a bash instance on 'alicia' and feed commands to it.
    #   - run 'kinit' using our PKINIT client cert to get a TGT. This is the
    #     "single sign-on" (SSO) event. (Or "zero sign-on" if you prefer, because
    #     the client cert is obtained non-interactively.)
    #     - kinit runs a subcommand and stays alive as long as the subcommand is
    #       running.
    #     - kinit will reauthenticate over time, as required to update the TGT,
    #       using newer client certs as they get updated by attestation.
    #     - the subcommand run by kinit is an ssh connection to 'shell';
    #       - the ssh-connection authenticates automatically using the TGT in
    #         kinit, hence SSO.
    #       - once authenticated, the ssh connection starts a bash shell on 'shell'
    #         and we feed commands to it.
    #         - Run 'hostname', the output will return through the ssh shell.
    # - pass the output through 'xargs' (a trick to strip whitespace)
    # - we confirm that all of the above generated "shell.$DOMAIN".
    sshbash = """
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	    ssh -l alicia shell.$DOMAIN bash <<DONE
hostname
DONE
    """
    sshbash = sshbash.strip().replace('$DOMAIN', DOMAIN)
    header('Running an SSO ssh session alicia -> shell')
    bashscript(sshbash)
    c = alicia.execT([ '/launcher', 'bash' ], input = sshbash,
                     stdout = subprocess.PIPE, text = True)
    output = c.stdout.strip()
    composer.log(True, f"Bash script output:\n{output}")
    if output != f"shell.{DOMAIN}":
        raise TestFailure()

    # This time, we ssh back to alicia from within the ssh session to shell
    sshbash = """
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
	ssh -l alicia shell.$DOMAIN bash <<DONE
ssh alicia.$DOMAIN bash <<INNER
hostname
INNER
DONE
    """
    sshbash = sshbash.strip().replace('$DOMAIN', DOMAIN)
    header('Running an SSO ssh boomerang alicia -> shell -> alicia')
    bashscript(sshbash)
    c = alicia.execT([ '/launcher', 'bash' ], input = sshbash,
                     stdout = subprocess.PIPE, text = True)
    output = c.stdout.strip()
    composer.log(True, f"Bash script output:\n{output}")
    if output != f"alicia.{DOMAIN}":
        raise TestFailure()

    header('Running a client-certificate authentication alicia -> auth_certificate')
    c = alicia.execT([
        'curl', '--silent',
        '--cacert', '/ca_default',
        '--cert', '/assets/https-client-alicia.pem',
        f"https://certificate.auth.{DOMAIN}/get" ],
        stdout = subprocess.PIPE, text = True)
    try:
        output = json.loads(c.stdout)
    except json.JSONDecodeError:
        composer.log(False, 'Result isn\'t valid JSON')
        raise TestFailure()
    composer.log(True, f"healthcheck response: {output}")
    if 'is_secure' not in output or output['is_secure'] != True:
        raise TestFailure()

    kerbbash = """
kinit -C FILE:/assets/pkinit-client-alicia.pem alicia \
    curl --silent --cacert /ca_default --negotiate -u : https://kerberos.auth.$DOMAIN/get \
    """
    kerbbash = kerbbash.strip().replace('$DOMAIN', DOMAIN)
    header('Running a kerberos-SPNEGO authentication alicia -> auth_kerberos')
    bashscript(kerbbash)
    c = alicia.execT([ '/launcher', 'bash' ], input = kerbbash,
                     stdout = subprocess.PIPE, text = True)
    composer.log(True, f"healthcheck response: {c.stdout.strip()}")
    try:
        output = json.loads(c.stdout)
    except json.JSONDecodeError:
        composer.log(False, 'Result isn\'t valid JSON')
        raise TestFailure()
    if 'is_secure' not in output or output['is_secure'] != True:
        raise TestFailure()

    if not args.nonfs:

        header('Waiting for nfs to be available')
        nfs.exec([
	    '/hcp/python/hcp/tool/waitTouchfile.py',
            '/tmp/vm.workload.running'])

        header('Starting barton (qemu/kvm virtual machine)')
        barton.up()

        header('Starting catarina (user-mode-linux virtual machine)')
        catarina.up()

        header('Waiting for barton to be available')
        barton.exec([
	    '/hcp/python/hcp/tool/waitTouchfile.py',
            '/tmp/vm.workload.running'])

        FOO = generate_random_string(60)
        writebash = """
ssh barton.$DOMAIN 'bash -c "echo $FOO > ~/dingdong"'
        """
        writebash = writebash.strip().replace('$DOMAIN', DOMAIN).replace('$FOO', FOO)
        header('Writing to NFS home directory from barton, via ssh from alicia')
        bashscript(writebash)
        alicia.execT([ 'su', '-w', 'HCP_CONFIG_MUTATE', '-', 'alicia' ],
                     input = writebash, stdout = subprocess.PIPE, text = True)

        header('Waiting for catarina to be available')
        catarina.exec([
	    '/hcp/python/hcp/tool/waitTouchfile.py',
            '/tmp/vm.workload.running'])

        readbash = """
ssh catarina.$DOMAIN 'bash -c "cat ~/dingdong"'
        """
        readbash = readbash.strip().replace('$DOMAIN', DOMAIN)
        header('Reading from NFS home directory from catarina, via ssh from alicia')
        bashscript(readbash)
        c = alicia.execT([ 'su', '-w', 'HCP_CONFIG_MUTATE', '-', 'alicia' ],
                         input = readbash, stdout = subprocess.PIPE, text = True)
        output = c.stdout.strip()
        composer.log(True, f"read result: {output}")
        if output != FOO:
            raise TestFailure()

    if not args.nohost:

        tpmbash = """
tpm2 createek -G rsa -u /ek.pub -c /dev/null
/hcp/python/hcp/api/enroll.py \
	--api https://enrollsvc.$DOMAIN \
	--cacert /ca_default \
	--clientcert /cred_enrollclient \
	add \
	--profile "{\\"hostname\\":\\"hostside.$DOMAIN\\",\\"days\\":1}" \
	/ek.pub
        """
        tpmbash = tpmbash.strip().replace('$DOMAIN', DOMAIN)
        header('Enrolling the host\'s TPM using \'hostside\'')
        bashscript(tpmbash)
        c = hostside.runT([ '/launcher', 'bash' ], input = tpmbash,
                          stdout = subprocess.PIPE, text = True)
        composer.log(True, f"enroll result: {c.stdout.strip()}")
        try:
            output = json.loads(c.stdout)
        except json.JSONDecodeError:
            composer.log(False, 'Result isn\'t valid JSON')
            raise TestFailure()
        if 'ekpubhash' not in output or len(output['ekpubhash']) != 64:
            raise TestFailure()
        header(f"Host TPM hash: {output['ekpubhash']}")

        header('Starting hostside')
        hostside.up()

        header('Waiting for hostside to be available')
        hostside.exec([
	    '/hcp/python/hcp/tool/waitTouchfile.py',
            '/tmp/workload.running' ])

    header('Success')
