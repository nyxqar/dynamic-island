"""Capture of the audio played by one process tree (WASAPI process loopback, Windows 10 2004+ / Windows 11)."""

import ctypes
import threading
import uuid
from ctypes import wintypes

import numpy as np

VT_BLOB = 65
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
BUFFER_DURATION = 200_000  # 20 ms in 100 ns units
WAIT_OBJECT_0 = 0
TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
E_NOINTERFACE = 0x80004002 - 2**32
COINIT_MULTITHREADED = 0
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


class GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    @classmethod
    def of(cls, text):
        guid = cls()
        ctypes.memmove(guid.data, uuid.UUID(text).bytes_le, 16)
        return guid


IID_IUnknown = GUID.of("00000000-0000-0000-C000-000000000046")
IID_IAgileObject = GUID.of("94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90")
IID_IActivateAudioInterfaceCompletionHandler = GUID.of("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_IAudioClient = GUID.of("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")
IID_IAudioCaptureClient = GUID.of("C8ADBD64-E71E-48a0-A4DE-185C395CD317")


class ProcessLoopbackParams(ctypes.Structure):
    _fields_ = [("TargetProcessId", wintypes.DWORD), ("ProcessLoopbackMode", ctypes.c_int)]


class ActivationParams(ctypes.Structure):
    _fields_ = [("ActivationType", ctypes.c_int), ("ProcessLoopbackParams", ProcessLoopbackParams)]


class Blob(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.ULONG), ("pBlobData", ctypes.c_void_p)]


class PropVariant(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("reserved", wintypes.USHORT * 3), ("blob", Blob)]


class WaveFormatEx(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


QueryInterfaceProto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
RefProto = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
ActivateCompletedProto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)


class HandlerVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", QueryInterfaceProto),
        ("AddRef", RefProto),
        ("Release", RefProto),
        ("ActivateCompleted", ActivateCompletedProto),
    ]


class Handler(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.POINTER(HandlerVtbl))]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_ole32 = ctypes.WinDLL("ole32")
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_mmdevapi = ctypes.WinDLL("mmdevapi")
_mmdevapi.ActivateAudioInterfaceAsync.argtypes = [
    wintypes.LPCWSTR, ctypes.POINTER(GUID), ctypes.POINTER(PropVariant), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
]
_mmdevapi.ActivateAudioInterfaceAsync.restype = ctypes.HRESULT


def _method(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)
    func = proto(vtbl[index])
    return lambda *args: func(obj, *args)


def _release(obj):
    if obj:
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        RefProto(vtbl[2])(obj)


def find_root_process(name):
    """PID of the top process named `name` (its parent has another name), or None."""
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, INVALID_HANDLE_VALUE):
        return None
    processes = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        ok = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            processes[entry.th32ProcessID] = (entry.szExeFile.lower(), entry.th32ParentProcessID)
            ok = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snapshot)
    name = name.lower()
    roots = [
        pid for pid, (exe, parent) in processes.items()
        if exe == name and processes.get(parent, ("",))[0] != name
    ]
    return min(roots) if roots else None


def process_alive(pid):
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        _kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == STILL_ACTIVE
    finally:
        _kernel32.CloseHandle(handle)


def _activate(pid):
    done = threading.Event()

    def query_interface(this, riid, out):
        if bytes(riid.contents.data) in (
            bytes(IID_IUnknown.data), bytes(IID_IAgileObject.data), bytes(IID_IActivateAudioInterfaceCompletionHandler.data)
        ):
            out[0] = this
            return 0
        out[0] = None
        return E_NOINTERFACE

    def activate_completed(this, operation):
        done.set()
        return 0

    # The handler lives on the stack of this function until the activation has completed.
    vtbl = HandlerVtbl(QueryInterfaceProto(query_interface), RefProto(lambda this: 1), RefProto(lambda this: 1),
                       ActivateCompletedProto(activate_completed))
    handler = Handler(ctypes.pointer(vtbl))

    params = ActivationParams(
        AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
        ProcessLoopbackParams(pid, PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE),
    )
    prop = PropVariant(vt=VT_BLOB, blob=Blob(ctypes.sizeof(params), ctypes.cast(ctypes.pointer(params), ctypes.c_void_p)))
    operation = ctypes.c_void_p()
    _mmdevapi.ActivateAudioInterfaceAsync(
        "VAD\\Process_Loopback", ctypes.byref(IID_IAudioClient), ctypes.byref(prop),
        ctypes.cast(ctypes.pointer(handler), ctypes.c_void_p), ctypes.byref(operation),
    )
    try:
        if not done.wait(5):
            raise TimeoutError("audio activation timed out")
        result = ctypes.c_long()
        client = ctypes.c_void_p()
        _method(operation, 3, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_void_p))(
            ctypes.byref(result), ctypes.byref(client)
        )
        if result.value < 0:
            raise OSError(f"process loopback activation failed: 0x{result.value & 0xFFFFFFFF:08X}")
        return client
    finally:
        _release(operation)


class ProcessLoopback:
    """Context manager; read() returns mono float32 frames (possibly empty) or None after a timeout."""

    def __init__(self, pid, samplerate, channels=2):
        self.pid = pid
        self.channels = channels
        self.format = WaveFormatEx(1, channels, samplerate, samplerate * channels * 2, channels * 2, 16, 0)
        self.client = self.capture = None
        self.event = None

    def __enter__(self):
        _ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        self.client = _activate(self.pid)
        try:
            _method(self.client, 3, ctypes.c_int, wintypes.DWORD, ctypes.c_longlong, ctypes.c_longlong,
                    ctypes.POINTER(WaveFormatEx), ctypes.c_void_p)(
                AUDCLNT_SHAREMODE_SHARED,
                AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
                BUFFER_DURATION, 0, ctypes.byref(self.format), None,
            )
            self.event = _kernel32.CreateEventW(None, False, False, None)
            _method(self.client, 13, wintypes.HANDLE)(self.event)
            capture = ctypes.c_void_p()
            _method(self.client, 14, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
                ctypes.byref(IID_IAudioCaptureClient), ctypes.byref(capture)
            )
            self.capture = capture
            self._get_buffer = _method(capture, 3, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32),
                                       ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, ctypes.c_void_p)
            self._release_buffer = _method(capture, 4, ctypes.c_uint32)
            self._next_packet = _method(capture, 5, ctypes.POINTER(ctypes.c_uint32))
            _method(self.client, 10)()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def read(self, timeout_ms=200):
        if _kernel32.WaitForSingleObject(self.event, timeout_ms) != WAIT_OBJECT_0:
            return None
        chunks = []
        size = ctypes.c_uint32()
        self._next_packet(ctypes.byref(size))
        while size.value:
            data = ctypes.c_void_p()
            frames = ctypes.c_uint32()
            flags = wintypes.DWORD()
            self._get_buffer(ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags), None, None)
            count = frames.value * self.channels
            if flags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data.value:
                chunk = np.zeros(count, dtype=np.int16)
            else:
                chunk = np.ctypeslib.as_array(ctypes.cast(data, ctypes.POINTER(ctypes.c_int16)), (count,)).copy()
            self._release_buffer(frames.value)
            chunks.append(chunk)
            self._next_packet(ctypes.byref(size))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        samples = np.concatenate(chunks).astype(np.float32) / 32768.0
        return samples.reshape(-1, self.channels).mean(axis=1)

    def __exit__(self, *exc):
        if self.client:
            try:
                _method(self.client, 11)()
            except OSError:
                pass
        _release(self.capture)
        _release(self.client)
        self.capture = self.client = None
        if self.event:
            _kernel32.CloseHandle(self.event)
            self.event = None
