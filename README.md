# NewHCP

The structure of this README is as follows;

* **[Quick reference](#quick-reference)** for building and running
* **[What](#what-it-is-and-what-it-does)** it is and what it does

---

## Quick reference

### Host system dependencies

```
sudo apt-get install -y docker-compose openssl heimdal-clients
```

### Clone and build

```
git clone https://github.com/geoffthorpe/newhcp
git submodule update --init
make
```

### Run the example workflow (test)

```
# The docker-compose stuff depends on TOP being set
export TOP=$(pwd)

# Run the test, which will clean up after itself, with quiet output
Q=1 ./test.sh

# Run the test, with verbose output, and leave all the containers
# running, in order to allow manual interaction.
V=1 NOTRAP=1 ./test.sh
```

### Examining host container state

```
# Show the health status of the containers
docker-compose ps

# Show (+follow) the enrollment and attestation service containers
docker-compose logs -f enrollsvc attestsvc

# Get a root shell on the secondary KDC
docker-compose exec kdc_secondary bash
```

### Step 1 of 2: get a Kerberos-authenticated shell

To get a TGT explicitly (as root, using alicia's certificate);

```
docker-compose exec alicia /launcher bash
root@alicia:/# kinit -C FILE:/assets/pkinit-client-alicia.pem \
                     alicia bash
root@alicia:/# klist
Credentials cache: FILE:/tmp/krb5cc_yorGFK
        Principal: alicia@HCPHACKING.XYZ

  Issued                Expires               Principal
Aug 19 17:26:57 2025  Aug 19 17:31:57 2025  krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ
```

To get a TGT implicitly (as alicia, 'kinit' runs automatically);

```
docker-compose exec alicia /launcher bash
root@alicia:/# su -w HCP_CONFIG_MUTATE - alicia
alicia@alicia:~$ klist
Credentials cache: FILE:/tmp/krb5cc_yorGFK
        Principal: alicia@HCPHACKING.XYZ

  Issued                Expires               Principal
Aug 19 17:26:57 2025  Aug 19 17:31:57 2025  krbtgt/HCPHACKING.XYZ@HCPHACKING.XYZ
```

### Step 2 of 2: ssh

As root;

```
root@alicia:/# ssh -l alicia shell.hcphacking.xyz
alicia@shell:~$
```

As alicia;

```
alicia@alicia:~$ ssh shell.hcphacking.xyz
alicia@shell:~$
```

### Teardown all running containers

```
docker-compose down -v
```

---

## What it is and what it does

### HCP (Host Cryptographic Provisioning)

Reference implementation of a TPM-enrollment-based attestation framework for
provisioning hosts with secret and non-secret assets. Here is a diagram
overview of HCP's reference usecase;

![HCP overview diagram](doc/HCP.drawio.svg)

### Software TPM service

Consumes TPM state created by the `orchestrator` tool. Can be instantiated as a
side-car container (using a shared-mount for host communication - no
networking) or as a cotenant service within the host container.

### **[Stateless KDC (Kerberos Domain Controller) service](doc/stateless-kdc.md)**

Demonstrates how PKI-based identity can underpin a Kerberos network, because
none of the service or client (role/user) identities in the reference usecase
are registered with the KDC, instead their Kerberos credentials are obtained
from X509v3 certificates containing their authorized identity. Think of it as
"stateless, certificate-based Kerberos".
[Click here for more detail.](doc/stateless-kdc.md)

* namespace principals (service credentials)
* synthetic principals (client credentials)
* `kdcsvc` (kadmin API, replication, ...)

### Stateless SSH (sshd) service

A cotenant service that allows a host's user accounts to become ssh-accessible
using Kerberos (GSS-API) authentication. Together with the Stateless KDC
service, this shows an end-to-end SSO solution running on top of an
HCP-bootstrapped network.

### WebAPI service

A web-API-hosting service (based on uwsgi) for representing Flask applications
and, if enabled, providing a HTTPS reverse-proxy (based on nginx) using TLS
certificates obtained from TPM enrollment. This service runs co-tenant inside
all the other services that provide web APIs (we dogfood webapi extensively).

### **[Tooling](doc/tooling.md)**

* Workload launcher, for defining and running workloads, consisting of services
  and dependencies. This consumes a basic JSON description of what has to be
  setup and started and runs like a container init daemon.
* JSON manipulations, for path handling (`gson.path`), recursive unions
  (`gson.union`), parameter expansion (`gson.expander`), and programmatic
  manipulation (`gson.mutater`), etc.
* Extensible workflow, for building and running.
