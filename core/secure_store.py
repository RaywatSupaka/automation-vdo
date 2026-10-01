import ctypes
import hashlib
import os
import sys
from ctypes import wintypes


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


def credential_target(target):
    """A frozen smoke test must never read or renew the user's real vault."""
    test_root = os.environ.get('SMARTFLOW_TEST_DATA_ROOT')
    if not test_root:
        return str(target)
    identity = os.path.normcase(os.path.abspath(test_root))
    namespace = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    return f'SmartFlowAI/Test/{namespace}/{target}'


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


class WindowsCredentialStore:
    """Store secrets in Windows Credential Manager for the current Windows account."""

    TARGET = "SmartPostAI/CatfufuExternalTTS"

    def __init__(self, target=None):
        if sys.platform != "win32":
            raise RuntimeError("รองรับการบันทึกคีย์แบบปลอดภัยเฉพาะ Windows")
        self.target = credential_target(target or self.TARGET)
        self._advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
        self._advapi.CredWriteW.restype = wintypes.BOOL
        self._advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIALW)]
        self._advapi.CredReadW.restype = wintypes.BOOL
        self._advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._advapi.CredDeleteW.restype = wintypes.BOOL
        self._advapi.CredFree.argtypes = [ctypes.c_void_p]
        self._advapi.CredFree.restype = None

    def save(self, secret):
        secret = str(secret or "").strip()
        if not secret:
            raise ValueError("กรุณาใส่ API Key ก่อนบันทึก")
        encoded = secret.encode("utf-16-le")
        if len(encoded) > 2560:
            raise ValueError("API Key ยาวเกินขนาดที่ Windows Credential Manager รองรับ")
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        credential = CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self.target
        credential.Comment = "SmartPost AI Voice API Key"
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "SmartPost AI"
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def load(self):
        pointer = PCREDENTIALW()
        if not self._advapi.CredReadW(self.target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            if error == ERROR_NOT_FOUND:
                return ""
            raise ctypes.WinError(error)
        try:
            credential = pointer.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self._advapi.CredFree(pointer)

    def delete(self):
        if self._advapi.CredDeleteW(self.target, CRED_TYPE_GENERIC, 0):
            return True
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return False
        raise ctypes.WinError(error)
