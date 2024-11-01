# Host Cryptographic Provisioning (HCP)

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

### Extensible workflow for build

A workflow was required for building docker images that could integrate with non-docker builds (ie. with dependencies and build stages that are performed without a Dockerfile). This includes the creation of artifacts for use in testing (eg. establishing a dummy PKI and associated credentials) and the custom building of Heimdal from source and subsequent installation into dependent container images.

### Workload launcher

This tool uses a JSON document input to describe a workload, including setup processing steps as well as run-time services, with controls of environment variables. This document is pointed to by the HCP_CONFIG_FILE environment variable on entry, and the bash (/hcp/common/hcp.sh) and python (/hcp/common/hcp_common.py) support libraries re-establishes this environment variable and provides an API for interrogating the JSON document. In other words, the JSON document can contain configuration not just for the workload launcher, but for consultation by any tools that are subsequently run in the container too - i.e. the JSON document can be used for all configuration requirements of the workload, including the workload-specific logic.

This tool is used by the reference usecase (test.sh) to run all services and tools.

### Enrollment service

This service manages an authoritative enrollment database that associates TPMs with hostnames and an arbitrary set of assets, cryptographic and otherwise. (These assets are created during the enrollment phase, but can also be recreated periodically). It also provides a replication service, which is how the enrollment database finds its way to the attestation service in order for hosts to be able to retrieve their assets.

The 'emgmt' part of the enrollment service is where enrollment actually happens, and it's where the enrollment API is served, so this is also the component that has write access to the authoritative database. Internally, privilege separation is used between (a) the web server handling of API requests and (b) the actual creation of assets and manipulation of the database that occurs as a result of API requests.

The data stored in the enrollment database is itself robust, in that an attacker obtaining access to the enrollment database cannot decrypt any of the secrets contained within. They're all sealed/encrypted to the associated TPM (and optionally, also to an escrow key, used by the infrastructure owner for break-glass purposes). That said, a compromise of the enrollment database could allow a compromised host to retrieve its assets without going through the attestation, which is another good reason to recommend the use of credential-refresh (re-attestation) and short expiry times.

### Attestation service

This service provides an attestation API to hosts. If the host's attestation (request) is successful, the current enrollment data associated with that TPM is returned to the host, which can be loaded and used through their TPM. The attestation interaction can optionally be encrypted (HTTPS), assuming that you do not wish HCP attestation to provision the host's trust roots. (A chicken and egg problem.) Otherwise, choosing HTTP to bootstrap is defensible, given that all the secrets within the returned enrollment data are encrypted to the legitimate TPM.

The 'arepl' part of the attestation service takes care of creating and updating a local replica of the enrollment database. It therefore has write access to the replica.

The 'ahcp' part of the attestation service is where attestation actually happens, so this is the component that has only read access to the replica.

### Enrollment client

The developer (for interactive, ad-hoc purposes) and the reference usecase (for automated testing) need to be interact with the Enrollment service API, so there is a python client (/hcp/tools/run_orchestrator.sh) for this purpose. Note, the client also supports creating and destroying software TPM instances, not just enrolling and unenrolling (and re-enrolling) them. This tool consumes a JSON configuration document, typically called "fleet.json", that describes;

- How (where) to connect to the Enrollment service.

- The set of hosts (and their TPMs) together with any non-default request details to be sent to the Enrollment service when enrolling.

- The use of variable substitution that is only evaluated on the server, after client and server request (JSON) documents have been combined. This allows for a maximum of templating and a minimum of hard-coded constants.

### Attestation client

