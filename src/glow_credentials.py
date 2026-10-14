"""Store the personal Sunsethue key with Windows DPAPI, never in forecast logs."""
import ctypes
import os
import pathlib

KEY_FILE = pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'GlowLetters' / 'sunsethue-key.dat'


class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(payload, protect=True):
    if os.name != 'nt':
        raise OSError('Encrypted key storage requires Windows')
    buffer = ctypes.create_string_buffer(payload)
    incoming = Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    function = api.CryptProtectData if protect else api.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
    function.restype = ctypes.c_int
    description = ctypes.c_wchar_p('Glow Letters Sunsethue key')
    pointer = ctypes.cast(description, ctypes.c_void_p) if protect else None
    if not function(ctypes.byref(incoming), pointer, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(outgoing.data, ctypes.c_void_p))


def load(path=None):
    if path is None and os.environ.get('SUNSETHUE_API_KEY'):
        return os.environ['SUNSETHUE_API_KEY'].strip()
    try:
        return crypt((path or KEY_FILE).read_bytes(), protect=False).decode('utf-8')
    except (OSError, ValueError, UnicodeError):
        return None


def save(key, path=None):
    key = key.strip()
    if not key or len(key) > 4096 or '\r' in key or '\n' in key:
        raise ValueError('Invalid API key format')
    path = path or KEY_FILE
    payload = crypt(key.encode('utf-8'))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(payload)
    temporary.replace(path)
