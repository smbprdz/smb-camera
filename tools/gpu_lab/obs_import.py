from pathlib import Path
import json,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from interop import Device,Interop
from ucs.gl_preview import GLPreview
from ucs.process_job import ProcessJob
r=GLPreview(64,36,window_width=64,window_height=36,hidden=True)
d=None;resources=[]
try:
 d=Device(r.info['renderer'])
 handles=[]
 for color in ((1.,0.,0.,1.),(0.,1.,0.,1.),(0.,0.,1.,1.)):
  shared=Interop(r,d,64,36);resources.append(shared)
  def draw(target):
   target.clear(0,0,0,0)
   target.clear(.25,.125,.375,.5,viewport=(21,0,22,36))
   target.clear(*color,viewport=(43,0,21,36))
  shared.render(draw);handles.append(shared.handle)
 config={'scope':'immutable generated GPU textures','width':64,'height':36}
 config.update({'handle'+str(i+1):h for i,h in enumerate(handles)})
 scripts=Path(__file__).resolve().parent
 folder=Path('output/gpu-lab').resolve();folder.mkdir(parents=True,exist_ok=True)
 with (folder/'obs-import.log').open('wb') as log:
  child=subprocess.Popen([sys.executable,str(scripts/'obs_receiver.py')],stdin=subprocess.PIPE,
   stdout=log,stderr=subprocess.STDOUT)
  job=ProcessJob(child)
  try:
   child.stdin.write((json.dumps(config)+'\n').encode());child.stdin.close()
   child.wait(20)
  except subprocess.TimeoutExpired:job.terminate();child.wait(5);raise
  finally:job.close()
 result=json.loads((folder/'obs-import-result.json').read_text());print(json.dumps(result))
 if child.returncode or not result['passed']:raise SystemExit(1)
finally:
 for shared in reversed(resources):shared.close()
 if d:d.close()
 r.close()
