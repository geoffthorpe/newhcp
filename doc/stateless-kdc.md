# Stateless KDC service

This service takes advantage of two powerful new features in the Heimdal kerberos implementation, namely namespace principals and synthetic principals. The result is that service and client/role principals do not need to be known and registered in the KDC database, and so the service is "stateless" in that sense. Instead, users and service owners are provisioned with X509v3 certificates (either from HCP itself or through whatever other PKI tooling is used for managing and distributing certificates) that have the desired principals encoded within them. If the KDC accepts the certificate as valid, then it can issue a TGT (for client/role principals) or keytab (for service principals) for the principal in that certificate, even if those principals haven't previously been registered.

## Namespace principals

This feature implements a kind of "wildcard" service principal, such that all principals within the "namespace" can be deterministically generated, as can the corresponding keys at an arbitrary point in time (key-rotation is important).

The reference usecase uses two namespace principals, as can be seen in the following output;

```
$ echo "list *" | docker-compose exec -T kdc_primary /install-heimdal/bin/kadmin -l -H /kdc_primary/var/heimdal.db
default@HCPHACKING.XYZ
kadmin/admin@HCPHACKING.XYZ
kadmin/hprop@HCPHACKING.XYZ
kadmin/changepw@HCPHACKING.XYZ
changepw/kerberos@HCPHACKING.XYZ
WELLKNOWN/ANONYMOUS@HCPHACKING.XYZ
WELLKNOWN/FEDERATED@HCPHACKING.XYZ
krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ
WELLKNOWN/org.h5l.fast-cookie@WELLKNOWN:ORG.H5L
WELLKNOWN/HOSTBASED-NAMESPACE/_/hcphacking.xyz@HCPHACKING.XYZ
WELLKNOWN/HOSTBASED-NAMESPACE/host/hcphacking.xyz@HCPHACKING.XYZ
```

The last two entries are the namespace principals, the latter of the two (with the "host" service identifier rather than "\_") exists for SSH services, because that namespace principal is configured to allow delegation. All other service principals matching the network address `<something>.hcphacking.xyz` in the realm `HCPHACKING.XYZ` are derived from the former of the two namespace principals.

Note, there are two ways for services to obtain (and update) their service principals. In the reference usecase, the enrollment (and periodic reenrollment) of the service host causes a keytab to be generated as a secret (sealed) asset, so the `sherver` SSH host (for example) gets its kerberos keytab via attestation. However, the service host could obtain its keytab directly from the KDC (which is what the Enrollment service does on its behalf when getting keytabs via enrollment).

## Synthetic principals

Synthetic principals are simpler than namespace principals because they (only) concern client/role principals and do not need to be derived from a base principal. A KDC can issue a TGT for any client/role principal at all. The feature is enabled in the KDC's configuration file, under the HDB section;

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

## `kdcsvc` (API, replication, ...)


