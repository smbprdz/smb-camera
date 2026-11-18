import unittest
from ucs.view_transform import ViewTransform,crop_geometry

class TransformTests(unittest.TestCase):
    def test_validated_state_is_independent_from_capture(self):
        state=ViewTransform();self.assertEqual(state.get()['angle'],0)
        state.set(angle=90,mirror=True,output_format='portrait');self.assertTrue(state.get()['mirror'])
        for invalid in [-90,45,360,True,'90']:
            with self.assertRaises(ValueError):state.set(angle=invalid)
        with self.assertRaises(ValueError):state.set(mirror=1)
        with self.assertRaises(ValueError):state.set(pan_x=float('nan'))

    def test_canvas_fill_and_crop_preserve_aspect_for_each_orientation(self):
        for angle in (0,90,180,270):
            for format in ('landscape','portrait'):
                geometry=crop_geometry(1920,1080,angle,format)
                w,h=geometry['canvas'];x,y,cw,ch=geometry['source']
                self.assertGreater(cw,0);self.assertGreater(ch,0)
                self.assertLessEqual(x+cw,1920);self.assertLessEqual(y+ch,1080)
                expected=h/w if angle in (90,270) else w/h
                self.assertAlmostEqual(cw/ch,expected,delta=.003)
                self.assertEqual((w,h),(1920,1080) if format=='landscape' else (1080,1920))
        left=crop_geometry(1920,1080,0,'portrait',pan_x=-1)['source']
        right=crop_geometry(1920,1080,0,'portrait',pan_x=1)['source']
        self.assertEqual(left[0],0);self.assertEqual(right[0]+right[2],1920)

if __name__=='__main__':unittest.main()
