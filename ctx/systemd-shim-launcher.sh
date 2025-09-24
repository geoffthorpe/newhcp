#!/bin/bash

set -e

source /_env/env

export HCP_SDNOTIFY=1

/hcp/python/hcp/tool/launcher.py $@

# Once the launcher exits, that's our cue to tear down
shutdown -h now
