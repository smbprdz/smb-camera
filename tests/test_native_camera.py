import io,time,unittest
from pathlib import Path
from unittest.mock import patch
from ucs.native_camera import NativeCamera

class NativeLifecycleTests(unittest.TestCase):
    def test_uninstalled_component_does_not_enable_output_or_launch_a_process(self):
        class Publisher:
            canvas=(1920,1080);enabled=False;epoch=7
            def enable(self):raise AssertionError('Uninstalled component enabled output')
        with patch('ucs.native_camera.camera_runtime.installed_directory',return_value=None),patch('ucs.native_camera.subprocess.Popen',side_effect=AssertionError('Uninstalled process launched')):
            native=NativeCamera(Publisher());self.assertFalse(native.start(30));self.assertEqual(native.snapshot()['state'],'off');native.close()
    def test_native_start_failure_releases_lazily_enabled_output_and_endpoint(self):
        events=[]
        class Publisher:
            canvas=(1920,1080);enabled=False;epoch=7
            def enable(self):self.enabled=True;events.append('enable')
            def disable(self):self.enabled=False;events.append('disable')
            def endpoint(self):return {'owner_sid':'S-1-5-21-1-2-3-1001'}
        with patch('ucs.native_camera.camera_runtime.installed_directory',return_value=Path('C:/Program Files/SMB Camera Bridge')),patch('ucs.native_camera.camera_runtime.write_endpoint',side_effect=lambda *_:events.append('write')),patch('ucs.native_camera.camera_runtime.remove_endpoint',side_effect=lambda *_:events.append('remove')),patch('ucs.native_camera.subprocess.Popen',side_effect=OSError('Unsigned native process refused')):
            publisher=Publisher();native=NativeCamera(publisher);self.assertTrue(native.start(30));native.close()
            self.assertEqual(native.snapshot()['state'],'error');self.assertFalse(publisher.enabled);self.assertEqual(events,['enable','write','remove','disable'])
    def test_format_change_requests_stop_without_relaunching_or_changing_capabilities(self):
        class Publisher:canvas=(1920,1080)
        with patch('ucs.native_camera.camera_runtime.installed_directory',return_value=None):
            native=NativeCamera(Publisher());native.state='running';native.mode=(1920,1080,30)
            native.observe((1080,1920),30);self.assertTrue(native.stop_event.is_set());self.assertEqual(native.state,'stopping')
            native.close()
