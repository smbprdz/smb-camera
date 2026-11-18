"""Build the portable Windows beta from committed files at an explicit Git revision."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PATHS = (
    'distribution/windows', 'ucs', 'integrations/obs',
    'LICENSE', 'THIRD-PARTY.md', 'requirements-windows-beta.txt',
    'docs/INSTALL-WINDOWS.md', 'docs/PRIMEIRO-USO.html', 'docs/INSTALL-IOS.md', 'docs/NVIDIA-BETA.md', 'docs/NATIVE.lock.json',
    'docs/NVIDIA-VFX.lock.json', 'docs/PRIVACY.md', 'docs/GPU-OUTPUT.md',
    'tools/install_sdl.py', 'tools/obs_setup.py',
)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def build(ref, output):
    commit = git('rev-parse', '--verify', '--end-of-options', f'{ref}^{{commit}}').decode().strip()
    records = {}
    archived = git('archive', '--format=zip', commit, '--', *RELEASE_PATHS)
    with zipfile.ZipFile(io.BytesIO(archived)) as source:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            name = PurePosixPath(entry.filename)
            if name.is_relative_to('distribution/windows'):
                name = name.relative_to('distribution/windows')
            if name.as_posix() in records:
                raise ValueError(f'Duplicate archive path: {name}')
            records[name.as_posix()] = source.read(entry)

    records['README.md'] = b'# SMB Camera Beta\n\n[Guia de instalacao para Windows](docs/INSTALL-WINDOWS.md)\n'
    version = re.search(rb"__version__ = '(\d+\.\d+\.\d+)'", records['ucs/__init__.py'])[1].decode()
    folder = f'SMB-Camera-Windows-{version}-beta'
    manifest = {
        'version': f'{version}-beta',
        'source_commit': commit,
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(records.items())},
    }
    records['MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'{folder}.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as release:
        for name, data in sorted(records.items()):
            release.writestr(f'{folder}/{name}', data)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--output', type=Path, default=ROOT / 'output' / 'releases')
    args = parser.parse_args()
    artifact = build(args.ref, args.output)
    print(f'{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact}')


if __name__ == '__main__':
    main()
