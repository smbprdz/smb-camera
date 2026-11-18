import hashlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.prepare_native_lab import safe_file,verify_source,fetch

class NativeInputTests(unittest.TestCase):
    def test_dependency_paths_cannot_escape_with_traversal_or_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'headers';root.mkdir()
            for name in ('../outside.h',str(Path(temp)/'outside.h')):
                with self.assertRaises(ValueError):safe_file(root,name)
            self.assertEqual(safe_file(root,'wil/com.h'),root/'wil/com.h')
    def test_only_the_pinned_source_or_pinned_line_ending_variant_is_accepted(self):
        data=b'// MIT\nint value=1;\n'
        row={'path':'sample.cpp','sha256':hashlib.sha256(data).hexdigest(),'normalized_lf_sha256':hashlib.sha256(data).hexdigest()}
        verify_source(data,row);verify_source(data.replace(b'\n',b'\r\n'),row)
        with self.assertRaises(ValueError):verify_source(data.replace(b'value=1',b'value=2'),row)
    def test_download_is_bounded_even_without_a_content_length(self):
        with patch('tools.prepare_native_lab.urllib.request.urlopen',return_value=io.BytesIO(b'12345')):
            with self.assertRaises(ValueError):fetch('https://example.invalid/source',4)
