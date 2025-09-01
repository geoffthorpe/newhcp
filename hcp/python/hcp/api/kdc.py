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

# This internal function is used as a wrapper to deal with exceptions and
# retries. 'args' specifies whether retries' should be attempted and how many
# times, how long to pause between those retries, etc. 'request_fn' is a
# caller-supplied callback (eg. lambda) function that performs the desired
# operation and (if no exception occurs) returns the desired result.  This
# caller-supplied function typically calls requests.get() or requests.post()
# with whatever inputs are desired and passes back the return value from that.
# Note, the retries are only considered in the case that an exception was
# thrown in the 'request_fn'. If 'request_fn' returns without exception, we
# pass along whatever it returned rather than retrying. (If the response
# contains a non-2xx http status code, that's not our business.)
def requester_loop(request_fn, retries = 0, pause = 0):
    debug(f"requester_loop: retries={retries}, pause={pause}")
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

# Handler functions for the subcommands
# They all return a 2-tuple of {result,json}, where result is True iff the
# operation was successful.

def kdc_add(api, principals, profile = None, requests_verify = True,
            requests_cert = False, retries = 0, timeout = 120):
    form_data = { 'principals': (None, json.dumps(principals)) }
    if profile is not None:
        form_data['profile'] = (None, profile)
    debug("'add' handler about to call API")
    debug(f" - url: {api + '/v1/add'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/add',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        err(f"Error, 'add' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'add' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def kdc_add_ns(api, principals, profile = None, requests_verify = True,
               requests_cert = False, retries = 0, timeout = 120):
    form_data = { 'principals': (None, json.dumps(principals)) }
    if profile is not None:
        form_data['profile'] = (None, profile)
    debug("'add_ns' handler about to call API")
    debug(f" - url: {api + '/v1/add_ns'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/add_ns',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        err(f"Error, 'add_ns' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'add_ns' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def kdc_get(api, principals, profile = None, requests_verify = True,
            requests_cert = False, retries = 0, timeout = 120):
    form_data = { 'principals': (None, json.dumps(principals)) }
    if profile is not None:
        form_data['profile'] = (None, profile)
    debug("'get' handler about to call API")
    debug(f" - url: {api + '/v1/get'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.get(api + '/v1/get',
                                     params = form_data,
                                     auth = auth,
                                     verify = requests_verify,
                                     cert = requests_cert,
                                     timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        err(f"Error, response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        log(f"Error, JSON decoding of response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def kdc_del(api, principals, profile = None, requests_verify = True,
            requests_cert = False, retries = 0, timeout = 120):
    form_data = { 'principals': (None, json.dumps(principals)) }
    if profile is not None:
        form_data['profile'] = (None, profile)
    debug("'del' handler about to call API")
    debug(f" - url: {api + '/v1/del'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/del',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        err(f"Error, 'del' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'del' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def kdc_del_ns(api, principals, profile = None, requests_verify = True,
               requests_cert = False, retries = 0, timeout = 120):
    form_data = { 'principals': (None, json.dumps(principals)) }
    if profile is not None:
        form_data['profile'] = (None, profile)
    debug("'add' handler about to call API")
    debug(f" - url: {api + '/v1/del_ns'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/del_ns',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        err(f"Error, 'del_ns' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'del_ns' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def kdc_ext_keytab(api, principals, kerberos, raw, profile = None,
                   requests_verify = True, requests_cert = False,
                   retries = 0, timeout = 120):
    if kerberos:
        # Special handling. python-requests-kerberos' seems to be broken on
        # debian, so we use "curl --negotiate" instead.
        myrequest = lambda: subprocess.run([
                'curl', '-F', 'principals="[]"',
                '--cacert', requests_verify,
                '--negotiate', '-u', ':',
                api + '/v1/ext_keytab' ],
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE)
        response = requester_loop(myrequest, retries = retries)
        if response.returncode != 0:
            err(f"Error, 'ext_keytab' curl exit code was {response.returncode}")
            return False, None
        myoutput = response.stdout
    else:
        form_data = { 'principals': (None, json.dumps(principals)) }
        if profile is not None:
            form_data['profile'] = (None, profile)
        debug("'add' handler about to call API")
        debug(f" - url: {api + '/v1/ext_keytab'}")
        debug(f" - files: {form_data}")
        myrequest = lambda: requests.post(api + '/v1/ext_keytab',
                                          files = form_data,
                                          auth = auth,
                                          verify = requests_verify,
                                          cert = requests_cert,
                                          timeout = timeout)
        response = requester_loop(myrequest, retries = retries)
        debug(f" - response: {response}")
        debug(f" - response.content: {response.content}")
        if response.status_code != 200:
            err(f"Error, 'ext_keytab' response status code was {response.status_code}")
            return False, None
        myoutput = response.content
    try:
        jr = json.loads(myoutput)
    except Exception as e:
        err(f"Error, JSON decoding of 'ext_keytab' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    # Special case
    if raw:
        with tempfile.TemporaryDirectory() as tempdir:
            with open(f"{tempdir}/b64", 'w') as fp:
                fp.write(jr['stdout'])
            c = subprocess.run(['base64', '-d', f"{tempdir}/b64"],
                               capture_output = True, text = False)
            if c.returncode != 0:
                err('Error, could not base64 decode the keytab')
                return False, None
            with open(raw, 'wb') as fp:
                fp.write(c.stdout)
    return True, jr


if __name__ == '__main__':

    # Wrapper 'kdc' command, using argparse

    kdc_desc = 'API client for KDC Service management interface'
    kdc_epilog = """
    If the URL for the KDC Service's management API is not supplied on the
    command line (via '--api'), it will fallback to using the 'KDCSVC_API_URL'
    environment variable. If the API is using HTTPS and the server certificate is
    not signed by a CA that is already trusted by the system, '--cacert' should
    be used to specify a CA certificate (or bundle) that should be considered
    trusted. (Otherwise, specify '--noverify' to inhibit certificate validation.)
    To use a client certificate to authenticate to the server, specify
    '--clientcert'. If that file doesn't include the private key, specify it with
    '--clientkey'.
    To use kerberos (SPNEGO) authentication, specify '--kerberos'.

    To see subcommand-specific help, pass '-h' to the subcommand.
    """
    kdc_help_api = 'base URL for management interface'
    kdc_help_profile = 'profile JSON to use (optional)'
    kdc_help_cacert = 'path to CA cert (or bundle) for validating server certificate'
    kdc_help_noverify = 'disable validation of server certificate'
    kdc_help_verbosity = 'verbosity level, 0 means quiet, more than 0 means less quiet'
    kdc_help_clientcert = 'path to client cert to authenticate with'
    kdc_help_clientkey = 'path to client key (if not included with --clientcert)'
    kdc_help_kerberos = 'use Kerberos TGT to authenticate with'
    kdc_help_retries = 'max number of API retries'
    kdc_help_pause = 'number of seconds between retries'
    kdc_help_timeout = 'number of seconds to allow before giving up'
    parser = argparse.ArgumentParser(description=kdc_desc,
                                     epilog=kdc_epilog)
    parser.add_argument('--api', metavar='<URL>',
                        default=os.environ.get('KDCSVC_API_URL'),
                        help=kdc_help_api)
    parser.add_argument('--profile', help=kdc_help_profile, required=False,
                        default='{}')
    parser.add_argument('--cacert', metavar='<PATH>',
                        default=os.environ.get('KDCSVC_API_CACERT'),
                        help=kdc_help_cacert)
    parser.add_argument('--noverify', action='store_true',
                        help=kdc_help_noverify)
    parser.add_argument('--clientcert', metavar='<PATH>',
                        default=os.environ.get('KDCSVC_API_CLIENTCERT'),
                        help=kdc_help_clientcert)
    parser.add_argument('--clientkey', metavar='<PATH>',
                        default=os.environ.get('KDCSVC_API_CLIENTKEY'),
                        help=kdc_help_clientkey)
    parser.add_argument('--kerberos', action='store_true',
                        help=kdc_help_kerberos)
    parser.add_argument('--verbosity', type=int, metavar='<level>',
                        default=0, help=kdc_help_verbosity)
    parser.add_argument('--retries', type=int, metavar='<num>',
                        default=0, help=kdc_help_retries)
    parser.add_argument('--pause', type=int, metavar='<secs>',
                        default=0, help=kdc_help_pause)
    parser.add_argument('--timeout', type=int, metavar='<secs>',
                        default=600, help=kdc_help_timeout)

    subparsers = parser.add_subparsers()

    # Subcommand details

    add_help = 'Register new principals with the KDC'
    add_epilog = """
    The 'add' subcommand invokes the '/v1/add' handler of the KDC Service's
    management API, to trigger the registration of the given Kerberos principals.
    Control over the registration is passed as a JSON string via the --profile
    argument.
    """
    add_help_principals = 'principals to be registered in the KDC'
    parser_a = subparsers.add_parser('add', help=add_help, epilog=add_epilog)
    parser_a.add_argument('principals', help=add_help_principals, nargs='*')
    parser_a.set_defaults(func='add', fname='add')

    add_ns_help = 'Register new namespace principals with the KDC'
    add_ns_epilog = """
    The 'add_ns' subcommand invokes the '/v1/add_ns' handler of the KDC Service's
    management API, to trigger the registration of the given namespace Kerberos
    principals.
    Control over the registration is passed as a JSON string via the --profile
    argument.
    """
    add_ns_help_principals = 'namespace principals to be registered in the KDC'
    parser_a = subparsers.add_parser('add_ns', help=add_ns_help, epilog=add_ns_epilog)
    parser_a.add_argument('principals', help=add_ns_help_principals, nargs='*')
    parser_a.set_defaults(func='add_ns', fname='add_ns')

    get_help = 'Retrieve/list principals on the KDC'
    get_epilog = """
    The 'get' subcommand invokes the '/v1/get' handler of the KDC Service's
    management API, to query its database for the given Kerberos principals,
    which contain wildcards. Providing a single argument '*' queries for all
    principals.
    Control over the query is passed as a JSON string via the --profile
    argument.
    """
    get_help_principals = 'principals to be queried for on the KDC'
    parser_a = subparsers.add_parser('get', help=get_help, epilog=get_epilog)
    parser_a.add_argument('principals', help=get_help_principals, nargs='*')
    parser_a.set_defaults(func='get', fname='get')

    del_help = 'Delete principals from the KDC'
    del_epilog = """
    The 'del' subcommand invokes the '/v1/del' handler of the KDC Service's
    management API, to trigger deregistration of the given Kerberos principals.
    Control over the deregistration is passed as a JSON string via the --profile
    argument.
    """
    del_help_principals = 'principals to be removed from the KDC'
    parser_a = subparsers.add_parser('del', help=del_help, epilog=del_epilog)
    parser_a.add_argument('principals', help=del_help_principals, nargs='*')
    parser_a.set_defaults(func='del', fname='del')

    del_ns_help = 'Delete namespace principals from the KDC'
    del_ns_epilog = """
    The 'del_ns' subcommand invokes the '/v1/del_ns' handler of the KDC Service's
    management API, to trigger deregistration of the given namespace Kerberos
    principals.
    Control over the deregistration is passed as a JSON string via the --profile
    argument.
    """
    del_ns_help_principals = 'namespace principals to be removed from the KDC'
    parser_a = subparsers.add_parser('del_ns', help=del_ns_help, epilog=del_ns_epilog)
    parser_a.add_argument('principals', help=del_ns_help_principals, nargs='*')
    parser_a.set_defaults(func='del_ns', fname='del_ns')

    ext_keytab_help = 'Extract keytab with service principals from the KDC'
    ext_keytab_epilog = """
    The 'ext_keytab' subcommand invokes the '/v1/ext_keytab' handler of the KDC
    Service's management API, to extract a current keytab for the given service
    principals. By default, the returned data is a JSON structure, within which
    the 'stdout' field contains a base64-encoded keytab. If the '--raw'
    argument is provided, the program instead writes the raw keytab file to
    stdout.
    Control over the extraction is passed as a JSON string via the
    --profile argument.
    """
    ext_keytab_help_raw = 'Path to output the raw keytab (extracted from JSON struct)'
    ext_keytab_help_principals = 'namespace principals to be removed from the KDC'
    parser_a = subparsers.add_parser('ext_keytab', help=ext_keytab_help, epilog=ext_keytab_epilog)
    parser_a.add_argument('--raw', type=str, metavar='<path>', default=None, help=ext_keytab_help_raw)
    parser_a.add_argument('principals', help=ext_keytab_help_principals, nargs='*')
    parser_a.set_defaults(func='ext_keytab', fname='ext_keytab')

    # Process the command-line
    args = parser.parse_args()
    set_loglevel(args.verbosity)
    log(f"verbosity={args.verbosity}")
    requests_verify = True
    if not args.api:
        err("Error, no API URL was provided.")
        sys.exit(-1)
    if args.noverify:
        requests_verify = False
    elif args.cacert:
        requests_verify = args.cacert
    if args.kerberos:
        if args.clientcert:
            err("Error, we don't support clientcert + kerberos")
            sys.exit(-1)
        if args.fname != 'ext_keytab':
            err("Error, we only support kerberos for 'ext_keytab'")
            sys.exit(-1)
    requests_cert = False
    if args.clientcert:
        if args.clientkey:
            requests_cert = (args.clientcert,args.clientkey)
        else:
            requests_cert = args.clientcert

    # Dispatch. Here, we are operating as a program with a parent process, not
    # a library with a caller. If we don't catch exceptions, they get handled
    # by the runtime which will print stack traces to stderr and exit, there is
    # no concept of the exceptions reaching the parent process. As such, catch
    # them all here.
    try:
        if args.func == 'add':
            result, j = kdc_add(args.api, args.principals, args.profile,
                                requests_verify = requests_verify,
                                requests_cert = requests_cert,
                                timeout = args.timeout)
        elif args.func == 'add_ns':
            result, j = kdc_add_ns(args.api, args.principals, args.profile,
                                requests_verify = requests_verify,
                                requests_cert = requests_cert,
                                timeout = args.timeout)
        elif args.func == 'get':
            result, j = kdc_get(args.api, args.principals, args.profile,
                                requests_verify = requests_verify,
                                requests_cert = requests_cert,
                                timeout = args.timeout)
        elif args.func == 'del':
            result, j = kdc_del(args.api, args.principals, args.profile,
                                requests_verify = requests_verify,
                                requests_cert = requests_cert,
                                timeout = args.timeout)
        elif args.func == 'del_ns':
            result, j = kdc_del_ns(args.api, args.principals, args.profile,
                                requests_verify = requests_verify,
                                requests_cert = requests_cert,
                                timeout = args.timeout)
        elif args.func == 'ext_keytab':
            result, j = kdc_ext_keytab(args.api, args.principals, args.kerberos,
                                args.raw, args.profile,
                                requests_verify = requests_verify,
                                requests_cert = requests_cert,
                                timeout = args.timeout)
        else:
            raise Exception("BUG")
    except Exception as e:
        print(f"Error, API failed: {e}", file = sys.stderr)
        sys.exit(-1)
    log(f"handler returned: result={result},j={j}")
    if j:
        print(json.dumps(j))
    if not result:
        sys.exit(-1)
