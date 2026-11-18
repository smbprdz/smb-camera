"""OBS discovery accepts official Windows layout and distinguishes config locations."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import obs_setup


class ObsSetupTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.installed = self.home / 'Program Files/obs-studio'
        self.portable = self.home / 'OBS-Portable'
        for root in (self.installed, self.portable):
            binary = root / obs_setup.OBS_BINARY
            binary.parent.mkdir(parents=True)
            binary.touch()

    def test_distinguishes_installed_and_portable(self):
        roaming = self.home / 'AppData/Roaming'
        installed = obs_setup.inspect_obs(self.installed, appdata=roaming)
        self.assertFalse(installed.portable)
        self.assertEqual(Path(installed.settings), roaming / 'obs-studio')
        (self.portable / 'portable_mode.txt').touch()
        portable = obs_setup.inspect_obs(self.portable / obs_setup.OBS_BINARY, appdata=roaming)
        self.assertTrue(portable.portable)
        self.assertEqual(Path(portable.settings), self.portable / 'config/obs-studio')
        self.assertTrue(obs_setup.inspect_obs(self.installed, portable=True).portable)

    def test_adjacent_portable_beats_standard_in_list_without_touching_profiles(self):
        (self.portable / 'portable_mode').touch()
        with patch.object(obs_setup, 'ROOT', self.home/'SMB-Camera'), \
                patch.dict(obs_setup.os.environ, {'ProgramFiles': str(self.installed.parent),
                                                 'ProgramW6432': str(self.installed.parent)}), \
                patch.object(obs_setup.subprocess, 'run', side_effect=OSError):
            observed = obs_setup.discover_obs()
        self.assertEqual(len(observed), 2)
        self.assertTrue(observed[0].portable)
        self.assertFalse(observed[1].portable)
        self.assertFalse((self.portable / 'config').exists())

    def test_incomplete_and_nonlocal_paths_are_rejected(self):
        self.assertIsNone(obs_setup.inspect_obs(self.home / 'missing'))
        self.assertIsNone(obs_setup.inspect_obs(r'\\server\shared\obs64.exe'))
        wrong = self.home / 'obs64.exe'
        wrong.touch()
        self.assertIsNone(obs_setup.inspect_obs(wrong))
