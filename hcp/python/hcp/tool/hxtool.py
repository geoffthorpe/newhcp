#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import os
import sys
import subprocess
import argparse
import tempfile

if __name__ == '__main__':

    # Wrapper command, using argparse
    _desc = 'Replacement for Heimdal\'s hxtool'
    _epilog = """
    """
    _help_type = 'TBD'
    _help_generate_key = 'TBD'
    _help_key_bits = 'TBD'
    _help_lifetime = 'TBD'
    _help_ca_certificate = 'TBD'
    _help_certificate = 'TBD'
    _help_hostname = 'TBD'
    _help_subject = 'TBD'
    _help_email = 'TBD'
    _help_pk_init_principal = 'TBD'

    parser = argparse.ArgumentParser(description = _desc,
                                     epilog = _epilog)
    parser.add_argument('--type', required = False, help = _help_type)
    parser.add_argument('--generate-key', required = False, help = _help_generate_key)
    parser.add_argument('--key-bits', required = False, help = _help_key_bits)
    parser.add_argument('--lifetime', required = False, help = _help_lifetime)
    parser.add_argument('--ca-certificate', required = False, help = _help_ca_certificate)
    parser.add_argument('--certificate', required = False, help = _help_certificate)
    parser.add_argument('--hostname', required = False, help = _help_hostname)
    parser.add_argument('--subject', required = False, help = _help_subject)
    parser.add_argument('--email', required = False, help = _help_email)
    parser.add_argument('--pk-init-principal', required = False, help = _help_pk_init_principal)

    if sys.argv.pop(1) != 'issue-certificate':
    	sys.exit(1)
    args = parser.parse_args()

    if not args.certificate:
        raise Exception('pkinit-kdc requires --certificate')
    if not args.certificate.startswith('FILE:'):
        raise Exception('--certificate must start with FILE:')
    args.certificate = args.certificate[5:]
    if not args.ca_certificate:
        raise Exception('pkinit-kdc requires --ca-certificate')
    if not args.ca_certificate.startswith('FILE:'):
        raise Exception('--ca-certificate must start with FILE:')
    args.ca_certificate = args.ca_certificate[5:]
    if not args.lifetime:
        raise Exception('pkinit-kdc requires --lifetime')
    if not args.lifetime.endswith('d'):
        raise Exception('--lifetime must be in days')
    args.lifetime = int(args.lifetime[:-1])
    if not args.subject:
        raise Exception('pkinit-kdc requires --subject')

    if args.type == 'pkinit-kdc' or args.type == 'pkinit-client':
        if not args.pk_init_principal:
            raise Exception('pkinit-kdc requires --pk-init-principal')
        tmp = args.pk_init_principal.split('@')
        if len(tmp) < 2:
            raise Exception('--pk-init-principal must be <princ>@<realm>')
        realm = tmp.pop(len(tmp) - 1)
        princ = '@'.join(tmp)
        if args.type == 'pkinit-kdc' and princ != f"krbtgt/{realm}":
            raise Exception('--pk-init-principal must be krbtgt/<realm>@<realm>')
        if args.generate_key != 'rsa':
            raise Exception('pkinit-kdc requires --generate-key=rsa')
        if args.key_bits != '2048':
            raise Exception('pkinit-kdc requires --key-bits=2048')
        with tempfile.TemporaryDirectory() as tempdir:
            with open(f"{tempdir}/openssl.cnf", 'w') as fp:
                if args.type == 'pkinit-kdc':
                    keyusage = 'nonRepudiation,digitalSignature,keyEncipherment,keyAgreement'
                    oid = '1.3.6.1.5.2.3.5'
                else:
                    keyusage = 'digitalSignature,keyEncipherment,keyAgreement'
                    oid = '1.3.6.1.5.2.3.4'
                fp.write("""
[kdc_cert]
basicConstraints=CA:FALSE
keyUsage={keyusage}
extendedKeyUsage={oid}
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
issuerAltName=issuer:copy
subjectAltName=otherName:1.3.6.1.5.2.2;SEQUENCE:kdc_princ_name

[kdc_princ_name]
realm=EXP:0,GeneralString:{realm}
principal_name=EXP:1,SEQUENCE:kdc_principal_seq

[kdc_principal_seq]
name_type=EXP:0,INTEGER:1
name_string=EXP:1,SEQUENCE:kdc_principals

[kdc_principals]
""".format(realm = realm, keyusage = keyusage, oid = oid))
                tmp = princ.split('/')
                princnum = 1
                while tmp:
                    fp.write(f"princ{princnum}=GeneralString:{tmp.pop(0)}\n")
                    princnum = princnum + 1
            c = subprocess.run([
                'openssl', 'genrsa',
                '-out', f"{tempdir}/key.pem",
                f"{args.key_bits}" ])
            if c.returncode != 0:
                raise Exception('openssl genrsa failed')
            c = subprocess.run([
                'openssl', 'req',
                '-new', '-out', f"{tempdir}/req.pem",
                '-key', f"{tempdir}/key.pem",
                '-subj', args.subject ])
            if c.returncode != 0:
                raise Exception('openssl req failed')
            c = subprocess.run([
                'openssl', 'x509',
                '-req', '-in', f"{tempdir}/req.pem",
                '-CAkey', args.ca_certificate,
                '-CA', args.ca_certificate,
                '-out', f"{tempdir}/cert.pem",
                '-days', str(args.lifetime),
                '-extfile', f"{tempdir}/openssl.cnf",
                '-extensions', 'kdc_cert' ])
            if c.returncode != 0:
                raise Exception('openssl x509 failed')
            with open(args.certificate, 'w') as fp:
                fp.write(f"{open(f"{tempdir}/cert.pem", 'r').read()}\n")
                fp.write(f"{open(f"{tempdir}/key.pem", 'r').read()}\n")
    elif args.type == 'https-client' or args.type == 'https-server':
        if args.type == 'https-client':
            if args.hostname:
                raise Exception('https-client doesn\'t accept --hostname')
            if not args.email:
                raise Exception('https-client requires --email')
        else:
            if args.email:
                raise Exception('https-server doesn\'t accept --email')
            if not args.hostname:
                raise Exception('https-server requires --hostname')
        with tempfile.TemporaryDirectory() as tempdir:
            with open(f"{tempdir}/openssl.cnf", 'w') as fp:
                fp.write("""
[extensions]
subjectAltName = @alt_section
[alt_section]
""")
                if args.email:
                    fp.write(f"email = {args.email}\n")
                if args.hostname:
                    fp.write(f"DNS = {args.hostname}\n")
            c = subprocess.run([
                'openssl', 'genrsa',
                '-out', f"{tempdir}/key.pem",
                f"{args.key_bits}" ])
            if c.returncode != 0:
                raise Exception('openssl genrsa failed')
            c = subprocess.run([
                'openssl', 'req',
                '-new', '-out', f"{tempdir}/req.pem",
                '-key', f"{tempdir}/key.pem",
                '-subj', args.subject ])
            if c.returncode != 0:
                raise Exception('openssl req failed')
            c = subprocess.run([
                'openssl', 'x509',
                '-req', '-in', f"{tempdir}/req.pem",
                '-CAkey', args.ca_certificate,
                '-CA', args.ca_certificate,
                '-out', f"{tempdir}/cert.pem",
                '-days', str(args.lifetime),
                '-extfile', f"{tempdir}/openssl.cnf",
                '-extensions', 'extensions' ])
            if c.returncode != 0:
                raise Exception('openssl x509 failed')
            with open(args.certificate, 'w') as fp:
                fp.write(f"{open(f"{tempdir}/cert.pem", 'r').read()}\n")
                fp.write(f"{open(f"{tempdir}/key.pem", 'r').read()}\n")
    else:
        raise Exception(f"Unrecognized --type={args.type}")
