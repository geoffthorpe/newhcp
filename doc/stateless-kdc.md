# Stateless KDC service

This service takes advantage of two powerful new features in the Heimdal
kerberos implementation: namespace principals and synthetic principals.
The result is that service and client/role principals do not need to be known
and registered in the KDC database - the service is "stateless" in that sense.
Instead, users and service owners are provisioned with X509v3 certificates that
have the desired principals encoded within them - these certificates are issued
and delivered by HCP itself (as in the reference usecase) or through whatever
other PKI tooling is preferred. If the KDC is sent such a certificate (and
validates it), it can then return a TGT (for client/role principals) or keytab
(for service principals) for the principal in that certificate, even if that
principal isn't registered.

## Namespace principals

This feature implements a kind of "wildcard" service principal, such that all
principals fitting that wildcard pattern ("namespace") can be deterministically
derived from the namespace principal, as can the corresponding keys at an
arbitrary point in time (key-rotation is important).

The reference usecase uses two namespace principals, as can be seen in the
following output;

```
$ docker-compose exec attestsvc /hcp/python/hcp/api/kdc.py \
    --api https://kdc_secondary.hcphacking.xyz \
    --cacert /ca_default \
    --clientcert /cred_kdcclient \
    get > foo.json
$ jq . foo.json
{
  "cmd": "get",
  "realm": "HCPHACKING.XYZ",
  "requested": [],
  "principals": [
    "default@HCPHACKING.XYZ",
    "kadmin/admin@HCPHACKING.XYZ",
    "kadmin/hprop@HCPHACKING.XYZ",
    "kadmin/changepw@HCPHACKING.XYZ",
    "changepw/kerberos@HCPHACKING.XYZ",
    "WELLKNOWN/ANONYMOUS@HCPHACKING.XYZ",
    "WELLKNOWN/FEDERATED@HCPHACKING.XYZ",
    "krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ",
    "WELLKNOWN/org.h5l.fast-cookie@WELLKNOWN:ORG.H5L",
    "WELLKNOWN/HOSTBASED-NAMESPACE/_/hcphacking.xyz@HCPHACKING.XYZ",
    "WELLKNOWN/HOSTBASED-NAMESPACE/host/hcphacking.xyz@HCPHACKING.XYZ"
  ]
}
```

The last two principals have the `WELLKNOWN/HOSTBASED-NAMESPACE` prefix - they
are the namespace principals. The first of the two has an underscore as the
service identifier, which acts as a wild-card. The latter of the two has the
`host` service identifier, as used for SSH services - that namespace principal
is configured to allow delegation.

Note, the `kdcsvc` API endpoint provides keytabs for service principals.

* The `ext_keytab` API will provide keytabs for _any_ requested principals, so
  long as the caller of the API has successfully authenticated using a client
  certificate. It is therefore essential to use an appropriately privileged CA
  for such credentials. In the reference usecase, the `attestsvc` service uses
  client certificate authentication to obtain keytab assets for arbitrary
  enrolled hosts from kdc\_secondary. So `shell` gets its keytab via
  attestation.

The following steps are performed automatically within `attestsvc`, to get the
keytab for `shell`. In the example below, you can see how the key versions in
the keytabs being returned to `shell` rotate with time.
```
$ docker-compose exec attestsvc bash
root@attestsvc:/# \
        /hcp/python/hcp/api/kdc.py \
                --api https://kdc_secondary.hcphacking.xyz \
                --cacert /ca_default \
                --clientcert /cred_kdcclient \
                ext_keytab host/shell.hcphacking.xyz | \
        jq -r .stdout | \
        base64 -d > kt
root@attestsvc:/# ktutil -k kt list
kt:

Vno  Type                     Principal                                     Aliases
 28  aes128-cts-hmac-sha1-96  host/shell.hcphacking.xyz@HCPHACKING.XYZ
 29  aes128-cts-hmac-sha1-96  host/shell.hcphacking.xyz@HCPHACKING.XYZ
root@attestsvc:/#
root@attestsvc:/# # Sleep 1 hour, the default rotation period for namespace principals
root@attestsvc:/# sleep 3600
root@attestsvc:/# \
        /hcp/python/hcp/api/kdc.py \
                --api https://kdc_secondary.hcphacking.xyz \
                --cacert /enrollcertchecker/CA.cert \
                --clientcert /enrollclient/client.pem \
                ext_keytab host/shell.hcphacking.xyz | \
        jq -r .stdout | \
        base64 -d > kt
root@attestsvc:/# ktutil -k kt list
kt:

Vno  Type                     Principal                                     Aliases
 29  aes128-cts-hmac-sha1-96  host/shell.hcphacking.xyz@HCPHACKING.XYZ
 30  aes128-cts-hmac-sha1-96  host/shell.hcphacking.xyz@HCPHACKING.XYZ
```

## Synthetic principals

Synthetic principals are simpler than namespace principals because they (only)
concern client/role principals and do not need to be derived from a base
principal. (A KDC can issue a TGT for any client/role principal at all.)

