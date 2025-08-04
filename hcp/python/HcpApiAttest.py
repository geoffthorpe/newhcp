#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import json
import requests
import os
import sys
import argparse
import time
import subprocess
import tempfile
import shutil
import filecmp

loglevel = 0
def set_loglevel(v):
    global loglevel
    loglevel = v

def _log(level, s):
    if level <= loglevel:
        print(f"{s}", file = sys.stderr)
def err(s):
    _log(0, s)
def log(s):
    _log(1, s)
def debug(s):
    _log(2, s)

auth = None
if os.environ.get('HCP_GSSAPI'):
    log('Enabling GSSAPI authentication')
    try:
        from requests_gssapi import HTTPSPNEGOAuth, DISABLED
        auth = HTTPSPNEGOAuth(mutual_authentication=DISABLED, opportunistic_auth=True)
    except ModuleNotFoundError:
        log("'requests-gssapi' unavailable, falling back to 'requests-kerberos'")
        try:
            from requests_kerberos import HTTPKerberosAuth, DISABLED
            auth = HTTPKerberosAuth(mutual_authentication=DISABLED, force_preemptive=True)
        except ModuleNotFoundError:
            log("'requests-kerberos' unavailable, falling back to no authentication")

def sr(cmd):
    debug('subprocess.run: ' + ' '.join(cmd))
    c = subprocess.run(cmd, stdout = subprocess.PIPE if loglevel < 2 else None)
    if c.returncode != 0:
        err('Error: ' + ' '.join(cmd))
        return False
    return True

def tpm2_flushall():
    return sr(['tpm2', 'flushcontext', '--transient-object']) and \
           sr(['tpm2', 'flushcontext', '--loaded-session']) and \
           sr(['tpm2', 'flushcontext', '--saved-session'])

def tpm2_secret_session(_dir):
    return tpm2_flushall() and \
           sr(['tpm2', 'startauthsession',
               '--session', f"{_dir}/session.ctx",
               '--policy-session']) and \
           sr(['tpm2', 'policysecret',
               '--session', f"{_dir}/session.ctx",
               '--object-context', 'endorsement'])

# TODO: this code was copied from HcpApiEnroll.py and suffers from the same
# akwardnesses. What's said there applies here.

def requester_loop(request_fn, retries = 0, pause = 0):
    debug(f"requester_loop: retries={retries}, pause={pause}")
    retries = retries
    while True:
        try:
            debug("requester_loop: calling request_fn()")
            response = request_fn()
        except Exception as e:
            if retries > 0:
                debug(f"requester_loop: caught exception, retries={retries}")
                debug(f" - e: {e}")
                retries -= 1
                time.sleep(pause)
                continue
            debug(f"requester_loop: caught exception, no retries")
            debug(f" - e: {e}")
            raise e
        debug("requester_loop: returning")
        return response

# Handler functions for the subcommands (initiate, quote)
# They all return a 2-tuple of {result,json}, where result is True iff the
# operation was successful.

