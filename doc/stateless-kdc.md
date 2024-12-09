# Stateless KDC service

This service takes advantage of two powerful new features in the Heimdal kerberos implementation, namely namespace principals and synthetic principals. The result is that service and client/role principals do not need to be known and registered in the KDC database - the service is "stateless" in that sense. Instead, users and service owners are provisioned with X509v3 certificates that have the desired principals encoded within them - these certificates are issued and delivered by HCP itself (as in the reference usecase) or through whatever other PKI tooling is preferred. If the KDC is sent such a certificate (and validates it), it can then return a TGT (for client/role principals) or keytab (for service principals) for the principal in that certificate, even if that principal isn't registered.

## Namespace principals

This feature implements a kind of "wildcard" service principal, such that all principals fitting that wildcard pattern ("namespace") can be deterministically derived from the namespace principal, as can the corresponding keys at an arbitrary point in time (key-rotation is important).

The reference usecase uses two namespace principals, as can be seen in the following output;

```
$ docker-compose exec emgmt /hcp/python/HcpApiKdc.py \
    --api https://secondary.kdc.hcphacking.xyz \
    --cacert /enrollcertchecker/CA.cert \
    --clientcert /enrollclient/client.pem \
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

The last two principals have the `WELLKNOWN/HOSTBASED-NAMESPACE` prefix - they are the namespace principals. The first of the two has an underscore as the service identifier, which acts as a wild-card. The latter of the two has the `host` service identifier, as used for SSH services, and that namespace principal is configured to allow delegation. Service principals that match the network address `<something>.hcphacking.xyz` and the realm `HCPHACKING.XYZ` but do not have the `host` service identifier will match on (and be derived from) the underscored namespace principal, which is configured not to allow delegation.

Note, the `kdcsvc` API endpoint provides two ways to obtain keytabs for service principals.

* The `ext_keytab` API will provide keytabs for _any_ requested principals, so long as the caller of the API has successfully authenticated using a client certificate. It is therefore essential to use an appropriately privileged CA for such credentials. In the reference usecase, the `emgmt` container of the Enrollment service uses client certificate authentication to enroll keytab assets for arbitrary enrolled hosts and this is how `ssherver1` gets its keytab, namely via attestation.
* If the caller of the `ext_keytab` API successfully authenticates using kerberos (SPNEGO), it will be issued with a keytab _only for the caller's principal_. In the reference usecase, the `ssherver2` host gets a pkinit-style certificate through attestation, and that will have the service principal encoded within it. The `ssherver2` host then runs a `keytabber` service that can use that certificate to obtain the keytab corresponding to it, using `run_keytabclient.sh`. 

The following steps are performed automatically within `emgmt`, to get the keytab for `ssherver1`'s enrollment data. In the example below, you can see how the key versions in the keytabs being returned to `ssherver1` rotate with time.
```
$ docker-compose exec emgmt bash
root@emgmt:/# \
        /hcp/python/HcpApiKdc.py \
                --api https://secondary.kdc.hcphacking.xyz \
                --cacert /enrollcertchecker/CA.cert \
                --clientcert /enrollclient/client.pem \
                ext_keytab host/ssherver1.hcphacking.xyz | \
        jq -r .stdout | \
        base64 -d > kt
root@emgmt:/# ktutil -k kt list
kt:

Vno  Type                     Principal                                     Aliases
 28  aes128-cts-hmac-sha1-96  host/ssherver1.hcphacking.xyz@HCPHACKING.XYZ
 29  aes128-cts-hmac-sha1-96  host/ssherver1.hcphacking.xyz@HCPHACKING.XYZ
root@emgmt:/#
root@emgmt:/# # Sleep 1 hour, the default rotation period for namespace principals
root@emgmt:/# sleep 3600
root@emgmt:/# \
        /hcp/python/HcpApiKdc.py \
                --api https://secondary.kdc.hcphacking.xyz \
                --cacert /enrollcertchecker/CA.cert \
                --clientcert /enrollclient/client.pem \
                ext_keytab host/ssherver1.hcphacking.xyz | \
        jq -r .stdout | \
        base64 -d > kt
root@emgmt:/# ktutil -k kt list
kt:

Vno  Type                     Principal                                     Aliases
 29  aes128-cts-hmac-sha1-96  host/ssherver1.hcphacking.xyz@HCPHACKING.XYZ
 30  aes128-cts-hmac-sha1-96  host/ssherver1.hcphacking.xyz@HCPHACKING.XYZ
```

The following steps are performed periodically within `ssherver2`, which relies on an always-fresh, pkinit-style certificate being provided to it via attestation. (The `attester` background service makes sure this is so by periodically running the attestation client.) People familiar with Kerberos will want to take note that the TGT being used in this example is issued for a _service principal_, and not a user/role-style principal as would normally be the case.

```
$ docker-compose exec ssherver2 bash
root@ssherver2:/# kinit -C FILE:/etc/pkinit/sshd-key.pem host/ssherver2.hcphacking.xyz bash
root@ssherver2:/# klist
Credentials cache: FILE:/tmp/krb5cc_LKLfZS
        Principal: host/ssherver2.hcphacking.xyz@HCPHACKING.XYZ

  Issued                Expires               Principal
