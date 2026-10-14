"""Download a newer public release; installation always needs a UI confirmation."""
import hashlib
import os
import pathlib
import re
import tempfile
from urllib.parse import urlparse
import requests

VERSION = '0.2.1'
REPO = 'isCharles/glow-letters'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
CACHE = pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'GlowLetters' / 'updates'
HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'GlowLetters/' + VERSION}


def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    if not match:
        raise ValueError('Invalid release version')
    return tuple(int(part) for part in match.groups())


def asset(release, current=VERSION):
    if release.get('draft') or release.get('prerelease'):
        return None
    tag = release.get('tag_name', '')
    if version(tag) <= version(current):
        return None
    number = tag.removeprefix('v')
    name = f'GlowLetters-{number}-Windows-x64-Setup.exe'
    row = next((item for item in release.get('assets', []) if item.get('name') == name), None)
    if not row:
        raise ValueError('Installer missing')
    digest = row.get('digest', '')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        raise ValueError('Release has no SHA-256 digest')
    url = row.get('browser_download_url')
    expected = f'https://github.com/{REPO}/releases/download/{tag}/{name}'
    if url != expected:
        raise ValueError('Unexpected installer URL')
    size = row.get('size')
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= 200_000_000:
        raise ValueError('Unexpected installer size')
    return {'version': number, 'name': name, 'url': url, 'size': size, 'sha256': digest[7:].lower()}


def valid_file(path, row):
    if not path.is_file() or path.is_symlink() or path.stat().st_size != row['size']:
        return False
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return digest == row['sha256']


def download(row, directory=CACHE):
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / row['name']
    if valid_file(destination, row):
        return destination
    temporary = None
    try:
        with requests.get(row['url'], headers=HEADERS, stream=True, timeout=(5, 30)) as response:
            response.raise_for_status()
            host = urlparse(response.url).hostname or ''
            if host != 'github.com' and not host.endswith('.githubusercontent.com'):
                raise ValueError('Unexpected download host')
            with tempfile.NamedTemporaryFile(dir=directory, suffix='.part', delete=False) as stream:
                temporary = pathlib.Path(stream.name)
                count = 0
                for chunk in response.iter_content(65536):
                    count += len(chunk)
                    if count > row['size']:
                        raise ValueError('Installer exceeds declared size')
                    stream.write(chunk)
        if not valid_file(temporary, row):
            raise ValueError('Installer digest/size mismatch')
        temporary.replace(destination)
        return destination
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def check(current=VERSION, directory=CACHE):
    response = requests.get(API, headers=HEADERS, timeout=(5, 15))
    response.raise_for_status()
    row = asset(response.json(), current)
    if row is None:
        return {'state': 'current'}
    return {'state': 'ready', 'version': row['version'], 'path': str(download(row, directory))}
