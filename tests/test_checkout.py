"""A real Git checkout must preserve hash-bound LF and retained CRLF bytes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git'), 'Git is required for the checkout regression')
class CheckoutTests(unittest.TestCase):
    def test_autocrlf_checkout_preserves_both_original_line_endings(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            original, checkout = base / 'original', base / 'checkout with spaces'
            original.mkdir()
            environment = os.environ.copy()
            environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

            def git(*arguments):
                return subprocess.run(['git', *arguments], env=environment, capture_output=True,
                                      check=True, timeout=30)

            payloads = {
                '.gitattributes': (ROOT / '.gitattributes').read_bytes(),
                'source.txt': b'First evidence line.\nSecond evidence line.\n',
                'retained-report.json': b'{\r\n  "historical": true\r\n}\r\n',
                'figure.png': b'\x89PNG\r\n\x1a\n\x00original binary bytes\x00',
            }
            for relative, data in payloads.items():
                (original / relative).write_bytes(data)
            git('-C', str(original), 'init', '-q')
            git('-C', str(original), '-c', 'core.autocrlf=true', 'add', '.')
            git('-C', str(original), '-c', 'user.name=Checkout Fixture',
                '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                'commit', '-q', '-m', 'Create local checkout fixture')
            git('-c', 'core.autocrlf=true', 'clone', '-q', '--no-local', str(original), str(checkout))
            for relative, data in payloads.items():
                with self.subTest(relative=relative):
                    self.assertEqual((checkout / relative).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
