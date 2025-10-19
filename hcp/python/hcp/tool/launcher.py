#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import json
import os
import sys
import subprocess
import time
import tempfile

# Special handling, as launcher is often the first contact between
# an environment and the HCP machinery. If PYTHONPATH has been lost
# (eg. through an 'su - <user>' command), this should get it back.
try:
    from gson.union import union
except:
    sys.path.append('/hcp/python')
    os.environ['PYTHONPATH'] = '/hcp/python' # For future sub-shells
    from gson.union import union

from gson.mutater import mutate
import hcp.common

# The number of seconds to pause when waiting for a blocking command to complete
# or when waiting for a signalled task to exit.
DELAY_FAST = 0.2

# The number of seconds to pause when waiting to see if a service has dropped.
DELAY_SLOW = 10

class Service:
    def __init__(self, stanza):
        self.stanza = stanza
        self._name = self.stanza['key']
        self._will_exit = self.stanza['will_exit'] \
            if 'will_exit' in self.stanza else False
    def name(self):
        return self._name
    def is_called(self, name):
        return self._name == name
    def exec(self, parent_env, args):
        env = parent_env.copy()
        if 'env' in self.stanza:
            myenv = self.stanza['env']
            for k in myenv:
                env[k] = myenv[k]
        env['HCP_CONFIG_FILE'] = os.environ['HCP_CONFIG_FILE']
        cmd = self.stanza['exec']
        if isinstance(cmd, str):
            cmd = [ cmd ]
        cwd = self.stanza['cwd'] if 'cwd' in self.stanza else None
        self.popen = subprocess.Popen(cmd + args, env = env, cwd = cwd)
        b = self.stanza['block'] if 'block' in self.stanza else False
        if b:
            while True:
                if self.popen.poll() != None:
                    break
                if isinstance(b, str) and os.path.isfile(b):
                    break
                time.sleep(DELAY_FAST)
    def exited(self):
        return self.popen.poll() != None
    def will_exit(self):
        return self._will_exit
    def wait(self):
        self.popen.wait()
    def teardown(self):
        if self.popen.poll() == None:
            self.popen.terminate()
        while self.popen.poll() == None:
            time.sleep(DELAY_FAST)
    def returncode(self):
        ret = self.popen.poll()
        if ret == None:
            raise Exception('BUG')
        return ret

class Nexus:
    def __init__(self, env, args, args_for = None, result_from = None):
        self.env = union(os.environ.copy(), env if env else {})
        self.args = args
        self.args_for = args_for
        self.result_from = result_from
        self.services = []
        self.exiting = False
        self._returncode = None
    def add_service(self, service):
        if not isinstance(service, Service):
            raise Exception('BUG')
        service.exec(self.env, 
                     self.args if service.is_called(self.args_for) else [])
        self.services.append(service)
    def is_exiting(self):
        if self.exiting:
            return True
        if len(self.services) == 0:
            self.exiting = True
        else:
            for s in self.services:
                if s.exited() and not s.will_exit():
                    self.exiting = True
                    if s.name() == self.result_from:
                        self._returncode = s.returncode()
        return self.exiting
    def teardown(self):
        for s in self.services:
            s.teardown()
            if s.name() == self.result_from:
                self._returncode = s.returncode()
    def returncode(self):
        return self._returncode

def launch(args):
    if 'HCP_CONFIG_MUTATE' not in os.environ:
        print('HCP_CONFIG_MUTATE was lost. E.g. for \'su\', don\'t forget',
              file = sys.stderr)
        print('to use:  su -w HCP_CONFIG_MUTATE - <user>',
              file = sys.stderr)
        raise Exception('No host config mutate given')
    configpath = os.environ['HCP_CONFIG_MUTATE']
    if not os.path.isfile(configpath):
        raise Exception(f"Host config not found: {config}")

    orig = os.environ['HCP_CONFIG_MUTATE']
    with open(orig, 'r') as fp:
        preworld = json.load(fp)
    world = mutate(preworld)
    _tempdir = tempfile.TemporaryDirectory()
    n = f"{_tempdir.name}/workload.json"
    with open(n, 'w') as fp:
        json.dump(world, fp)
    os.environ['HCP_CONFIG_FILE'] = n
    os.chmod(_tempdir.name, 0o755)
    os.chmod(n, 0o444)

    # Load the config, extract any top-level 'env', 'args_for', 'result_from',
    # 'foreground', and '_' (the latter is a convention for comments)
    config = world
    env = config.pop('env') if 'env' in config else {}
    args_for = config.pop('args_for') if 'args_for' in config else None
    result_from = config.pop('result_from') if 'result_from' in config else None
    foreground = config.pop('foreground') if 'foreground' in config else None
    _ = config.pop('_') if '_' in config else None
    # Also, pop the vars so that we don't mistake it for a service stanza
    _vars = config.pop('vars') if 'vars' in config else {}

    # Anything left is a service stanza. As we allow service stanzas to contain
    # other top-level service stanzas, pop them out at this stage and union
    # them with the top-level.
    popped_toplevel = True
    while popped_toplevel:
        popped_toplevel = False
        keys = [ service for service in config ]
        for key in keys:
            s = config[key]
            if 'toplevel' in s:
                toplevel = s.pop('toplevel')
                config = union(config, toplevel)
                popped_toplevel = True

    # Unlike other consumers of this config (the services themselves), we care
    # more about the order they are in than what they are called. So we want a
    # list instead.
    # It's not that we don't care at all: take note of each stanza's name
    # (within the stanza itself) before doing the dict->list conversion.
    for key in config:
        config[key]['key'] = key
    if len(args) and not args[0].startswith('-'):
        # The args are telling us what to run
        stanzas = [ {
            'id': 'dedicated',
            'key': 'dedicated',
            'priority': 0,
            'exec': args,
            'block': True } ]
        args_for = 'dedicated'
        result_from = 'dedicated'
        args = []
    else:
        if len(args) and args[0] == '--':
            args.pop(0)
        # Create a list and discard stanzas that we don't act on
        stanzas = [ config[key] for key in config if \
            'exec' in config[key] and 'ignore' not in config[key] ]
    # Put the list in priority-order.
    stanzas.sort(key = lambda stanza: stanza['priority'])
    # Convert the list of stanzas to a list of service objects
    services = [ Service(stanza) for stanza in stanzas ]

    # Our 'Nexus' holds and manages our spawned service processes
    nexus = Nexus(env, args, args_for = args_for, result_from = result_from)

    # One by one, work through the prioritised service list
    fg = None
    for service in services:
        if foreground and service.name() == foreground:
            fg = service
        nexus.add_service(service)
        if nexus.is_exiting():
            break

    # Hack. For qemu/uml guests, the host runners are groping for a sign that
    # the workloads within the VMs are launched. Give it to them.
    if os.path.isdir('/hosthack') and os.getuid() == 0:
        with open('/hosthack/tmp/vm.workload.running', 'w') as _:
            pass
    # Something similar even if we're not a VM
    try:
        with open('/tmp/workload.running', 'w') as _:
            pass
    except:
        pass

    if foreground:
        if fg:
            fg.wait()
    else:
        while not nexus.is_exiting():
            time.sleep(DELAY_SLOW)

    nexus.teardown()
    return nexus.returncode()

if __name__ == '__main__':

    sys.argv.pop(0)

    ret = launch(sys.argv)
    sys.exit(ret)
