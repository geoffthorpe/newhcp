# Host Cryptographic Provisioning (HCP)

---

## How it works

### Enrollment service

The administrator can configure all relevant aspects of this container, including;

- filesystem path to the persistent storage that should hold the database

- all parameters governing the exported webapi (TLS certificates and trust roots, host address and port, etc)

- a JSON document representing the default/initial enrollment configuration for incoming enrollment requests. Any configuration in the client's JSON request can override this default. If all enrollment requests should get the same treatment, then this document can specify that, meaning that little or no configuration is required on the enrollment client side (infrastructure orchestration).

- another JSON document representing enforced enrollment configuration for enrollment requests. Any configuration in this document will override settings in the default/initial configuration and/or the client's request.

- an optional policy URL, indicating whether or not a policy service should be consulted on all enrollment API requests, and indicating the address of that policy service.

The enrollment database is structured as a git repository, and uses the associated git-daemon mechanism for replication. (Ie. the attestation service clones the enrollment database and uses git fetch/merge to pull updates.)

### TBD