def attest_initiate(api, output, requests_verify = True, requests_cert = False,
                    retries = 0, timeout = 120):
    with tempfile.TemporaryDirectory() as tempdir:
        if not tpm2_flushall() or \
            not sr(['tpm2', 'createek',
                   '--ek-context', f"{tempdir}/ek.ctx",
                   '--key-algorithm', 'rsa',
                   '--public', f"{tempdir}/ek.pub"]):
            return False
        c = subprocess.run(['openssl', 'sha256', '-r', f"{tempdir}/ek.pub"],
                           capture_output = True, text = True)
        if c.returncode != 0:
            return False
    form_data = {
        'ekpubhash': (None, c.stdout[0:64])
    }
    debug("'initiate' handler about to call API")
    debug(f" - url: {api + '/v1/initiate'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/initiate',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        err(f"Error, 'initiate' response status code was {response.status_code}")
        return False
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'initiate' response failed: {e}")
        return False
    debug(f" - jr: {jr}")
    with open(output, 'w') as fp:
        fp.write(json.dumps(jr))
    return True

def attest_quote(initial, output):
    with open(initial, 'r') as fp:
        initjson = fp.read()
    init = json.loads(initjson)
    with tempfile.TemporaryDirectory() as tempdir:
        with open(f"{tempdir}/nonce", 'w') as fp:
            fp.write(init['nonce'].strip())
        if tpm2_flushall() and \
            sr(['tpm2', 'createek',
                '--ek-context', f"{tempdir}/ek.ctx",
                '--key-algorithm', 'rsa',
                '--public', f"{tempdir}/ek.pub"]) and \
            tpm2_secret_session(tempdir) and \
            sr(['tpm2', 'create',
                '--parent-context', f"{tempdir}/ek.ctx",
                '--parent-auth', f"session:{tempdir}/session.ctx",
                '--key-algorithm', 'ecc:ecdsa:null',
                '--attributes', 'fixedtpm|fixedparent|sensitivedataorigin|userwithauth|restricted|sign|stclear',
                '--public', f"{tempdir}/ak-pub.key",
                '--private', f"{tempdir}/ak-priv.key"]) and \
            tpm2_secret_session(tempdir) and \
            sr(['tpm2', 'load',
                '--parent-context', f"{tempdir}/ek.ctx",
                '--auth', f"session:{tempdir}/session.ctx",
                '--key-context', f"{tempdir}/ak.ctx",
                '--public', f"{tempdir}/ak-pub.key",
                '--private', f"{tempdir}/ak-priv.key"]) and \
            sr(['tpm2', 'readpublic',
                '--object-context', f"{tempdir}/ak.ctx",
                '--output', f"{tempdir}/ak.pub",
                '--format', 'tpmt']) and \
            tpm2_flushall() and \
            sr(['tpm2', 'quote',
                '--key-context', f"{tempdir}/ak.ctx",
                '--pcr-list', f"sha256:{init['PCRs']}",
                '--qualification', f"{tempdir}/nonce",
                '--message', f"{tempdir}/quote.out",
                '--signature', f"{tempdir}/quote.sig",
                '--pcr', f"{tempdir}/quote.pcr"]) and \
            sr(['tar', '-zcf', output,
                '-C', tempdir,
                'ek.pub', 'ak.pub', 'ak.ctx',
                'quote.out', 'quote.sig', 'quote.pcr']):
            return True
    return False

def attest_complete(api, initial, quote, output, requests_verify = True,
                    requests_cert = False, retries = 0, timeout = 120):
    form_data = {
        'initial': ('initial', open(initial, 'r')),
        'quote': ('quote', open(quote, 'rb'))
    }
    debug("'complete' handler about to call API")
    debug(f" - url: {api + '/v1/complete'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/complete',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    if response.status_code != 200:
        err(f"Error, 'complete' response status code was {response.status_code}")
        return False
    with open(output, 'wb') as fp:
        fp.write(response.content)
    return True

def attest_unseal(bundle, output, callback = None):
    if not os.path.isfile(f"{bundle}"):
        err(f"Error, no bundle at path '{bundle}'")
        return False
    if not os.path.isdir(f"{output}"):
        err(f"Error, no output path '{output}'")
        return False
    with tempfile.TemporaryDirectory() as tempdir:
        if not sr(['tar', '-zxf', bundle,
                   '-C', tempdir]):
            err("Error, failed to extract bundle")
            return False
        if not os.path.isfile(f"{tempdir}/manifest/data"):
            err("Error, bundle has no manifest")
            return False
        if not sr(['/hcp/safeboot/api_unseal',
                   '-s',
                   '/enrollverifier/key.pem',
                   f"{tempdir}/manifest",
                   f"{output}/manifest"]):
            err("Error, failed to verify the manifest")
            return False
        with open(f"{output}/manifest", 'r') as fp:
            manifest = json.loads(fp.read())
        log(f"Unsealed manifest: {manifest}")
        for _tuple in manifest:
            d = _tuple[0]
            p = _tuple[1]
            _makedir = os.path.dirname(f"{output}/{d}")
            if not os.path.isdir(_makedir):
                os.makedirs(_makedir)
            if not p:
                # The asset has to be decrypted first
                if not os.path.isfile(f"{tempdir}/{d}/symkeyenc"):
                    err(f"Error, encrypted asset incomplete ({d})")
                    return False
                if not sr(['/hcp/safeboot/api_unseal',
                           '/enrollverifier/key.pem',
                           f"{tempdir}/{d}",
                           f"{output}/{d}.tmp"]):
                    return False
            else:
                if not sr(['/hcp/safeboot/api_unseal', '-s',
                           '/enrollverifier/key.pem',
                           f"{tempdir}/{d}",
                           f"{output}/{d}.tmp"]):
                    return False
            if callback:
                if not os.path.isfile(f"{output}/{d}") or \
                    not filecmp.cmp(f"{output}/{d}", f"{output}/{d}.tmp",
                                    shallow = False):
                    c = subprocess.run([callback, d], cwd = output)
                    if c.returncode != 0:
                        err(f"Error, callback failed ({d})")
                        return False
            shutil.move(f"{output}/{d}.tmp", f"{output}/{d}")
            log(f"Unsealed asset: {d}")
    return True

if __name__ == '__main__':

    # Wrapper 'attest' command, using argparse

    attest_desc = 'API client for Attestation Service interface'
    attest_epilog = """
    If the URL for the Attestation Service's API is not supplied on the command
    line (via '--api'), it will fallback to using the 'ATTESTSVC_API_URL'
    environment variable. If the API is using HTTPS and the server certificate is
    not signed by a CA that is already trusted by the system, '--cacert' should
    be used to specify a CA certificate (or bundle) that should be considered
    trusted. (Otherwise, specify '--noverify' to inhibit certificate validation.)
    To use a client certificate to authenticate to the server, specify
    '--clientcert'. If that file doesn't include the private key, specify it with
    '--clientkey'.

    To see subcommand-specific help, pass '-h' to the subcommand.
    """
    attest_help_api = 'base URL for management interface'
    attest_help_cacert = 'path to CA cert (or bundle) for validating server certificate'
    attest_help_noverify = 'disable validation of server certificate'
    attest_help_verbosity = 'verbosity level, 0 means quiet, more than 0 means less quiet'
    attest_help_clientcert = 'path to client cert to authenticate with'
    attest_help_clientkey = 'path to client key (if not included with --clientcert)'
    attest_help_retries = 'max number of API retries'
    attest_help_pause = 'number of seconds between retries'
    attest_help_timeout = 'number of seconds to allow before giving up'
    parser = argparse.ArgumentParser(description=attest_desc,
                                     epilog=attest_epilog)
    parser.add_argument('--api', metavar='<URL>',
                        default=os.environ.get('ATTESTSVC_API_URL'),
                        help=attest_help_api)
    parser.add_argument('--cacert', metavar='<PATH>',
                        default=os.environ.get('ATTESTSVC_API_CACERT'),
                        help=attest_help_cacert)
    parser.add_argument('--noverify', action='store_true',
                        help=attest_help_noverify)
    parser.add_argument('--clientcert', metavar='<PATH>',
                        default=os.environ.get('ATTESTSVC_API_CLIENTCERT'),
                        help=attest_help_clientcert)
    parser.add_argument('--clientkey', metavar='<PATH>',
                        default=os.environ.get('ATTESTSVC_API_CLIENTKEY'),
                        help=attest_help_clientkey)
    parser.add_argument('--verbosity', type=int, metavar='<level>',
                        default=0, help=attest_help_verbosity)
    parser.add_argument('--retries', type=int, metavar='<num>',
                        default=0, help=attest_help_retries)
    parser.add_argument('--pause', type=int, metavar='<secs>',
                        default=0, help=attest_help_pause)
    parser.add_argument('--timeout', type=int, metavar='<secs>',
                        default=600, help=attest_help_timeout)

    subparsers = parser.add_subparsers()

    # Subcommand details

    initiate_help = 'Initiate an attestation exchange'
    initiate_epilog = """
    The 'initiate' subcommand invokes the '/v1/initiate' handler of the Attestation
    Service's API. The response will contain the nonce and PCR settings required to
    produce a quote and complete the attestation. This should be saved to a file
    and used as the <initial> parameter to the 'quote' and 'attest' commands.
    """
    initiate_help_output = 'path for the resulting \'initial\' file'
    parser_a = subparsers.add_parser('initiate', help=initiate_help, epilog=initiate_epilog)
    parser_a.add_argument('output', help=initiate_help_output)
    parser_a.set_defaults(func='initiate')

    quote_help = 'Generate a TPM quote'
    quote_epilog = """
    The 'quote' subcommand interacts with the host's TPM to produce a quote file for
    use in attestation.
    """
    quote_help_initial = 'path to attestation context, as returned from \'initiate\''
    quote_help_output = 'path for the resulting quote file'
    parser_a = subparsers.add_parser('quote', help=quote_help, epilog=quote_epilog)
    parser_a.add_argument('initial', help=quote_help_initial)
    parser_a.add_argument('output', help=quote_help_output)
    parser_a.set_defaults(func='quote')

    complete_help = 'Complete an attestation exchange'
    complete_epilog = """
    The 'complete' subcommand invokes the '/v1/complete' handler of the Attestation
    Service's API. This sends a quote file (as generated by the 'quote' subcommand)
    and, if successful, obtains a TPM-sealed asset bundle (a gzip'd tarball).
    """
    complete_help_initial = 'path to attestation context, as returned from \'initiate\''
    complete_help_quote = 'path to quote, as returned from \'quote\''
    complete_help_output = 'path for the returned asset bundle'
    parser_a = subparsers.add_parser('complete', help=complete_help, epilog=complete_epilog)
    parser_a.add_argument('initial', help=complete_help_initial)
    parser_a.add_argument('quote', help=complete_help_quote)
    parser_a.add_argument('output', help=complete_help_output)
    parser_a.set_defaults(func='complete')

    unseal_help = 'Unseal an attestation-returned asset bundle'
    unseal_epilog = """
    The 'unseal' subcommand interacts with the host's TPM to unseal an asset bundle
    that was returned from the Attestation Service. If '--callback' is used to set
    an update callback, it will be invoked each and every time an asset is unbundled
    and is not replacing an identical existing asset. This hook can be used to
    restart or HUP services that need to re-read asset inputs.
    """
    unseal_help_callback = 'callback to invoke on assets that change'
    unseal_help_verifier = 'path to public key for signature-verification'
    unseal_help_bundle = 'path prefix for asset files'
    unseal_help_output = 'prefix for the resulting output files'
    parser_a = subparsers.add_parser('unseal', help=unseal_help, epilog=unseal_epilog)
    parser_a.add_argument('--callback', metavar='<PATH>',
                        default=None, help=unseal_help_callback)
    parser_a.add_argument('verifier', help=unseal_help_verifier)
    parser_a.add_argument('bundle', help=unseal_help_bundle)
    parser_a.add_argument('output', help=unseal_help_output)
    parser_a.set_defaults(func='unseal')

    # Process the command-line
    args = parser.parse_args()
    set_loglevel(args.verbosity)
    log(f"verbosity={args.verbosity}")
    if not args.api:
        err("Error, no API URL was provided.")
        sys.exit(-1)
    requests_verify = True
    if args.noverify:
        requests_verify = False
    elif args.cacert:
        requests_verify = args.cacert
    requests_cert = False
    if args.clientcert:
        if args.clientkey:
            requests_cert = (args.clientcert,args.clientkey)
        else:
            requests_cert = args.clientcert

    # Dispatch. Here, we are operating as a program with a parent process, not a library with
    # a caller. If we don't catch exceptions, they get handled by the runtime which will print
    # stack traces to stderr and exit, there is no concept of the exceptions reaching the
    # parent process. As such, catch them all here.
    try:
        if args.func == 'initiate':
            result = attest_initiate(args.api, args.output,
                                     requests_verify = requests_verify,
                                     requests_cert = requests_cert,
                                     timeout = args.timeout)
        elif args.func == 'quote':
            result = attest_quote(args.initial, args.output)
        elif args.func == 'complete':
            result = attest_complete(args.api, args.initial,
                                     args.quote, args.output,
                                     requests_verify = requests_verify,
                                     requests_cert = requests_cert,
                                     timeout = args.timeout)
        elif args.func == 'unseal':
            result = attest_unseal(args.bundle, args.output, args.callback)
        else:
            raise Exception("BUG")
    except Exception as e:
        print(f"Error, unable to perform '{args.func}' function", file = sys.stderr)
        print(f"Exception: {e}", file = sys.stderr)
        sys.exit(-1)
    log(f"handler returned: result={result}")
    if not result:
        sys.exit(-1)
