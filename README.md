# Host Cryptographic Provisioning (HCP)

There's a lot to unpack, as people may be coming to this project for multiple
different reasons and I need to structure things so that each of them can find
what they're looking for.

* **[Quick reference](#quick-reference)** reference for building and running
* **[What](#what-it-is)** it is and what it does
* **[Why](#why-it-exists)** it exists and works the way it does
* **[How](#how-it-does-what-it-does)** it does what it does

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
# Run the test, which will clean up after itself, with quiet output
Q=1 ./test.sh

# Run the test, with verbose output, and leave all the host containers
# running, in order to allow manual interaction.
V=1 NOTRAP=1 ./test.sh
```

### Examining host container state

```
# Show the health status of the containers
docker-compose ps

# Show (+follow) the enrollment and attestation service containers
docker-compose logs -f emgmt erepl arepl ahcp

# Get a root shell on the secondary KDC
docker-compose exec kdc_secondary bash
```

### Step 1 of 2: get a Kerberos-authenticated shell

```
docker-compose exec workstation1 bash
root@workstation1:/# su - luser
luser@workstation1:~$ kinit \
    -C FILE:/home/luser/.hcp/pkinit/user-luser-key.pem luser bash
luser@workstation1:~$ echo $KRB5CCNAME 
FILE:/tmp/krb5cc_zJ0xtC
```

### Step 2 of 2: ssh

```
luser@workstation1:~$ ssh -p 2222 sherver.hcphacking.xyz
luser@sherver:~$
```

---

## What it is

The HCP software has been and is the vehicle for multiple conveniences, so it is probably useful to identify which of them are of interest, and to recognize enough about the things that aren't of interest for them to not interfere in your understanding and use of HCP.

* Extensible workflow for building inter-dependent docker images through programmatic use of GNU Make. Eg. with HCP this allows the host-building of heimdal to be integrated into the flow of container building, deals with multiple tags (distro versions) in parallel, and even allows cross-tag dependencies to be expressed (at the time of writing, it was necessary to build the development head of Heimdal in a different OS version to the one it is installed into).

* TPM enrollment service (container), such that each enrollment is a TPM-sealed set of assets (keys, configs, ...) that gets periodically refreshed. This consists of "emgmt", which has read-write access to the enrollment database and exposes the enrollment API, and "erepl", which has read-only access to the enrollment database and supports replication to attestation service instances.

* TPM attestation service (container), that uses the enrollment service as its source of truth. Successfully-attested clients receive their assets that are subsequently unsealed within their respective TPMs. This consists of "arepl", which has read-write access to a replica of the enrollment database that it pulls (from "erepl"), and "ahcp", which has read-only access to the replica and provides the attestation API to otherwise-untrusted hosts on the network.

* Software TPM service (co-tenant or container), a side-car TPM emulation. Unsurprisingly it is used rather heavily for automated test-cases, but it can be a viable production stub for hosts without any other source of TPM. Eg. in order to unify a secrets-provisioning workflow, and avoid having different processes for machines with TPMs vs those without. (Cloud providers increasingly offer similar TPM-as-a-service features with their VM products. Naturally they provide extremely similar behavior to this one.)

* Enrollment client, as a reference example of how to interact with the enrollment service API. This is available as reusable python code, as well as a container wrapper called "orchestrator". This represents that part of the infrastructure that creates and/or registers new hosts for them to have identity and credentials.

* Attestation client, uses an associated TPM and interacts with the attestation service, includes a default implementation for handling the enrollment assets that are received (installing them, triggering asset-change hooks, etc). Optional: a background "attester" service that triggers re-attestation periodally. This is provided as code that can work on platforms with any compliant TPMs (including appropriately-enabled cloud VMs, as well as our own software TPM service), and is also runnable as a container wrapper called "aclient".

* A novel Kerberos Domain Controller (KDC) service, with corresponding support in the TPM enrollment service. The KDC host uses a TPM to attest during start-up, and in return gets its credentials and configuration (via attestation). Heimdal's support for "synthetic" (role) and "namespace" (service) principals allows credentials to be obtained from the KDC via PKI, by using identities encoded in X509v3 certificates, to avoid the classic Kerberos problem of maintaining user and service databases. (Or rather, punting the orchestration problem from Kerberos, where maintaining state and business logic is a classical corporate IT hassle, to PKI, which is often more palatable and/or already a solved problem.) Think of it as "stateless, certificate-based Kerberos". This service supports running as primary and/or secondary, and supports resilient replication between them.

* A Kerberos-based (SSO) `ssh` service. As with the KDC, this service uses a TPM to get its credentials and configuration (via attestation).

* A web-API-hosting service (based on uwsgi) for representing Flask applications and, if enabled, providing a HTTPS reverse-proxy (based on nginx) using TLS certificates obtained from TPM enrollment. This service runs co-tenant inside all the other services that provide web APIs (as dog-food, so to speak).

* A JSON-based policy-enforcement service. A JSON configuration document defines all the policy rules (iptables-like) for examining input payloads (which are also JSON), which then returns success or failure accordingly. The TPM enrollment service and the KDC's https-based API both implement hooks to support using the policy service, and the example workflow shows them in use. Ie. the application service represents its client's request as a JSON document and submits that to the associated policy service for approval/rejection. This allows for an architecture to have some separation between what it enables (the application service) and what constraints it imposes (codified in the policy service).

* A workflow that initializes an example (docker) network of containers, representing all of the above elements, and through which the automated tests are run. Ad-hoc interactions are also possible. (Eg. one can simply instruct the test script not to tear down the network once the test has completed - after which, the developer can interact with all the elements on the network.)

---

## Why it exists

### Use of TPM2

The TPM2 standard allows for some very powerful use-cases, not least of which is the ability to embed a policy when encrypting an asset to a given TPM, knowing that the TPM will adhere to that policy when decrypting the asset. Examples include: disallowing the unsealing of the asset unless certain conditions have been met (such as the prior presence of other assets), or insisting that an unsealed private key never leave the confines of the TPM. TPMs are the basis for (nearly) all modern implementations of secure boot and host attestation.

### Requirements

The genesis of HCP was the need to find an attestation system that would;

1. easily integrate with an existing host orchestration system and workflow, ie. such that existing host-creation workflows can easily be adapted to "enroll" a new host's TPM and create a trusted binding between that TPM and the host's FQDN.

2. use remote attestation at run-time as a means for hosts to receive assets.

3. have an extensible framework for generating (and periodically updating) host assets within an "enrollment service".

4. have a clear security separation between;
   
   1. the "attestation service", which must be highly-available for access by arbitrary and as-yet-untrusted hosts, and therefore should possess none of the capabilities of the "enrollment service", and
   
   2. the "enrollment service", which must possess the necessary permissions and/or credentials to create host assets, and therefore should only be accessible by suitably-trusted infrastructure.

5. allow the remote attestation and asset-provisioning capabilities to be used even with hosts that don't possess TPMs.

6. allow attestation-based provisioning to bootstrap network services in a "zero-conf"-like manner.

### Enrollment service

This service manages an authoritative enrollment database that associates TPMs with hostnames and an arbitrary set of assets, cryptographic and otherwise. (These assets are created during the enrollment phase, but can also be recreated periodically). It also provides a replication service, which is how the enrollment database finds its way to the attestation service in order for hosts to be able to retrieve their assets.

The 'emgmt' part of the enrollment service is where enrollment actually happens, and it's where the enrollment API is served, so this is also the component that has write access to the authoritative database. Internally, privilege separation is used between (a) the web server handling of API requests and (b) the actual creation of assets and manipulation of the database that occurs as a result of API requests.

The data stored in the enrollment database is itself robust, in that an attacker obtaining access to the enrollment database cannot decrypt any of the secrets contained within. They're all sealed/encrypted to the associated TPM (and optionally, also to an escrow key, used by the infrastructure owner for break-glass purposes). That said, a compromise of the enrollment database could allow a compromised host to retrieve its assets without going through the attestation, which is another good reason to recommend the use of credential-refresh (re-attestation) and short expiry times.

### Attestation service

This service provides an attestation API to hosts. If the host's attestation (request) is successful, the current enrollment data associated with that TPM is returned to the host, which can be loaded and used through their TPM. The attestation interaction can optionally be encrypted (HTTPS), assuming that you do not wish HCP attestation to provision the host's trust roots. (A chicken and egg problem.) Otherwise, choosing HTTP to bootstrap is defensible, given that all the secrets within the returned enrollment data are encrypted to the legitimate TPM.

The 'arepl' part of the attestation service takes care of creating and updating a local replica of the enrollment database. It therefore has write access to the replica.

The 'ahcp' part of the attestation service is where attestation actually happens, so this is the component that has only read access to the replica.

### Enrollment client

TBD

### Attestation client

TBD

### Software TPM service

TBD

### KDC service

TBD

### SSH service

TBD

### Policy service

TBD

---

## How it does what it does

### Enrollment service

The administrator can configure all relevant aspects of this container, including;

- filesystem path to the persistent storage that should hold the database

- all parameters governing the exported webapi (TLS certificates and trust roots, host address and port, etc)

- a JSON document representing the default/initial enrollment configuration for incoming enrollment requests. Any configuration in the client's JSON request can override this default. If all enrollment requests should get the same treatment, then this document can specify that, meaning that little or no configuration is required on the enrollment client side (infrastructure orchestration).

- another JSON document representing enforced enrollment configuration for enrollment requests. Any configuration in this document will override settings in the default/initial configuration and/or the client's request.

- an optional policy URL, indicating whether or not a policy service should be consulted on all enrollment API requests, and indicating the address of that policy service.

The enrollment database is structured as a git repository, and uses the associated git-daemon mechanism for replication. (Ie. the attestation service clones the enrollment database and uses git fetch/merge to pull updates.)

### TBD
