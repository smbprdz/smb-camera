"""Local studio preferences/presets. No pairing credentials or remote camera commands."""
import json,os
from pathlib import Path
from .color import ColorState,MAX_PRESET_BYTES
from .view_transform import ViewTransform
from .matting import BackgroundState

def snapshot(color,view,background):
    bg=background.get()
    return {'version':2,'color':color.preset(),'view':view.get(),
            'background':{key:bg[key] for key in ('mode','image','quality','solidity')}}

def validated(data):
    if type(data) is not dict or set(data)!={'version','color','view','background'} or type(data['version']) is not int or data['version'] not in (1,2):
        raise ValueError('Perfil de estudio incompativel.')
    color=ColorState();color.restore(data['color'])
    view=ViewTransform();values=data['view']
    if type(values) is not dict or set(values)!=set(view.get()):raise ValueError('Enquadramento invalido.')
    view.set(**values)
    bg=data['background']
    expected={'mode','image','quality'} if data['version']==1 else {'mode','image','quality','solidity'}
    if type(bg) is not dict or set(bg)!=expected:raise ValueError('Fundo invalido.')
    path=bg['image'];warning=''
    if path is not None:
        if type(path) is not str or len(path)>4096 or path.startswith(('\\\\','//')) or not Path(path).is_absolute():
            raise ValueError('O fundo precisa estar em um arquivo local.')
        if not Path(path).is_file():path=None;warning='Arquivo de fundo do perfil não encontrado.'
        elif bg['mode']=='motion' or Path(path).suffix.lower() in ('.gif','.mp4','.mov','.webm','.mkv'):
            from .background_motion import verify_motion
            try:
                verify_motion(path)
            except Exception as exc:
                raise ValueError('Fundo animado do perfil inválido.') from exc
        else:
            from PIL import Image
            try:
                with Image.open(path) as image:
                    if image.width*image.height>50_000_000:raise ValueError('Imagem de fundo muito grande.')
                    image.verify()
            except Exception as exc:raise ValueError('Imagem de fundo do perfil invalida.') from exc
    background=BackgroundState();background.set(mode=bg['mode'],image=path,quality=bg['quality'],solidity=bg.get('solidity',0.))
    return color,view,background,warning

def restore(data,color,view,background):
    c,v,b,warning=validated(data)
    color.restore(c.preset());view.set(**v.get());bg=b.get()
    # A missing path clears the old choice rather than retaining an unrelated image.
    with background.lock:background.image=bg['image']
    background.set(mode=bg['mode'],quality=bg['quality'],solidity=bg['solidity'])
    return warning

def read(path):
    if path.stat().st_size>MAX_PRESET_BYTES:raise ValueError('Perfil muito grande.')
    return json.loads(path.read_text(encoding='utf-8'))

def write(path,data):
    validated(data)
    encoded=json.dumps(data,ensure_ascii=False,indent=2)
    if len(encoded.encode('utf-8'))>MAX_PRESET_BYTES:raise ValueError('Perfil muito grande.')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(encoded,encoding='utf-8',newline='\n');os.replace(temp,path)
