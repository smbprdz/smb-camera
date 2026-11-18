"""Install model data only, with pinned hash. No third-party code execution."""
from pathlib import Path
import hashlib,json,urllib.request

def main():
    root=Path(__file__).resolve().parents[1];info=json.loads((root/'docs/MODELS.lock.json').read_text())['modnet-webcam']
    folder=root/'runtime/models';folder.mkdir(parents=True,exist_ok=True);path=folder/'modnet-webcam.onnx'
    if not path.exists():
        with urllib.request.urlopen(info['url'],timeout=30) as response:path.write_bytes(response.read())
    if path.stat().st_size!=info['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:
        raise ValueError('Model size/digest mismatch')
    with urllib.request.urlopen(info['license_url'],timeout=20) as response:(folder/'MODNet-LICENSE.txt').write_bytes(response.read())
    (folder/'modnet-webcam.receipt.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    print('Pinned MODNet model ready. Inference backend must be installed separately in an isolated environment.')

if __name__=='__main__':main()
