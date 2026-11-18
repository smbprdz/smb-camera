from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ucs import nvidia_vfx


class NvidiaRuntimeTests(unittest.TestCase):
    def test_missing_and_valid_locally_selected_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / 'docs'
            docs.mkdir()
            payload = b'placeholder tested without loading a DLL'
            manifest = {'files': [{'path': 'required.dll', 'bytes': len(payload),
                                  'sha256': hashlib.sha256(payload).hexdigest()}]}
            (docs/'NVIDIA-VFX.lock.json').write_text(json.dumps(manifest))
            default = root/'runtime/default'
            preference = root/'runtime/nvidia-vfx-location.txt'
            with patch.multiple(nvidia_vfx, ROOT=root, DEFAULT_RUNTIME=default,
                                RUNTIME_CHOICE=preference):
                self.assertEqual(nvidia_vfx.runtime_error(), nvidia_vfx.RUNTIME_MISSING)
                with self.assertRaises(RuntimeError):
                    nvidia_vfx.select_runtime(root)
                self.assertFalse(preference.exists())
                alternate = root/'verified SDK'
                alternate.mkdir()
                (alternate/'required.dll').write_bytes(payload)
                nvidia_vfx.select_runtime(alternate)
                self.assertEqual(nvidia_vfx.runtime_folder(), alternate)
                self.assertEqual(nvidia_vfx.runtime_error(), '')
                (alternate/'required.dll').write_text('truncated')
                self.assertEqual(nvidia_vfx.runtime_error(), nvidia_vfx.RUNTIME_MISSING)

    def test_worker_reports_missing_runtime_without_exposing_paths(self):
        script = '''
from pathlib import Path
from ucs import nvidia_vfx, matting_inference
import sys
nvidia_vfx.DEFAULT_RUNTIME = Path(sys.argv[1]) / 'missing'
nvidia_vfx.RUNTIME_CHOICE = Path(sys.argv[1]) / 'missing-choice'
sys.argv = ['check', '--backend', 'nvidia']
matting_inference.main()
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-c', script, directory],
                                    capture_output=True, input=b'', timeout=15, check=True)
        self.assertEqual(result.stdout[:4], b'FAIL')
        expected = nvidia_vfx.RUNTIME_MISSING.encode('utf8')
        self.assertEqual(int.from_bytes(result.stdout[4:8], 'big'), len(expected))
        self.assertEqual(result.stdout[8:], expected)
