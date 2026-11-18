"""Fetch pinned MIT source/header dependencies for the isolated native test.

No installer, downloaded executable, device registration or third-party script
is executed. This prepares only audited C++ source/header inputs for compilation.
"""
from pathlib import Path
import hashlib,io,json,urllib.request,zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'runtime/native-lab'

def fetch(url,limit):
    with urllib.request.urlopen(url,timeout=40) as response:data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Dependency download exceeds bounded size')
    return data

def safe_file(base,name):
    if '..' in Path(name).parts or Path(name).is_absolute():raise ValueError('Unsafe dependency path')
    target=(base/name).resolve()
    if not target.is_relative_to(base.resolve()):raise ValueError('Dependency path escaped destination')
    target.parent.mkdir(parents=True,exist_ok=True);return target

def verify_source(data,row):
    exact=hashlib.sha256(data).hexdigest()
    normalized=hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()
    if exact!=row['sha256'] and normalized!=row['normalized_lf_sha256']:
        raise ValueError('Pinned source digest mismatch: '+row['path'])
    return exact

def main():
    record=json.loads((ROOT/'docs/NATIVE-LAB.lock.json').read_text(encoding='utf-8'))
    DEST.mkdir(parents=True,exist_ok=True);copied=[]
    for row in record['files']:
        target=safe_file(DEST/'src',Path(row['path']).name)
        data=target.read_bytes() if target.is_file() else fetch(record['source_base']+row['path'],512*1024)
        exact=verify_source(data,row)
        target.write_bytes(data);copied.append({'path':row['path'],'download_sha256':exact})
    dependency=record['dependency'];archive_path=DEST/'wil.nupkg'
    data=archive_path.read_bytes() if archive_path.is_file() else fetch(dependency['url'],4*1024*1024)
    if hashlib.sha256(data).hexdigest()!=dependency['sha256']:raise ValueError('Pinned WIL package digest mismatch')
    archive_path.write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        selected=[member for member in archive.infolist() if member.filename.startswith('include/wil/') or member.filename in ('LICENSE','ThirdPartyNotices.txt')]
        if sum(member.file_size for member in selected)>16*1024*1024:raise ValueError('Header archive expansion too large')
        for member in selected:
            if member.is_dir():continue
            if (member.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive link rejected')
            safe_file(DEST/'wil',member.filename).write_bytes(archive.read(member))
    receipt={'source_commit':record['commit'],'files':copied,'WIL':dependency,'executed_downloads':False}
    (DEST/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({'status':'prepared','source_files':len(copied),'destination':str(DEST),'device_registered':False}))

if __name__=='__main__':main()
