import os,unittest,uuid
from unittest.mock import patch
from ucs.camera_runtime import CONFIG,endpoint_bytes

def endpoint():return {'canvas':[1920,1080],'producer_pid':123,'epoch':7,'pipe_name':'\\\\.\\pipe\\UCS.FrameBridge.'+str(uuid.uuid4()),'owner_sid':'S-1-5-21-1-2-3-1001'}

class NativeEndpointTests(unittest.TestCase):
    def test_public_endpoint_matches_cpp_layout_and_bounds(self):
        value=endpoint();data=endpoint_bytes(value,30);fields=CONFIG.unpack(data)
        self.assertEqual(len(data),688);self.assertEqual(fields[:11],(0x42534355,2,123,0,7,1920,1080,30,1,1,0))
        self.assertEqual(fields[11].decode('utf-16-le').rstrip('\0'),value['pipe_name'])
        for change in ({'canvas':[1921,1080]},{'producer_pid':0},{'epoch':0},{'pipe_name':'\\\\remote\\pipe\\wrong'},{'owner_sid':'S-1-5-21\n'}):
            with self.assertRaises(ValueError):endpoint_bytes(dict(value,**change),30)
    @unittest.skipUnless(os.name=='nt','Windows registry and pipe')
    def test_public_leaf_acl_write_and_owned_cleanup_do_not_touch_other_endpoint(self):
        import winreg
        from ucs import camera_runtime as runtime
        from ucs.frame_output import FramePublisher
        key='Software\\SMB\\Camera\\Test'+uuid.uuid4().hex
        publisher=FramePublisher(formats=(1,));publisher.set_canvas(1920,1080)
        try:
            with patch.object(runtime,'RUNTIME_KEY',key):
                runtime.write_endpoint(publisher.endpoint(),30)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:data,kind=winreg.QueryValueEx(handle,'Endpoint')
                self.assertEqual(kind,winreg.REG_BINARY);self.assertEqual(len(data),688)
                runtime.remove_endpoint(os.getpid()+1,publisher.epoch)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:self.assertEqual(winreg.QueryValueEx(handle,'Endpoint')[0],data)
                runtime.remove_endpoint(os.getpid(),publisher.epoch)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:
                    with self.assertRaises(FileNotFoundError):winreg.QueryValueEx(handle,'Endpoint')
        finally:
            publisher.close()
            try:winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,key,winreg.KEY_WOW64_64KEY)
            except FileNotFoundError:pass
