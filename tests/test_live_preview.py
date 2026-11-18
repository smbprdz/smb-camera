import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import hashlib
from ucs.live_preview import LatestFrame, PacketDecoder
from ucs.synthetic import access_units

class MailboxTests(unittest.TestCase):
    def test_stalled_renderer_keeps_only_latest_frame(self):
        slot=LatestFrame()
        for n in range(1000): slot.put(n)
        self.assertEqual(slot.take(),999)
        self.assertEqual(slot.replaced,999)
        self.assertIsNone(slot.take(timeout=0))
        slot.close();slot.put('after-close')
        self.assertIsNone(slot.take(timeout=0))

@unittest.skipUnless(importlib.util.find_spec('av'), 'optional PyAV preview not installed')
class PacketTests(unittest.TestCase):
    def test_malformed_access_unit_fails_closed(self):
        decoder=PacketDecoder({'width':1920,'height':1080})
        with self.assertRaises(ValueError): decoder.decode(b'invalid h264',0)

    def test_packet_decode_preserves_images_pts_and_immediate_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture=root/'test.h264';reference=root/'hashes.txt'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                'testsrc2=size=1920x1080:rate=30','-frames:v','30','-c:v','libx264','-preset','ultrafast',
                '-tune','zerolatency','-x264-params','aud=1:keyint=30:repeat-headers=1',str(fixture)],check=True)
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(fixture),
                '-pix_fmt','yuv420p','-f','framemd5',str(reference)],check=True)
            expected=[x.rsplit(',',1)[-1].strip() for x in reference.read_text().splitlines() if x and not x.startswith('#')]
            decoder=PacketDecoder({'width':1920,'height':1080})
            actual=[]
            for n,(unit,_) in enumerate(access_units(fixture.read_bytes())):
                pts=round(n*1_000_000/30)
                frames=decoder.decode(unit,pts)
                self.assertEqual(len(frames),1,'decoder buffered an AU')
                self.assertEqual(frames[0].pts,pts)
                actual.append(hashlib.md5(frames[0].to_ndarray(format='yuv420p').tobytes()).hexdigest())
            self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()
