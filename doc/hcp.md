# HCP (Host Cryptographic Provisioning)

HCP provides two complementary functions to an infrastructure provider;

* TPM-based host attestation,
* Furnishing attested hosts with secret (and nonsecret) assets.

## Table of contents

* [Step by step](#step-by-step)
* [Enrollment service](#enrollment-service) (`emgmt`, `erepl`)
* [Attestation service](#attestation-service) (`arepl`, `ahcp`)
* [Enrollment client](#enrollment-client) (`orchestrator`)
* [Attestation client](#attestation-client) (`aclient`)

---

## Step by step

The following diagram shows the HCP's reference usecase and most of its components;

![HCP overview diagram](hcp-overview.svg)

1. A new host and its TPM are enrolled with the Enrollment service, generally by automated logic in the infrastructure. This is represented by the `orchestrator` host in the reference usecase, which consumes a JSON description of the fleet called [fleet.json](../usecase/config/fleet.json).
```
$ docker-compose up -d emgmt_pol emgmt erepl arepl ahcp aclient_tpm
$ docker-compose run orchestrator
Processing entry: aclient (doesn't exist)
Processing entry: kdc_primary (doesn't exist)
Processing entry: kdc_secondary (doesn't exist)
Processing entry: workstation1 (doesn't exist)
Processing entry: sherver (doesn't exist)
Processing entry: bigbrother (doesn't exist)
Processing entry: www (doesn't exist)
$ docker-compose run orchestrator -c -e aclient
Processing entry: aclient (doesn't exist)
    create: TPM created successfully
    enroll: TPM enrolled successfully
$ docker-compose run orchestrator
Processing entry: aclient (exists, enrolled)
Processing entry: kdc_primary (doesn't exist)
Processing entry: kdc_secondary (doesn't exist)
Processing entry: workstation1 (doesn't exist)
Processing entry: sherver (doesn't exist)
Processing entry: bigbrother (doesn't exist)
Processing entry: www (doesn't exist)
```

2. The host+TPM enrollment is created within the Enrollment service's database and is periodically refreshed to ensure that enrolled credentials are fresh (unexpired).

3. The Attestation service instance (of which there may be many) replicates the enrollment database from the Enrollment service. The replication continues over time and survives network glitches, outages, etc.

4. The host contacts the Attestation service and uses its TPM to attest to its current state. If the TPM is recognized in the Attestation service's (replicated clone of the) enrollment data, and the state it attests to is accepted, then the corresponding set of assets is wrapped and returned to the host.

5. If the attestation was successful and assets have been returned, any sealed (secret) assets are unsealed, then the canonical attestation callback (overridable) is called to examine the returned assets and perform any necessary post-processing. I.e. install assets into the appropriate directories, signal any dependent apps ("HUP") to reload assets that might be expiring, etc. The following trace shows the reference usecase's `aclient` performing this sequence;
```
$ docker-compose run aclient
Creating newhcp_aclient_run ... done
Running 'attestclient'
Info, 'tpm2-attest attest' succeeded
Extracting the attestation result
./
./certissuer.pem
./certissuer.pem.sig
./clientprofile
./ek.pub
./ekpubhash
./enroll.conf
./hint-reenroll-20241118230151
./hint-reenroll-20241118230151.sig
./hostcert-default-https-hostclient-key.pem.enc
./hostcert-default-https-hostclient-key.pem.enc.sig
./hostcert-default-https-hostclient-key.pem.policy
./hostcert-default-https-hostclient-key.pem.symkeyenc
./hostcert-default-https-hostclient.pem
./hostcert-default-https-hostclient.pem.sig
./hostcert-user-https-client-barry-key.pem.enc
./hostcert-user-https-client-barry-key.pem.enc.sig
./hostcert-user-https-client-barry-key.pem.policy
./hostcert-user-https-client-barry-key.pem.symkeyenc
./hostcert-user-https-client-barry.pem
./hostcert-user-https-client-barry.pem.sig
./hostcert-user-pkinit-admin-alicia-key.pem.enc
./hostcert-user-pkinit-admin-alicia-key.pem.enc.sig
./hostcert-user-pkinit-admin-alicia-key.pem.policy
./hostcert-user-pkinit-admin-alicia-key.pem.symkeyenc
./hostcert-user-pkinit-admin-alicia.pem
./hostcert-user-pkinit-admin-alicia.pem.sig
./hostcert-user-pkinit-user-alicia-key.pem.enc
./hostcert-user-pkinit-user-alicia-key.pem.enc.sig
./hostcert-user-pkinit-user-alicia-key.pem.policy
./hostcert-user-pkinit-user-alicia-key.pem.symkeyenc
./hostcert-user-pkinit-user-alicia.pem
./hostcert-user-pkinit-user-alicia.pem.sig
./hostname
./hostname.sig
./krb5.conf
./krb5.conf.sig
./manifest
./manifest.sig
./meta-data
./meta-data.sig
./rootfs.key.enc
./rootfs.key.enc.sig
./rootfs.key.policy
./rootfs.key.symkeyenc
./signer.pem
./user-data
./user-data.sig
Signature-checking the received assets
Unsealing asset 'hostcert-default-https-hostclient-key.pem'
Unsealing asset 'hostcert-user-https-client-barry-key.pem'
Unsealing asset 'hostcert-user-pkinit-admin-alicia-key.pem'
Unsealing asset 'hostcert-user-pkinit-user-alicia-key.pem'
Unsealing asset 'rootfs.key'
Running callback '/hcp/tools/attest_callback_common.py'
Processing assets returned from attestation
Class: genconf-krb5
 - asset: krb5.conf (644) [changed]
 [preinstall]
 - install: krb5.conf,644
      dest: /etc/krb5.conf
 [postinstall]
Class: gencert-hxtool
 - asset: hostcert-user-pkinit-user-alicia.pem (644) [changed]
 - asset: hostcert-user-pkinit-user-alicia-key.pem (600) [changed]
 [preinstall]
 - install: hostcert-user-pkinit-user-alicia.pem,644
      dest: /home/alicia/.hcp/pkinit/user-alicia.pem
 - install: hostcert-user-pkinit-user-alicia-key.pem,600
      dest: /home/alicia/.hcp/pkinit/user-alicia-key.pem
 [postinstall]
 - asset: hostcert-default-https-hostclient.pem (644) [changed]
 - asset: hostcert-default-https-hostclient-key.pem (600) [changed]
 [preinstall]
 - install: hostcert-default-https-hostclient.pem,644
      dest: /etc/https-hostclient/aclient.hcphacking.xyz.pem
 - install: hostcert-default-https-hostclient-key.pem,600
      dest: /etc/https-hostclient/aclient.hcphacking.xyz-key.pem
 [postinstall]
 - asset: hostcert-user-https-client-barry.pem (644) [changed]
 - asset: hostcert-user-https-client-barry-key.pem (600) [changed]
 [preinstall]
 - install: hostcert-user-https-client-barry.pem,644
      dest: /etc/creds/unknown/barry/https/client-barry.pem
 - install: hostcert-user-https-client-barry-key.pem,600
      dest: /etc/creds/unknown/barry/https/client-barry-key.pem
 [postinstall]
 - asset: hostcert-user-pkinit-admin-alicia.pem (644) [changed]
 - asset: hostcert-user-pkinit-admin-alicia-key.pem (600) [changed]
 [preinstall]
 - install: hostcert-user-pkinit-admin-alicia.pem,644
      dest: /home/alicia/.hcp/pkinit/admin-alicia.pem
 - install: hostcert-user-pkinit-admin-alicia-key.pem,600
      dest: /home/alicia/.hcp/pkinit/admin-alicia-key.pem
 [postinstall]
Class: gencert-issuer
 - asset: certissuer.pem (644) [changed]
 [preinstall]
 - install: certissuer.pem,644
      dest: /usr/share/ca-certificates/aclient/certissuer.pem
 [postinstall]
Updating certificates in /etc/ssl/certs...
rehash: warning: skipping ca-certificates.crt, it does not contain exactly one certificate or CRL
1 added, 0 removed; done.
Running hooks in /etc/ca-certificates/update.d...
done.
Class: genkrb5keytab
Completion touchfile: null
```

As can be seen from this example, user credentials on the given host are automatically installed into that user's directory. The same is true for service credentials, which can be stored in a global `/etc` path, or in a more constrained, workload-specific path of `/etc/hcp/<workload>` if preferred.

---

## Enrollment service

This service is where cryptographic assets get produced for the enrolled hosts. The enrollment takes the form of a JSON request object. The `orchestrator` tool constructs the enrollment request using details from the `fleet.json` configuration, which is then passed through `preclient` and `postclient` filters defined in the Enrollment service's [configuration](../usecase/hosts/emgmt.json).

### Use of a policy service

If a policy service is configured for the Enrollment service, the processed JSON request is sent to the policy service for adjudication, otherwise the operation is assumed acceptable. The Enrollment service is presumed accessible only to trusted infrastructure, so the use of a policy service hook may be surplus to requirements, especially if the Enrollment service is configured to allow little or no flexibility in client requests.

### Keeping enrollment assets fresh with `reenroller`

The enrollment service also provides a background `reenroller` agent, whose job it is to determine the enrollments that are due for reenrollment and causes them to reenroll. This has the affect of updating assets that are too close to their expiry times.

### The API and credential-generation with `emgmt`

The `emgmt` container is the one that provides the Enrollment service API (a flask app running over HTTPS requiring client certificate authentication), which trusted infrastructure uses to enroll/unenroll hosts and their TPMs. This is also the container that has write access to the enrollment database and possesses the secrets and/or access for credential-creation. (Internal to the container, privilege-separation is used to insulate the enrollment API from the credential-generation process.)

### Replication with `erepl`

The `erepl` container has read-only access to the enrollment database and provides a replication daemon to allow that database to be replicated to Attestation service instances. The current reference implementation uses a git repo to hold the enrollment database, meaning that standard git replication (`git-daemon`, `git clone`, etc) is used.

### HCP can't bootstrap itself

One achievement of HCP is that it provides an attestation-based delivery vehicle for PKI - that is, it provides a way to control generation of service and client credentials on a host-by-host basis, and a way to control (via attestation) their distribution to the intended hosts. The reference usecase demonstrates this by having all the credentials (and even some of the configs) for KDCs, SSH servers, and user/client workstations generated and distributed by HCP.

That said, who generates the credentials used by HCP itself? The assumption is that one cannot have "turtles all the way down", and so HCP depends on the external environment providing (and maintaining!) these seed credentials, on the assumption that maintaining a small set of core credentials for HCP is compensated for by the fact that HCP maintains a fleet's worth of credentials in return.

The reference usecase automatically generates this core set of credentials and automatically mounts them into HCP containers as appropriate;

| Host path                     | Mount path         | Usage                                     |
| ----------------------------- | ------------------ | ----------------------------------------- |
| \_testcreds/enrollcertissuer  | /enrollcertissuer  | CA with private key                       |
| \_testcreds/enrollcertchecker | /enrollcertchecker | CA without private key                    |
| \_testcreds/enrollsigner      | /enrollsigner      | Enrollment signature key-pair             |
| \_testcreds/enrollverifier    | /enrollverifier    | Enrollment signature public key           |
| \_testcreds/enrollserver      | /enrollserver      | `emgmt` HTTPS certificate and key         |
| \_testcreds/enrollclient      | /enrollclient      | `orchestrator` client certificate and key |

---

## Attestation service

Unlike the Enrollment service, the Attestation service is presumed to be widely deployed and accessible. If the Enrollment service goes down, enrollment and unenrollment is temporarily unavailable, whereas if the Attestation service goes down, attestation and retrieval of updated assets becomes unavailable. It is expected that the latter is far more mission-critical than the former, and that is why;

* The Attestation service is expected to be deployed and monitored for maximum reliabilty and availability.
* The Attestation service is unable to sign enrollment data, does not possess any credential-creation capability, etc.
* The Attestation service is unable to unseal any of the sealed assets it holds for (and distributes to) enrolled hosts.
* The Attestation API operates on a read-only copy of the enrollment data, by running in a separate container from the replication client that is responsible for updating the enrollment data.

### The API with `ahcp`

The `ahcp` container is the one that provides the Attestation service API, a flask app that runs over unencrypted HTTP (by default) and provides a target for fleet hosts to attest to their current state (using their TPM) and to retrieve their assets.

The default use of unencrypted HTTP is to alleviate the bootstrapping requirement that HTTPS imposes - after all, if HCP is being used to distribute trust-roots to hosts, it can't depend on trust-roots already being installed! The only trust-root that must be present on attesting hosts is the public key used by the Enrollment service to sign secret assets, and this can be delivered to the host at the same time as the attestation client. Further, any secrets contained in the enrollment data are already encrypted (sealed) to the relevant host's TPM, so there is inherent protection both against theft (the assets can't be unsealed by any other host) and against impersonation (the assets are signed by the Enrollment service). That said, the attestation service can use HTTPS if preferred, certainly if trust-roots are not maintained via HCP.

`ahcp` mounts the enrollment data read-only, to limit the effective risk of an exploit against the web service.

### Replication with `arepl`

The `arepl` container has writable access to the local "attestdb", which it updates by replicating from the `erepl` component of the Enrollment service. In fact, the Attestation service's "attestdb" consists of _two_ replicas of the enrollment database, which are updated and rotated (using symlinks) to ensure that an in-progress update in `arepl` cannot interfere with an ongoing attestation in `ahcp`. Put another way, once an attestation request to `ahcp` begins processing, it is guaranteed to see an unchanging copy of the attestation database, even if updates to the database are being replicated at the same time.

The backing store for the enrollment database is a git repository, and the native git transport is used for replication (à la `git-daemon`, `git pull`, etc). One characteristic of this is that updates (commits, merges, ...) are applied atomically to the replica, and the transport is robust and resilient to intermittent errors and outages.

---

## Enrollment client

### Using the API directly with `enroll_api.py`

The Enrollment service API has a corresponding python library+tool called [enroll\_api.py](../hcp/tools/enroll_api.py) that can be used to simplify HTTPS calls to the enrollment service. The expectation is that a network's orchestration tooling and workflow could be adapted to invoke these enroll/unenroll API calls at the appropriate moments, i.e. when a new host is being stood up and its TPM details are known with certitude (enroll), or when a host is to be decommissioned and attestation access should be denied (unenroll).

### Managing a fleet with `orchestrator`

The `orchestrator` container;

* uses the aforementioned `enroll_api.py` to interact with the Enrollment service to enroll and unenroll fleet hosts and their TPMs,
* uses a [fleet.json](../usecase/config/fleet.json) configuration file that defines all such fleet hosts (and the requested set of enrolled assets for each), and
* is able to create and delete software TPM state for those hosts that use them (and that are mounted).

### Managing software TPMs with `orchestrator`

The reference usecase has multiple fleet hosts using software TPMs, all of which are created and destroyed via the `orchestrator` tool. This needn't be the case, but works well for the development workflow because it is portable. Testing has also shown that `orchestrator` can enroll and unenroll TPMs that it does not manage (the `ek.pub` file must be provided), and those TPMs can also be used directly with `aclient` to successfully attest and unseal assets.

As can be seen from the following excerpt of [`docker-compose.yml`](../docker-compose.yml), `orchestrator` can only manage software TPMs that are mounted at their expected paths;

```
    orchestrator:
        extends: common
        hostname: orchestrator.hcphacking.xyz
        networks:
          - hcpnetwork
        volumes:
          - ./_testcreds/enrollcertchecker:/enrollcertchecker:ro
          - ./_testcreds/enrollclient:/enrollclient:ro
          - tpm_aclient:/tpm_aclient
          - tpm_kdc_primary:/tpm_primary.kdc
          - tpm_kdc_secondary:/tpm_secondary.kdc
          - tpm_sherver:/tpm_sherver
          - tpm_workstation1:/tpm_workstation1
          - tpm_bigbrother:/tpm_bigbrother
          - tpm_www:/tpm_www
        environment:
          - HCP_CONFIG_FILE=/usecase/hosts/orchestrator.json
```

---

## Attestation client

All of the fleet hosts in the reference usecase;

* have software TPMs,
* execute `/hcp/tools/run_client.sh` on start-up to attest and receive assets,
* run the `attester` service to periodically re-run `run_client.sh`.

As such, the `aclient` container is really just a short-lived subset of what all the other fleet hosts do. It simply runs `/hcp/tools/run_client.sh` once, and then exits.

### Identifying the TPM

The `run_client.sh` attestation script uses the TCG's tpm2-tools library and mechanisms to interface with a TPM, and this is no less true when it is interacting with our very own Software TPM service. As can be seen from the following default config for `run_client.sh` ([proto/client.json](../usecase/proto/client.json)), the `tcti` indicates the transport (`"swtpm"`) and location (`/tpmsocket_{id}/tpm`) of the TPM (here `{id}` is substituted with the hostname). `run_client.sh` takes that value and sets the TPM2TOOLS\_TCTI environment variable to it, which is how the TCG's canonical TPM stack identifies the TPM.
```
{
    "exec": "/hcp/tools/run_client.sh",
    "tag": "{client_tag}",
    "attest_url": "{client_url}",
    "tcti": "swtpm:path=/tpmsocket_{id}/tpm",
    "enroll_CA": "{client_CA}",
    "callbacks": [ "/hcp/tools/attest_callback_common.py" ],
    "global": "{client_global}"
}
```

The following excerpt of [docker-compose.yml](../docker-compose.yml) shows how `aclient`'s TPM is mounted at the expected location for `aclient` and its TPM side-car, `aclient_tpm`;

```
    aclient:
        extends: common
        hostname: aclient.hcphacking.xyz
        networks:
          - hcpnetwork
        volumes:
          - tpmsocket_aclient:/tpmsocket_aclient
          - ./_testcreds/enrollverifier:/enrollverifier:ro
        environment:
          - HCP_CONFIG_FILE=/usecase/hosts/aclient.json

    aclient_tpm:
        extends: common_tpm
        hostname: aclient_tpm.hcphacking.xyz
        volumes:
          - tpm_aclient:/tpm_aclient
          - tpmsocket_aclient:/tpmsocket_aclient
        environment:
          - HCP_CONFIG_FILE=/usecase/hosts/aclient.json
```

### Running the TPM side-car

As can be seen from the last excerpt, the "TPM" that `aclient` sees is actually a unix domain socket sitting in a (very small) docker volume, `tpmsocket_aclient`, whose sole purpose is to house that socket as an IPC channel between the `aclient` and `aclient_tpm` containers. The latter (the software TPM) has the same volume mounted for the same reason, but it also has the volume holding the _actual_ TPM state, `tpm_aclient` (i.e. without the "`socket"`). NB: the only other container that mounts `tpm_aclient` is `orchestrator`, as it is responsible for creating and destroying TPM state.

The TPM side-car `aclient_tpm`, like all other TPM side-cars, is cut off from all networking and runs nothing but the `swtpm` daemon;

```
$ docker-compose exec aclient_tpm ps axf
    PID TTY      STAT   TIME COMMAND
  30629 pts/0    Rs+    0:00 ps axf
      1 ?        Ss     0:24 /sbin/docker-init -- /hcp/common/launcher.py
      7 ?        S      0:18 /usr/bin/python3 /hcp/common/launcher.py
     36 ?        S      0:00  \_ /usr/bin/python3 /hcp/swtpm.py
     37 ?        S      0:34      \_ swtpm socket --tpm2 --tpmstate dir=/tpm_acl
```
