The default usecase is used for automated testing, and is defined by:
- docker-compose.yml, the initial definitions that have no prefix
- usecase/test.sh, which runs to test completion

The usecase consists of:
- Core:
  - Policy service (policy)
  - Enrollment service (emgmt, erepl)
  - Attestation service (arepl)
  - Orchestrator tool (orchestrator)
  - Attestation client (attestclient)
- KDC:
  - Kerberos service (kdc_primary, kdc_secondary, kdc_keytab)
- Fleet:
  - SSH service (ssherver1, ssherver2)
  - Utility hosts (workstation1, bigbrother, www)
- SWTPM service (*_tpm, and internal to bigbrother)

Characteristics:
- The KDC cannot run until its own TPMs are enrolled.
- The KDC must be running before other TPMs can be enrolled.
