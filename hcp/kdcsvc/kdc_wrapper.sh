#!/bin/bash

source /hcp/kdcsvc/common.sh

export KRB5_KDC_PROFILE="$HCP_KDCSVC_STATE/etc/kdc.conf"
krb5kdc -n
