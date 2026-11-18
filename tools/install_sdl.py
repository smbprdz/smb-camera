"""Download the exact official SDL2 runtime identified in NATIVE.lock.json."""
import hashlib,json
from pathlib import Path
import urllib.request,zipfile

def main():
    root=Path(__file__).resolve().parents[1]
    info=json.loads((root/'docs/NATIVE.lock.json').read_text())['SDL2']
    dest=root/'runtime/native'/('SDL2-'+info['version']);dest.mkdir(parents=True,exist_ok=True)
    archive=dest/'SDL2.zip'
    with urllib.request.urlopen(info['url'],timeout=30) as response:archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=info['archive_sha256']:raise ValueError('SDL2 archive digest mismatch')
    with zipfile.ZipFile(archive) as bundle:
        for name in ('SDL2.dll','README-SDL.txt','.git-hash'):
            (dest/name).write_bytes(bundle.read(name))
    if hashlib.sha256((dest/'SDL2.dll').read_bytes()).hexdigest()!=info['dll_sha256']:raise ValueError('SDL2 DLL digest mismatch')
    with urllib.request.urlopen(info['license_url'],timeout=20) as response:license_text=response.read()
    if hashlib.sha256(license_text).hexdigest()!=info['license_sha256']:raise ValueError('SDL2 license digest mismatch')
    (dest/'LICENSE.txt').write_bytes(license_text)
    print('Pinned SDL2 runtime ready:',dest)

if __name__=='__main__':main()