Dec 12 22:07:20 2024  Dec 12 22:37:20 2024  krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ
root@ssherver2:/# \
        /hcp/python/HcpApiKdc.py \
                --api https://keytab.kdc.hcphacking.xyz \
                --cacert /enrollcertchecker/CA.cert \
                --kerberos \
                ext_keytab | \
        jq -r .stdout | \
        base64 -d > kt
root@ssherver2:/# ktutil -k kt list
kt:

Vno  Type                     Principal                                     Aliases
 29  aes128-cts-hmac-sha1-96  host/ssherver2.hcphacking.xyz@HCPHACKING.XYZ
 28  aes128-cts-hmac-sha1-96  host/ssherver2.hcphacking.xyz@HCPHACKING.XYZ
```

## Synthetic principals

Synthetic principals are simpler than namespace principals because they (only) concern client/role principals and do not need to be derived from a base principal. (A KDC can issue a TGT for any client/role principal at all.)

The namespace and synthetic principals features can enabled in the KDC's configuration file, under the HDB section, as seen here;

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
$ docker-compose exec workstation1 ls -l /home/luser/.hcp/pkinit
total 12
-rw------- 1 luser root 4314 Nov 25 19:39 user-luser-key.pem
-rw-r--r-- 1 luser root 2644 Nov 25 19:39 user-luser.pem
$ docker-compose exec workstation1 /install-heimdal/bin/hxtool print --content \
    /home/luser/.hcp/pkinit/user-luser.pem | grep Kerberos
	otherName: 1.3.6.1.5.2.2 KerberosPrincipalName luser@HCPHACKING.XYZ
$ docker-compose exec workstation1 /install-heimdal/bin/kinit -C \
    FILE:/home/luser/.hcp/pkinit/user-luser-key.pem luser \
    /install-heimdal/bin/klist
Credentials cache: FILE:/tmp/krb5cc_n6pEWh
        Principal: luser@HCPHACKING.XYZ

  Issued                Expires               Principal
Nov 25 19:48:25 2024  Nov 25 19:53:25 2024  krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ
```

## `kdcsvc`

### The kdcsvc API, and `/hcp/python/HcpApiKdc.py`

The KDC Service runs a `webapi` instance whose interface is derived from the command-line interface of the kadmin tool. It supports the following actions on the KDC database; `add`, `add_ns`, `get`, `del`, `del_ns`, and `ext_keytab`. These allow it to (respectively) add new regular principals, add new namespace principals, query principals, delete regular principals, delete namespace principals, and extract keytabs for service principals. This service should always be run with HTTPS. As with all webapi-hosted apps, it supports client-authentication options `clientcert` and `kerberos`. The service will allow any and all commands if a valid client certificate was used, as this is used to infer administrative privilege. If instead the client is kerberos-authenticated, the service will only support the `ext_keytab` command and will only allow the user's own principal to be exported to a keytab.

Note, in the HCP workflow and the reference usecase, the presence of the KDC service is to show how it can operate statelessly, where _all_ principals are derived on-the-fly based on certificates. In this mode of operation, there should be no need to manipulate the KDC database, but the ability to do so supports hybrid scenarios and/or helps when migrating a legacy database over to stateless usage. The KDC's database can register and use (and replicate) conventional principals, even if the reference usecase only makes use of the new, dynamically-generated kinds of principals.

To help with the use of the KDC web API, the `/hcp/python/HcpApiKdc.py` library and tool can be used. The earlier section on namespace principals shows an example usage - one can get further usage information about how to invoke the tool by adding a `--help` argument. (For importing it into other python code, the easiest reference is to read the code itself.)

### kdcsvc replication

As the reference usecase demonstrates, it is possible to run both primary (a.k.a. "authoratative" or "master") and secondary (a.k.a. "non-authoratative" or "slave") KDCs, with replication between them. This is done in the reference usecase simply to demonstrate (and test) the capabilities, even though the reference usecase doesn't register any of its principals with the KDC (and so the replication doesn't ever need to wake up - it can be tested by manual/ad-hoc modifications to the primary and checking that they replicate to the secondaries).

When a primary KDC is configured, it is automatically set up to run the `ipropd-master` service to provide a replication source, and the list of allowed secondaries must be configured up-front. When a secondary KDC is configured, it is automatically set up to run the `ipropd-slave` server to provide a replication sink and pull database updates from the primary.

```
$ cat usecase/hosts/kdc_primary.json | grep secondaries
        "kdcsvc_secondaries": [ "secondary.kdc.hcphacking.xyz" ],
$ cat usecase/hosts/kdc_secondary.json | grep primary
        "kdcsvc_primary": "primary.kdc.hcphacking.xyz",
```

### primary versus secondary

The presence of multiple (primary and secondary) KDC services poses the question of which should be used for which kinds of operations. Clearly any requirement to modify the KDC database must be directed to the primary. However other APIs (queries with `get`, keytab extraction with `ext_keytab`) can be directed at either, unless access restrictions are used at the networking or authentication layers to decide the matter.

The key run-time usage of KDCs is in the issuance of TGTs and service-tickets, which is typically controlled by the `krb5.conf` file used by Kerberos tools and libraries. The reference usecase generates krb5.conf files in the Enrollment service and distributes + installs them via attestation, and all KDC usage is directed to the secondary with the exception of the KDCs themselves, which are both configured to use the primary as authoratative.
