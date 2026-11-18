"""Process-local DLL search paths for the optional isolated NVIDIA runtime."""
import os
from pathlib import Path
import sys

_handles=[]
def prepare():
    if os.name=='nt':
        root=Path(sys.prefix)/'Lib/site-packages/nvidia'
        folders=[p for p in root.glob('*/bin') if p.is_dir()]
        for folder in folders:_handles.append(os.add_dll_directory(str(folder)))
        # Some cuDNN sublibraries use their own LoadLibrary lookup. This affects
        # this process only, not the machine PATH or any other application.
        os.environ['PATH']=os.pathsep.join([str(p) for p in folders]+[os.environ.get('PATH','')])
    import onnxruntime as ort
    ort.preload_dlls(directory='')
