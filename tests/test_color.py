import json,math,tempfile,unittest
from pathlib import Path
from ucs.color import ColorState,parse_cube
from ucs import studio_state
from ucs.matting import BackgroundState
from ucs.view_transform import ViewTransform

def cube(swap=False):
    lines=['TITLE "Teste local"','LUT_3D_SIZE 2']
    for b in (0,1):
        for g in (0,1):
            for r in (0,1):lines.append(f'{g if swap else r} {r if swap else g} {b}')
    return '\n'.join(lines)

class ColorTests(unittest.TestCase):
    def test_neutral_bypass_keeps_intent_and_reset_removes_lut(self):
        state=ColorState();self.assertFalse(state.get()['active'])
        state.set(exposure=1);state.set_lut(cube());state.enable(False)
        self.assertFalse(state.get()['active']);self.assertEqual(state.get()['exposure'],1)
        state.enable(True);self.assertTrue(state.get()['active']);state.reset()
        self.assertFalse(state.get()['active']);self.assertIsNone(state.get()['lut'])
    def test_invalid_controls_cannot_mutate_live_values(self):
        state=ColorState();before=state.preset()
        for update in ({'exposure':float('nan')},{'gamma':0},{'temperature':True},{'bogus':1},{'saturation':201}):
            with self.assertRaises(ValueError):state.set(**update)
            self.assertEqual(state.preset(),before)
    def test_cube_rejects_truncation_unsupported_formats_and_bad_domain(self):
        for text in (cube().rsplit('\n',1)[0],cube()+'\n0 0 0','LUT_1D_SIZE 2\n0 0 0',cube()+'\nDOMAIN_MAX 0 1 1',cube().replace('1 1 1','nan 1 1')):
            with self.assertRaises(ValueError):parse_cube(text)
    def test_embedded_lut_and_color_preset_roundtrip_and_atomic_rejection(self):
        state=ColorState();state.set(exposure=.7,saturation=80);state.set_lut(cube(True))
        other=ColorState();other.restore(json.loads(json.dumps(state.preset())))
        self.assertEqual(other.preset(),state.preset())
        bad=state.preset();bad['lut_cube']='LUT_3D_SIZE 2\n0 0 0'
        before=other.preset()
        with self.assertRaises(ValueError):other.restore(bad)
        self.assertEqual(other.preset(),before)
    def test_studio_roundtrip_saves_view_and_grade_without_pairing_secrets(self):
        color=ColorState();color.set(temperature=20);view=ViewTransform();view.set(angle=90,mirror=True,output_format='portrait')
        background=BackgroundState();background.set(mode='transparent')
        data=studio_state.snapshot(color,view,background)
        self.assertNotIn('token',json.dumps(data));self.assertNotIn('fingerprint',json.dumps(data))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'studio.json';studio_state.write(path,data)
            colors,views,bg,warning=studio_state.validated(studio_state.read(path))
        self.assertEqual(colors.preset(),color.preset());self.assertEqual(views.get(),view.get());self.assertEqual(bg.get()['mode'],'transparent')
    def test_invalid_view_does_not_partially_apply_valid_color(self):
        color=ColorState();view=ViewTransform();background=BackgroundState();data=studio_state.snapshot(color,view,background)
        data['color']['adjustments']['exposure']=2;data['view']['angle']=37
        with self.assertRaises(ValueError):studio_state.restore(data,color,view,background)
        self.assertEqual(color.get()['exposure'],0)
    def test_preset_rejects_unc_background_before_reading_it(self):
        data=studio_state.snapshot(ColorState(),ViewTransform(),BackgroundState());data['background']['image']='\\\\server\\share\\photo.png'
        with self.assertRaises(ValueError):studio_state.validated(data)
    def test_invalid_background_file_cannot_partially_apply_a_profile(self):
        color=ColorState();view=ViewTransform();background=BackgroundState()
        data=studio_state.snapshot(color,view,background);data['color']['adjustments']['exposure']=2
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'broken.png';file.write_bytes(b'not an image')
            data['background'].update(mode='image',image=str(file))
            with self.assertRaises(ValueError):studio_state.restore(data,color,view,background)
        self.assertEqual(color.get()['exposure'],0);self.assertEqual(background.get()['mode'],'off')
