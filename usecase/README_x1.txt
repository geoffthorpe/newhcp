The x1 usecase is used to test the long-term behavior of namespace principals.
It does this by:
- Not using the HCP core services (no policy, emgmt, erepl, arepl, ..., no TPMs)
- Setting up a KDC (x1_kdc) with a 10year 'pkinit-kdc' certificate.
  - Runs x1.kdc.extkeytab.sh in the background, which, every 15 seconds:
    - Publishes (on backdoor volume) a keytab for an sshd namespace principal.
    - Displays the keytab to console, showing the currently active versions.
- Starting an SSH service (x1_sshd) using the backdoor-published keytab.
- Setting up a client (x1_client) with a 10year 'pkinit-client' certificate.
- The client runs x1.client.sh, an infinite loop until failure, in which it:
  - Obtains a Kerberos ticket (SSO) using the pkinit-client cert.
  - Connects to x1_sshd using SSO.
  - Echoes "success" back through the SSH tunnel to the console.
  - Exits if that went wrong.
  - Sleeps for 10 seconds.
- Running (forever) a logging client to pick up the output of the containers.

It is defined by:
- docker-compose.yml, the definitions with 'x1_' prefix
- usecase/test_x1.sh, which runs forever
