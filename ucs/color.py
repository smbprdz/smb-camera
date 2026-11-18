"""Versioned SDR grading intent, independent of capture and rendering APIs."""
from dataclasses import dataclass
import hashlib,json,math,threading

# key: (default, minimum, maximum). Temperature/tint are relative corrections,
# not physical camera Kelvin, ISO or shutter settings.
PARAMETERS={
    'exposure':(0.,-4.,4.),'contrast':(0.,-100.,100.),
    'saturation':(100.,0.,200.),'vibrance':(0.,-100.,100.),'gamma':(1.,.5,2.),
    'shadows':(0.,-100.,100.),'highlights':(0.,-100.,100.),
    'blacks':(0.,-100.,100.),'whites':(0.,-100.,100.),
    'temperature':(0.,-100.,100.),'tint':(0.,-100.,100.),
    'red':(0.,-2.,2.),'green':(0.,-2.,2.),'blue':(0.,-2.,2.),
    'lut_strength':(100.,0.,100.)}
MAX_PRESET_BYTES=32*1024*1024

@dataclass(frozen=True)
class CubeLUT:
    size:int
    data:bytes
    minimum:tuple
    maximum:tuple
    title:str
    source:str
    digest:str

def parse_cube(text):
    """Bounded 3D .cube parser. R changes fastest; no code or remote paths."""
    import numpy as np
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_PRESET_BYTES:raise ValueError('LUT muito grande.')
    size=None;nodes=[];minimum=(0.,0.,0.);maximum=(1.,1.,1.);title='LUT personalizada'
    def triple(parts):
        if len(parts)!=3:raise ValueError('A LUT precisa de valores RGB completos.')
        values=tuple(float(v) for v in parts)
        if not all(math.isfinite(v) and abs(v)<=16 for v in values):raise ValueError('LUT com valores invalidos.')
        return values
    for line in text.splitlines():
        parts=line.split('#',1)[0].strip().split()
        if not parts:continue
        name=parts[0]
        if name=='TITLE':title=' '.join(parts[1:]).strip('"')[:128];continue
        if name=='LUT_3D_SIZE':
            if size is not None or len(parts)!=2:raise ValueError('Tamanho de LUT invalido.')
            size=int(parts[1])
            if not 2<=size<=65:raise ValueError('Suportadas LUTs 3D de 2 a 65 pontos por eixo.')
        elif name=='DOMAIN_MIN':minimum=triple(parts[1:])
        elif name=='DOMAIN_MAX':maximum=triple(parts[1:])
        else:
            if name.startswith(('LUT_','DOMAIN_')):raise ValueError('Esta variante de LUT ainda nao e suportada. Use .cube 3D.')
            if size is None or len(nodes)>=size**3:raise ValueError('Numero de pontos da LUT invalido.')
            nodes.append(triple(parts))
    if size is None or len(nodes)!=size**3 or not all(hi>lo for lo,hi in zip(minimum,maximum)):
        raise ValueError('LUT incompleta ou dominio invalido.')
    data=np.asarray(nodes,dtype=np.float32).tobytes()
    return CubeLUT(size,data,minimum,maximum,title,text,hashlib.sha256(text.encode('utf-8')).hexdigest())

class ColorState:
    def __init__(self):
        self.lock=threading.Lock();self.values={key:spec[0] for key,spec in PARAMETERS.items()}
        self.enabled=True;self.lut=None;self.revision=0
    @staticmethod
    def validate(values):
        if type(values) is not dict or any(key not in PARAMETERS for key in values):raise ValueError('Ajuste de cor desconhecido.')
        result={key:spec[0] for key,spec in PARAMETERS.items()}
        for key,value in values.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not PARAMETERS[key][1]<=value<=PARAMETERS[key][2]:
                raise ValueError('Valor de cor fora do intervalo: '+key)
            result[key]=float(value)
        return result
    def set(self,**values):
        validated=self.validate(values)
        with self.lock:
            self.values.update({key:validated[key] for key in values});self.revision+=1
    def enable(self,value):
        if type(value) is not bool:raise ValueError('Estado de cor invalido.')
        with self.lock:self.enabled=value;self.revision+=1
    def set_lut(self,text):
        lut=parse_cube(text) if text is not None else None
        with self.lock:self.lut=lut;self.revision+=1
    def reset(self):
        with self.lock:
            self.values={key:spec[0] for key,spec in PARAMETERS.items()};self.enabled=True;self.lut=None;self.revision+=1
    def get(self):
        with self.lock:
            active=self.enabled and (any(self.values[k]!=PARAMETERS[k][0] for k in PARAMETERS if k!='lut_strength') or
                                     self.lut is not None and self.values['lut_strength']>0)
            return dict(self.values,enabled=self.enabled,active=active,lut=self.lut,revision=self.revision)
    def preset(self):
        with self.lock:return {'version':1,'enabled':self.enabled,'adjustments':dict(self.values),'lut_cube':self.lut.source if self.lut else None}
    def restore(self,preset):
        # Validate everything before mutating the live grading state.
        if type(preset) is not dict or set(preset)!={'version','enabled','adjustments','lut_cube'} or type(preset['version']) is not int or preset['version']!=1 or type(preset['enabled']) is not bool:
            raise ValueError('Perfil de cor incompativel.')
        values=self.validate(preset['adjustments']);lut=parse_cube(preset['lut_cube']) if preset['lut_cube'] is not None else None
        with self.lock:self.values=values;self.enabled=preset['enabled'];self.lut=lut;self.revision+=1

def load_preset(path):
    if path.stat().st_size>MAX_PRESET_BYTES:raise ValueError('Perfil muito grande.')
    return json.loads(path.read_text(encoding='utf-8'))
