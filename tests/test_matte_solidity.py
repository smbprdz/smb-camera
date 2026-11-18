import math
import unittest
from ucs.matting import BackgroundState
from ucs import studio_state
from ucs.color import ColorState
from ucs.view_transform import ViewTransform


class SolidityStateTests(unittest.TestCase):
    def test_post_processing_does_not_invalidate_temporal_model(self):
        state=BackgroundState();state.set(mode='transparent')
        generation=state.get()['generation']
        state.set(solidity=60)
        self.assertEqual(state.get()['solidity'],60)
        self.assertEqual(state.get()['generation'],generation)
        before=state.get()
        for value in (-1,101,math.nan,math.inf,True,'50'):
            with self.assertRaises(ValueError):state.set(mode='off',solidity=value)
            self.assertEqual(state.get(),before)
        state.set(quality='performance');self.assertGreater(state.get()['generation'],generation)

    def test_old_profiles_migrate_neutrally_and_new_profiles_preserve_control(self):
        state=BackgroundState();state.set(mode='transparent',solidity=60)
        data=studio_state.snapshot(ColorState(),ViewTransform(),state)
        self.assertEqual(data['version'],2)
        self.assertEqual(studio_state.validated(data)[2].get()['solidity'],60)
        data['version']=1;del data['background']['solidity']
        self.assertEqual(studio_state.validated(data)[2].get()['solidity'],0)
        data['version']=2
        with self.assertRaises(ValueError):studio_state.validated(data)

    def test_invalid_new_profile_never_partially_changes_live_color(self):
        color=ColorState();view=ViewTransform();state=BackgroundState()
        data=studio_state.snapshot(color,view,state)
        data['color']['adjustments']['exposure']=1
        data['background']['solidity']=-1
        with self.assertRaises(ValueError):studio_state.restore(data,color,view,state)
        self.assertEqual(color.get()['exposure'],0)
        self.assertEqual(state.get()['solidity'],0)
