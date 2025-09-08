source /hcp/common/hcp.sh

export HCP_ID=$(hcp_config_extract "vars.id")

# We pull the 'kdcsvc' config once and then interrogate it locally.
export HCP_KDCSVC_JSON=$(hcp_config_extract ".kdcsvc")
export HCP_KDCSVC_GLOBAL_INIT=$(echo "$HCP_KDCSVC_JSON" | jq -r ".toplevel.setup_global.block")
export HCP_KDCSVC_LOCAL_INIT=$(echo "$HCP_KDCSVC_JSON" | jq -r ".toplevel.setup_local.block")
export HCP_KDCSVC_STATE=$(echo "$HCP_KDCSVC_JSON" | jq -r ".state")
export HCP_KDCSVC_MODE=$(echo "$HCP_KDCSVC_JSON" | jq -r ".mode")
export HCP_KDCSVC_SECONDARIES=$(echo "$HCP_KDCSVC_JSON" | jq -r ".secondaries // []")
export HCP_KDCSVC_REALM=$(echo "$HCP_KDCSVC_JSON" | jq -r ".realm")
export HCP_KDCSVC_NAMESPACE=$(echo "$HCP_KDCSVC_JSON" | jq -r ".namespace")
export HCP_KDCSVC_POLICYURL=$(echo "$HCP_KDCSVC_JSON" | jq -r ".policy_url")
export HCP_KDCSVC_ANCHOR=$(echo "$HCP_KDCSVC_JSON" | jq -r ".anchor")
export HCP_KDCSVC_PKINIT_IDENTITY=$(echo "$HCP_KDCSVC_JSON" | jq -r ".pkinit_identity")
export HCP_KDCSVC_KEY_ROTATION_EPOCH=$(echo "$HCP_KDCSVC_JSON" | jq -r ".key_rotation_epoch")
export HCP_KDCSVC_KEY_ROTATION_PERIOD=$(echo "$HCP_KDCSVC_JSON" | jq -r ".key_rotation_period")
export HCP_KDCSVC_MAX_TICKET_LIFE=$(echo "$HCP_KDCSVC_JSON" | jq -r ".max_ticket_life")
export HCP_KDCSVC_MAX_RENEWABLE_LIFE=$(echo "$HCP_KDCSVC_JSON" | jq -r ".max_renewable_life")

echo "Parsed 'kdcsvc': $HCP_HOSTNAME"
echo "               STATE: $HCP_KDCSVC_STATE"
echo "         GLOBAL_INIT: $HCP_KDCSVC_GLOBAL_INIT"
echo "          LOCAL_INIT: $HCP_KDCSVC_LOCAL_INIT"
echo "                MODE: $HCP_KDCSVC_MODE"
echo "         SECONDARIES: $HCP_KDCSVC_SECONDARIES"
echo "               REALM: $HCP_KDCSVC_REALM"
echo "           NAMESPACE: $HCP_KDCSVC_NAMESPACE"
echo "           POLICYURL: $HCP_KDCSVC_POLICYURL"
echo "              ANCHOR: $HCP_KDCSVC_ANCHOR"
echo "     PKINIT_IDENTITY: $HCP_KDCSVC_PKINIT_IDENTITY"
echo "  KEY_ROTATION_EPOCH: $HCP_KDCSVC_KEY_ROTATION_EPOCH"
echo " KEY_ROTATION_PERIOD: $HCP_KDCSVC_KEY_ROTATION_PERIOD"
echo "     MAX_TICKET_LIFE: $HCP_KDCSVC_MAX_TICKET_LIFE"
echo "  MAX_RENEWABLE_LIFE: $HCP_KDCSVC_MAX_RENEWABLE_LIFE"

if [[ ! -d $HCP_KDCSVC_STATE ]]; then
	echo "Error, kdcsvc::state isn't a directory: $HCP_KDCSVC_STATE" >&2
	exit 1
fi

if [[ -z $HCP_KDCSVC_REALM ]]; then
	echo "Error, HCP_KDCSVC_REALM isn't set" >&2
	exit 1
fi

if [[ -z $HCP_KDCSVC_NAMESPACE ]]; then
	echo "Error, HCP_KDCSVC_NAMESPACE isn't set" >&2
	exit 1
fi
