# Host Cryptographic Provisioning (HCP)

---

## What it is

The HCP software has been and is the vehicle for multiple conveniences, so it is probably useful to identify which of them are of interest, and to recognize enough about the things that aren't of interest for them to not interfere in your understanding and use of HCP.

* Extensible workflow for building inter-dependent docker images through programmatic use of GNU Make. Eg. this allows the compiling and installing of heimdal to be integrated into the container building workflow, deals with multiple tags (distro versions) in parallel, and even allows cross-tag dependencies to be expressed (at the time of writing, it was necessary to build the development head of Heimdal with a different OS version than the one it is subsequently installed into).

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
