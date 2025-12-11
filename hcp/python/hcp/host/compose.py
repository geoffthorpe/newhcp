#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import sys
import os
import enum
import subprocess

class SubprocessFailure(Exception):
    pass

def _srun(args, **xargs):
    c = subprocess.run(args, **xargs)
    if c.returncode != 0:
        raise SubprocessFailure()
    return c

class Container:

    def __init__(self, composer, name):
        self.composer = composer
        self.name = name
        self.running = False

    def up(self):
        args = [ 'docker', 'compose', 'up', '-d', self.name ]
        self.composer.log(True, f"subprocess.run({args})")
        return _srun(args,
            stdout = subprocess.PIPE if not self.composer.verbose else sys.stdout,
            stderr = subprocess.PIPE if not self.composer.verbose else sys.stderr)

    def run(self, args):
        args = [ 'docker', 'compose', 'run', '--rm', self.name ] + args
        self.composer.log(True, f"subprocess.run({args})")
        return _srun(args,
            stdout = subprocess.PIPE if not self.composer.verbose else sys.stdout,
            stderr = subprocess.PIPE if not self.composer.verbose else sys.stderr)
    def runT(self, args, **runargs):
        args = [ 'docker', 'compose', 'run', '-iT', '--rm', self.name ] + args
        self.composer.log(True, f"subprocess.run({args})")
        return _srun(args, **runargs)

    def exec(self, args):
        args = [ 'docker', 'compose', 'exec', self.name ] + args
        self.composer.log(True, f"subprocess.run({args})")
        return _srun(args,
            stdout = subprocess.PIPE if not self.composer.verbose else sys.stdout,
            stderr = subprocess.PIPE if not self.composer.verbose else sys.stderr)
    def execT(self, args, **runargs):
        args = [ 'docker', 'compose', 'exec', '-iT', self.name ] + args
        self.composer.log(True, f"subprocess.run({args})")
        return _srun(args, **runargs)

class Composer:

    def log(self, verbose, txt, **printargs):
        if self.quiet:
            return
        if verbose and not self.verbose:
            return
        print(txt, **printargs)

    def __init__(self, project = None, verbose = False, quiet = False):
        self.verbose = verbose
        self.quiet = quiet
        if project:
            self.project = project
            self.log(True, f"Explicitly setting project prefix: {self.project}")
        else:
            self.project = os.getcwd()
            self.log(True, f"Implicitly setting project prefix: {self.project}")

    def down(self):
        args = [ 'docker', 'compose', 'down', '-v', '--remove-orphans' ]
        self.log(True, f"subprocess.run({args})")
        _srun(args,
            stdout = subprocess.PIPE if not self.verbose else sys.stdout,
            stderr = subprocess.PIPE if not self.verbose else sys.stderr)

if __name__ == '__main__':

    print("Not executable (yet)", file = sys.stderr)
    sys.exit(1)
