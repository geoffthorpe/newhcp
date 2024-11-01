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

