import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
import glow_update as update


class UpdateTests(unittest.TestCase):
    def release(self, payload=b'installer'):
        name = 'GlowLetters-0.3.0-Windows-x64-Setup.exe'
        return {'tag_name': 'v0.3.0', 'assets': [{'name': name, 'size': len(payload),
            'digest': 'sha256:' + hashlib.sha256(payload).hexdigest(),
            'browser_download_url': f'https://github.com/{update.REPO}/releases/download/v0.3.0/{name}'}]}

    def test_no_downgrade_or_prerelease(self):
        self.assertIsNone(update.asset(self.release(), '0.3.0'))
        self.assertIsNone(update.asset(self.release(), '0.4.0'))
        release = self.release()
        release['prerelease'] = True
        self.assertIsNone(update.asset(release))

    def test_wrong_origin_and_missing_digest_are_rejected(self):
        release = self.release()
        release['assets'][0]['browser_download_url'] = 'https://example.com/setup.exe'
        with self.assertRaises(ValueError): update.asset(release)
        release = self.release()
        release['assets'][0]['digest'] = None
        with self.assertRaises(ValueError): update.asset(release)

    def test_corrupt_download_is_not_retained(self):
        row = update.asset(self.release())
        response = Mock()
        response.url = row['url']
        response.iter_content.return_value = [b'wrong']
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as folder, patch.object(update.requests, 'get', return_value=response):
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                update.download(row, pathlib.Path(folder))
            self.assertEqual(list(pathlib.Path(folder).iterdir()), [])

    def test_valid_cached_installer_needs_no_download(self):
        row = update.asset(self.release())
        with tempfile.TemporaryDirectory() as folder, patch.object(update.requests, 'get') as get:
            path = pathlib.Path(folder) / row['name']
            path.write_bytes(b'installer')
            self.assertEqual(update.download(row, pathlib.Path(folder)), path)
            get.assert_not_called()

    def test_install_requires_yes(self):
        from glow_qt import GlowWindow, QMessageBox
        window = Mock(language='en')
        result = {'state': 'ready', 'version': '0.3.0', 'path': 'test-setup.exe'}
        with patch('glow_qt.QMessageBox.question', return_value=QMessageBox.No), \
             patch('glow_qt.subprocess.Popen') as launch:
            GlowWindow.on_update(window, result, False)
            launch.assert_not_called()
        with patch('glow_qt.QMessageBox.question', return_value=QMessageBox.Yes), \
             patch('glow_qt.subprocess.Popen') as launch, patch('glow_qt.QApplication.quit') as quit_app:
            GlowWindow.on_update(window, result, False)
            launch.assert_called_once_with(['test-setup.exe'])
            quit_app.assert_called_once()


if __name__ == '__main__': unittest.main()