The namespace and synthetic principals features can enabled in the KDC's
configuration file, under the HDB section, as seen here;

```
$ docker-compose exec kdc_primary cat /kdc_primary/etc/kdc.conf

   [...]

[hdb]
	db-dir = /kdc_primary/var
	enable_virtual_hostbased_princs = true
	virtual_hostbased_princ_mindots = 1
	virtual_hostbased_princ_maxdots = 5
	enable_synthetic_clients = true
	synthetic_clients_forwardable = true

   [...]
```

The following illustrates how a TGT for a synthetic principal can be obtained by using an X509v3 certificate with the desired principal encoded within it.

```
$ docker-compose exec alicia ls -l /assets
   [...]
-rw------- 1 alicia root 2989 Aug 19 17:46 pkinit-client-alicia.pem
   [...]
$ docker-compose exec alicia /install-heimdal/bin/hxtool print --content \
    /assets/pkinit-client-alicia.pem | grep Kerberos
	otherName: 1.3.6.1.5.2.2 KerberosPrincipalName alicia@HCPHACKING.XYZ
$ docker-compose exec alicia /install-heimdal/bin/kinit -C \
    FILE:/assets/pkinit-client-alicia.pem alicia \
    /install-heimdal/bin/klist
Credentials cache: FILE:/tmp/krb5cc_n6pEWh
        Principal: alicia@HCPHACKING.XYZ

  Issued                Expires               Principal
Nov 25 19:48:25 2024  Nov 25 19:53:25 2024  krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ
```

## `kdcsvc`

### The kdcsvc API, and `/hcp/python/hcp/api/kdc.py`

The KDC Service runs a `webapi` instance whose interface is derived from the
command-line interface of the kadmin tool. It supports the following actions on
the KDC database; `add`, `add_ns`, `get`, `del`, `del_ns`, and `ext_keytab`.
These allow it to (respectively) add new regular principals, add new namespace
principals, query principals, delete regular principals, delete namespace
principals, and extract keytabs for service principals. This service should
always be run with HTTPS. As with all webapi-hosted apps, it supports
client-authentication options `clientcert` and `kerberos`. The service will
allow any and all commands if a valid client certificate was used, as this is
used to infer administrative privilege. If instead the client is
kerberos-authenticated, the service will only support the `ext_keytab` command
and will only allow the user's own principal to be exported to a keytab.

Note, in the HCP workflow and the reference usecase, the presence of the KDC
service is to show how it can operate statelessly, where _all_ principals are
derived on-the-fly based on certificates. In this mode of operation, there
should be no need to manipulate the KDC database, but the ability to do so
supports hybrid scenarios and/or helps when migrating a legacy database over to
stateless usage. The KDC's database can register and use (and replicate)
conventional principals, even if the reference usecase only makes use of the
new, dynamically-generated kinds of principals.

To help with the use of the KDC web API, the `/hcp/python/hcp/api/kdc.py`
library and tool can be used. The earlier section on namespace principals shows
an example usage - one can get further usage information about how to invoke
the tool by adding a `--help` argument. (For importing it into other python
code, the easiest reference is to read the code itself.)

### kdcsvc replication

As the reference usecase demonstrates, it is possible to run both primary
(a.k.a. "authoratative" or "master") and secondary (a.k.a. "non-authoratative"
or "slave") KDCs, with replication between them. This is done in the reference
usecase simply to demonstrate (and test) the capabilities, even though the
reference usecase doesn't register any of its principals with the KDC (and so
the replication doesn't ever need to wake up - it can be tested by
manual/ad-hoc modifications to the primary and checking that they replicate to
the secondaries).

When a primary KDC is configured, it is automatically set up to run the
`ipropd-master` service to provide a replication source, and the list of
allowed secondaries must be configured up-front. When a secondary KDC is
configured, it is automatically set up to run the `ipropd-slave` server to
provide a replication sink and pull database updates from the primary.

```
$ docker-compose exec kdc_primary jq .kdcsvc.secondaries \
        /tmp/workloads/kdc_primary.json
[
  "kdc_secondary.hcphacking.xyz"
]
$ docker-compose exec kdc_secondary jq .vars.kdcsvc_primary \
        /tmp/workloads/kdc_secondary.json
"kdc_primary.hcphacking.xyz"
```

### primary versus secondary

The presence of multiple (primary and secondary) KDC services poses the
question of which should be used for which kinds of operations. Clearly any
requirement to modify the KDC database must be directed to the primary. However
other APIs (queries with `get`, keytab extraction with `ext_keytab`) can be
directed at either, unless access restrictions are used at the networking or
authentication layers to decide the matter.

The key run-time usage of KDCs is in the issuance of TGTs and service-tickets,
which is typically controlled by the `krb5.conf` file used by Kerberos tools
and libraries. The reference usecase generates krb5.conf files and installs
them via attestation, and all KDC usage is directed to the secondary with the
exception of the KDCs themselves, which are both configured to use the primary
as authoratative.