The attestation client is a reference implementation of the HCP attestation protocol (inherited from [safeboot](https://trmm.net/Safeboot/)), together with a reference implementation of how to handle (decode, unseal, install) the assets that are received from the host. This is used by the HCP reference example to get (and automatically refresh) user, role, and service credentials and have them automatically installed within the host operating system, including (in the case of ssh keytab updates) hooks to reload services that should absorb the new credentials.

The "aclient" container (defined in docker-compose.yml for use by the reference usecase/test) is a wrapper around the attestation client, that has an associated software TPM side-car which is defined in the Enrollment client's "fleet.json".

### Software TPM service

A key requirement of HCP is that the enrollment+attestation framework be usable for fleet-wide asset-provisioning, *including those hosts that don't have TPMs*. The Software TPM service is built around the open-source 'swtpm' project and can be run as a co-tenant service (as the 'bigbrother' entity does in the reference usecase) or wrapped as a containerized side-car (as all the other TPM-enabled entities do in the reference usecase).

In order to follow a more real-world model, the software state for a software TPM instance is not created by the instance itself, instead the orchestrator tool (that communicates with the Enrollment service and represents that part of infrastructure that provisions new hosts) creates the TPM instance that the Software TPM service can operate on. I.e. it is easier for the orchestrator (who enrolls TPMs) to create those TPMs, and "inject" them into the host and TPM service, than it is for the orchestrator to "extract" the TPM details from a TPM service that created itself. It is also better security practice.

### KDC service

There are some good reasons for incorporating KDCs into the HCP project.

1. The HCP model assumes that once you have enrollment and attestation services available, all remaining hosts in the fleet should (in theory) be able to bootstrap by using attestation to retrieve all the assets it needs; secrets, configs, and any other personalization. Whether HCP users choose to go that far is another matter. For the reference usecase, we add network services that are themselves bootstrapped by TPM-based enrollment and attestation, where SSH, web, and Kerberos services are all good candidates.

2. Although the KDCs are themselves bootstrapped through enrollment and attestation, they can be a dependency for the enrollment of any and all hosts whose enrollments should include Kerberos credentials! The reference usecase (test) illustrates this by ensuring the KDCs are already enrolled, attested, and running before attempting to enroll the SSH service's TPM. Why? Because the assets created for the SSH enrollment include a (periodically refreshed) Kerberos keytab, which the enrollment service gets from the secondary KDC!

3. Heimdal implemented two extremely powerful features recently that HCP is quite good at illustrating. Namely, "synthetic" (role) principals and "namespace" (service) principals.

#### Stateless Kerberos

Mechanically, synthetic and namespace principals are quite different, because the handling of role and service principals is inherently different in Kerberos. But the essence of them both is that you no longer need the KDC to use or maintain a database of known principals, because the role or service will instead authenticate themselves to the KDC using an X509v3 certificate with their principals encoded within. The KDC is able to emit TGTs (for users/roles) and keytabs (for services) based on these certificates and their content, and do not need corroborating local state. This means that fleet orchestration need only concern itself with PKI, the KDCs can remain more or less stateless.

It so happens that HCP enrollment and attestation provides an elegant way to provision the KDC services for a network _and_ provision the Kerberos-dependent services and clients with their own credentials for using Kerberos, thus producing a segment of production infrastructure using HCP alone - one if its goals.

#### Zero-sign-on (ZSO)

This is a play on the concept of Single-sign-on (SSO), which is one of the core features/benefits of Kerberos (and the reason it underlies Microsoft's Active Directory technology and many others).

The "single sign on" idea (for example when logging into a corporate network with Windows) corresponds to authenticating oneself to a KDC and obtaining a TGT (Ticket-Granting Ticket) - all subsequent authentication on the network by that user/role can be performed automatically, by using the TGT to get "service tickets" from the KDCs to allow secure communication with any given target service. SSH facilitates this kind of authentication using GSSAPI (Generic Security Service API), which means an ssh client with a suitable TGT can automatically obtain a service ticket and connect, giving the appearance that no further login was required - hence "SSO".

The "zero sign on" idea extends this by assuming that the enrollment and attestation of hosts has been configured such that known/registered users of a machine will _already_ have fresh credentials in their accounts (the attestation client installs them) that can be used to obtain a TGT from a KDC without intervention. Meaning that even the "single sign on" step appears not to be necessary because it can be performed automatically. In reality, one presumably still needs to "login" to the machine in _some_ fashion before having access to the credentials, so the term is slightly tongue-in-cheek, but it does mean that the login is outside the scope of Kerberos tooling rather than inside it.

### SSH service

The SSH service was a natural candidate for a network service to illustrate, given the prevalence of its use and its obvious relevance for all questions of user and service credential orchestration. The aforementioned reasons for supplying a KDC service have already made clear how SSH is useful in that context. It is worth noting that the precise configuration of SSH (on client and server sides) for Kerberos-based SSO can be a non-trivial exercise, so the ability to stand up a working network fleet that includes such an SSH configuration can be of considerable interest to people trying to solve their own network orchestration problems.

### Policy service

The first idea for producing a policy service came from designing the Enrollment service. The key enrollment service observation is that;

- an enrollment "request" is represented as a JSON document that specifies everything that should be produced, and all the parameters required to produce it,

- this JSON document is constructed by overlay - an initial "preclient" document on the service-side describes a default enrollment request, it is then overlaid by the (possibly-empty) JSON document supplied in the client request, and that in turn will be overlaid by a "postclient" document on the service-side.

This is quite an effective way to build up an enablement story, as the composite JSON document allows for concise representation of defaults as well as being very flexible with specializations. However, this model is not so compelling from the perspective of how once can control "what the client might cause to happen".

The author wondered if it would be possible to express a flexible set of conditions using JSON itself, because if so, that would be a good way of filtering JSON documents because the conditionals and assignments would be expressible with native types and formatting. (I.e. the filtering rules and filtered data are written in the same language.) Nothing obvious was found though, so we wrote our own. As a consequence, the application service (enrollment, KDC, ...) can run its own policy service, forward its requests through that before operating on them, and then use the policy configuration as the mechanism to codify what makes a request acceptable or unacceptable. 

### WebAPI service

Almost all of the HCP services include web (i.e. HTTP(S)-served) APIs, and given the nature of HCP it was natural to assume that the configuration and credentials for the services should be produced by enrollment and attestation, hence the creation of the "webapi" service. It supports Python flask applications running within 'uwsgi', and if TLS/HTTPS is requested, an nginx reverse-proxy instance is stood up in front using HCP-provided credentials. We dog-food this for all the services that serve HTTP(S).
