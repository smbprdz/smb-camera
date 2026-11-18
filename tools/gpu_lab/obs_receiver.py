"""Isolated existing signed OBS engine consumes immutable generated GPU textures."""
from pathlib import Path
import ctypes as C,json,os,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.probe_obs_alpha import VideoInfo,VideoData,bind
config=json.loads(sys.stdin.readline())
assert config['scope']=='immutable generated GPU textures' and config['width']==64 and config['height']==36
script_directory=Path(__file__).resolve().parent
folder=Path('output/gpu-lab').resolve();folder.mkdir(parents=True,exist_ok=True)
binary=Path('C:/Program Files/obs-studio/bin/64bit')
directory=os.add_dll_directory(str(binary));os.chdir(binary)
obs=C.CDLL(str(binary/'obs.dll'));scripts=C.CDLL(str(binary/'obs-scripting.dll'))
p,s,u,b=C.c_void_p,C.c_char_p,C.c_uint32,C.c_bool
CB=C.CFUNCTYPE(None,p,C.POINTER(VideoData))
for n,a,r in (
 ('obs_get_version_string',[],s),('obs_startup',[s,s,p],b),('obs_shutdown',[],None),
 ('obs_add_data_path',[s],None),('obs_reset_video',[C.POINTER(VideoInfo)],C.c_int),
 ('obs_data_create_from_json',[s],p),('obs_data_release',[p],None),
 ('obs_source_create',[s,s,p,p],p),('obs_source_release',[p],None),
 ('obs_set_output_source',[u,p],None),('obs_add_raw_video_callback',[p,CB,p],None),
 ('obs_remove_raw_video_callback',[CB,p],None)):
 bind(obs,n,a,r)
for n,a,r in (('obs_scripting_load',[],b),('obs_scripting_unload',[],None),
 ('obs_script_create',[s,p],p),('obs_script_destroy',[p],None),('obs_script_loaded',[p],b)):
 bind(scripts,n,a,r)
report={'scope':'own generated GPU textures imported directly by official OBS engine',
 'passed':False,'personal_media_recorded':False,'obs_ui_or_profiles_modified':False,
 'sender_readback_in_import_path':False,'live_mutable_transport_validated':False,
 'output_frames':0,'colors':[],'callback_errors':[]}
active=loaded=connected=False;source=script=settings=None;colors=set()
def receive(param,ptr):
 try:
  frame=ptr.contents
  row=C.string_at(C.cast(frame.data[0],p).value+18*frame.linesize[0],64*4)
  pixels=[tuple(row[x*4:x*4+4]) for x in (8,32,56)]
  report['output_frames']+=1
  if pixels[1][3]>0:
   colors.add(pixels[2])
   assert max(pixels[0])==0
   assert all(abs(a-b)<=1 for a,b in zip(pixels[1],(96,32,64,128)))
   assert pixels[2][3]>=254
 except Exception as error:report['callback_errors'].append(type(error).__name__)
callback=CB(receive)
try:
 assert obs.obs_get_version_string()==b'32.2.2','Pinned OBS ABI required'
 active=obs.obs_startup(b'en-US',str(folder/'obs-module-config').encode(),None);assert active
 obs.obs_add_data_path(b'C:/Program Files/obs-studio/data/libobs/')
 info=VideoInfo(b'libobs-d3d11',30,1,64,36,64,36,7,0,False,0,2,0)
 assert obs.obs_reset_video(C.byref(info))==0
 loaded=scripts.obs_scripting_load();assert loaded
 script=scripts.obs_script_create((script_directory/'obs_gpu.lua').as_posix().encode(),None)
 assert script and scripts.obs_script_loaded(script)
 settings=obs.obs_data_create_from_json(json.dumps(config).encode())
 source=obs.obs_source_create(b'smb_gpu_generated_lab',b'Own generated GPU textures',settings,None);assert source
 obs.obs_set_output_source(0,source);obs.obs_add_raw_video_callback(None,callback,None);connected=True
 time.sleep(4)
 report['colors']=[list(c) for c in sorted(colors)]
 report['passed']=report['output_frames']>=90 and len(colors)==3 and not report['callback_errors']
except Exception as error:report['error']=type(error).__name__+': '+str(error)
finally:
 if connected:obs.obs_remove_raw_video_callback(callback,None)
 if source:obs.obs_set_output_source(0,None);obs.obs_source_release(source)
 if settings:obs.obs_data_release(settings)
 if script:scripts.obs_script_destroy(script)
 if loaded:scripts.obs_scripting_unload()
 if active:obs.obs_shutdown()
 directory.close()
 (folder/'obs-import-result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report),flush=True)
raise SystemExit(0 if report['passed'] else 1)
