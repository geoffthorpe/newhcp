# Host Cryptographic Provisioning (HCP)

There's a lot to unpack, as people may be coming to this project for multiple
different reasons and I need to structure things so that each of them can find
what they're looking for.

* **[Quick reference](#quick-reference)** for building and running
* **[What](doc/HCP-what-it-is.md)** it is and what it does
* **[Why](doc/HCP-why-it-exists.md)** it exists and works the way it does
* **[How](doc/HCP-how-it-works.md)** it works

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

### Teardown all running containers

```
docker-compose down -v
```
