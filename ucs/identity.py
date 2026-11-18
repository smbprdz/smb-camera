"""Local pairing material. Never include runtime in packages or source control."""
import argparse
import hashlib
from pathlib import Path
import secrets
import shutil
import ssl
import subprocess

def create(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cert, key, token = [directory / n for n in ('cert.pem', 'key.pem', 'token.txt')]
    if any(p.exists() for p in (cert, key, token)):
        raise FileExistsError('identity already exists; choose a new directory to rotate')
    openssl = shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:3072', '-sha256',
                    '-nodes', '-days', '30', '-subj', '/CN=UCS laboratory receiver',
                    '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
    token.write_text(secrets.token_hex(32), encoding='ascii')
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    fingerprint = hashlib.sha256(der).hexdigest()
    (directory/'fingerprint.txt').write_text(fingerprint, encoding='ascii')
    return fingerprint

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--directory', default='runtime/identity')
    args = p.parse_args()
    print('Certificate SHA-256:', create(args.directory))
    print('Pairing token saved locally. Read it on your PC; never put it in logs.')
