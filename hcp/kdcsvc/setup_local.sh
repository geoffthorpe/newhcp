#!/bin/bash

echo "Initializing (rootfs-local) kdcsvc state"

source /hcp/kdcsvc/common.sh

if [[ ! -f $HCP_KDCSVC_GLOBAL_INIT ]]; then
	echo "Error, setup_local.sh being run before setup_global.sh" >&2
	exit 1
fi

if [[ -f "$HCP_KDCSVC_LOCAL_INIT" ]]; then
	echo "Error, setup_local.sh being run but already initialized" >&2
	exit 1
fi

# Create any symlinks in the rootfs that are expected
# Oh, and by the way there is a gotcha - any files in /etc/sudoers.d/ that have
# '.' characters in their filenames will be ignored. ($%@&!!!!!)
# Sadly, HCP_ID values can and do have '.' characters in them, sometimes.
# (They're basically the FQDN minus the canonical domain, so there can be
# ndots.) Hence the weird substitution going on here;
BORKBORK="/etc/sudoers.d/hcp-$(echo "$HCP_ID" | sed -e "s/\./_/g")"
if ! ln -s "$HCP_KDCSVC_STATE/etc/sudoers" "$BORKBORK" > /dev/null 2>&1 && \
		[[ ! -h $BORKBORK ]]; then
	echo "Error, couldn't create symlink '$BORKBORK'" >&2
	exit 1
fi

# Done!
mkdir -p $(dirname $HCP_KDCSVC_LOCAL_INIT)
touch "$HCP_KDCSVC_LOCAL_INIT"
echo "Local state now initialized"
