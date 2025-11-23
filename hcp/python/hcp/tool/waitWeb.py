#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import json
import requests
import os
import sys
import argparse
import time

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

def set_kerberos():
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
        #except requests.exceptions.RequestException as e:
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

# Handler functions for the subcommands (add, query, delete, find)
# They all return a 2-tuple of {result,json}, where result is True iff the
# operation was successful.

def enroll_add(api, ekpub, profile = None, requests_verify = True,
               requests_cert = False, retries = 0, timeout = 120):
    debug(f"enroll_add:")
    debug(f"  api={api}")
    debug(f"  ekpub={ekpub}")
    debug(f"  profile={profile}")
    debug(f"  requests_verify={requests_verify}")
    debug(f"  requests_cert={requests_cert}")
    form_data = {
        'ekpub': ('ek.pub', open(ekpub, 'rb'))
    }
    if profile:
        form_data['profile'] = (None, profile)
    myrequest = lambda: requests.post(api + '/v1/add',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    if response.status_code != 201:
        err(f"Error, 'add' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'add' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def enroll_reenroll(api, ekpubhash, requests_verify = True,
                    requests_cert = False, retries = 0, timeout = 120):
    form_data = { 'ekpubhash': (None, ekpubhash) }
    debug("'reenroll' handler about to call API")
    debug(f" - url: {api + '/v1/reenroll'}")
    debug(f" - files: {form_data}")
    myrequest = lambda: requests.post(api + '/v1/reenroll',
                                      files = form_data,
                                      auth = auth,
                                      verify = requests_verify,
                                      cert = requests_cert,
                                      timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 201:
        err(f"Error, 'reenroll' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        err(f"Error, JSON decoding of 'add' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

def do_query_or_delete(api, ekpubhash, is_delete, nofiles,
                       requests_verify = True, requests_cert = False,
                       retries = 0, timeout = 120):
    form_data = {
        'ekpubhash': (None, ekpubhash)
    }
    if nofiles:
        form_data['nofiles'] = (None, True)
    if is_delete:
        debug("'delete' handler about to call API")
        debug(f" - url: {api + '/v1/delete'}")
        debug(f" - files: {form_data}")
        myrequest = lambda: requests.post(api + '/v1/delete',
                                          files = form_data,
                                          auth = auth,
                                          verify = requests_verify,
                                          cert = requests_cert,
                                          timeout = timeout)
        response = requester_loop(myrequest, retries = retries)
    else:
        debug("'query' handler about to call API")
        debug(f" - url: {api + '/v1/query'}")
        debug(f" - params: {form_data}")
        myrequest = lambda: requests.get(api + '/v1/query',
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

def enroll_query(api, ekpubhash, nofiles, **kwargs):
    return do_query_or_delete(api, ekpubhash, False, nofiles, **kwargs)

def enroll_delete(api, ekpubhash, nofiles, **kwargs):
    return do_query_or_delete(api, ekpubhash, True, nofiles, **kwargs)

def enroll_janitor(api, requests_verify = True, requests_cert = False,
                   retries = 0, timeout = 120):
    debug("'janitor' handler about to call API")
    debug(f" - url: {api + '/v1/janitor'}")
    myrequest = lambda: requests.get(api + '/v1/janitor',
                                     auth = auth,
                                     verify = requests_verify,
                                     cert = requests_cert,
                                     timeout = timeout)
    response = requester_loop(myrequest, retries = retries)
    debug(f" - response: {response}")
    debug(f" - response.content: {response.content}")
    if response.status_code != 200:
        log(f"Error, 'janitor' response status code was {response.status_code}")
        return False, None
    try:
        jr = json.loads(response.content)
    except Exception as e:
        log("Error, JSON decoding of 'janitor' response failed: {e}")
        return False, None
    debug(f" - jr: {jr}")
    return True, jr

if __name__ == '__main__':

    ww_desc = 'Tool for polling on the availability of a URL'
    ww_epilog = """
    If the API is using HTTPS and the server certificate is not signed by a CA
    that is already trusted by the system, '--cacert' should be used to specify
    a CA certificate (or bundle) that should be considered trusted. (Otherwise,
    specify '--noverify' to inhibit certificate validation.) To use a client
    certificate to authenticate to the server, specify '--clientcert'. If that
    file doesn't include the private key, specify it with '--clientkey'.

    To see subcommand-specific help, pass '-h' to the subcommand.
    """
    ww_help_cacert = 'path to CA cert (or bundle) for validating server certificate'
    ww_help_noverify = 'disable validation of server certificate'
    ww_help_verbosity = 'verbosity level, 0 means quiet, more than 0 means less quiet'
    ww_help_clientcert = 'path to client cert to authenticate with'
    ww_help_clientkey = 'path to client key (if not included with --clientcert)'
    ww_help_kerberos = 'authenticate using GSSAPI (Kerberos/SPNEGO)'
    ww_help_retries = 'max number of retries'
    ww_help_pause = 'number of seconds between retries'
    ww_help_timeout = 'number of seconds to allow before giving up'
    ww_help_URL = 'the \'GET\' URL to poll for'
    ww_help_show = 'send the URL response to stdout'
    parser = argparse.ArgumentParser(description=ww_desc,
                                     epilog=ww_epilog)
    parser.add_argument('--cacert', metavar='<PATH>',
                        default=os.environ.get('WAITWEB_CACERT'),
                        help=ww_help_cacert)
    parser.add_argument('--noverify', action='store_true',
                        help=ww_help_noverify)
    parser.add_argument('--clientcert', metavar='<PATH>',
                        default=os.environ.get('WAITWEB_CLIENTCERT'),
                        help=ww_help_clientcert)
    parser.add_argument('--clientkey', metavar='<PATH>',
                        default=os.environ.get('WAITWEB_CLIENTKEY'),
                        help=ww_help_clientkey)
    parser.add_argument('--kerberos', action='store_true',
                        help=ww_help_kerberos)
    parser.add_argument('--verbosity', type=int, metavar='<level>',
                        default=0, help=ww_help_verbosity)
    parser.add_argument('--retries', type=int, metavar='<num>',
                        default=0, help=ww_help_retries)
    parser.add_argument('--pause', type=int, metavar='<secs>',
                        default=0, help=ww_help_pause)
    parser.add_argument('--timeout', type=int, metavar='<secs>',
                        default=600, help=ww_help_timeout)
    parser.add_argument('--show', action='store_true',
                        help=ww_help_show)
    parser.add_argument('URL',
                        default=os.environ.get('WAITWEB_CLIENTKEY'),
                        help=ww_help_URL)

    # Process the command-line
    args = parser.parse_args()
    set_loglevel(args.verbosity)
    log(f"verbosity={args.verbosity}")
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
    if args.kerberos or os.environ.get('HCP_GSSAPI'):
        set_kerberos()

    # Dispatch. Here, we are operating as a program with a parent process, not
    # a library with a caller. If we don't catch exceptions, they get handled
    # by the runtime which will print stack traces to stderr and exit, there is
    # no concept of the exceptions reaching the parent process. As such, catch
    # them all here.
    try:
        myrequest = lambda: requests.get(args.URL,
                                         auth = auth,
                                         verify = requests_verify,
                                         cert = requests_cert,
                                         timeout = args.timeout)
        response = requester_loop(myrequest,
                                  retries = args.retries,
                                  pause = args.pause)
        if response.status_code < 200 or response.status_code >= 300:
            err(f"Error, response status code was {response.status_code}")
            raise Exception("URL failed")
    except Exception as e:
        print(f"Error, unable to hit URL: {e}", file = sys.stderr)
        sys.exit(-1)
    if args.show:
        print(response.content)
