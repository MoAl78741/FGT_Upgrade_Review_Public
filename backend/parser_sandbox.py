"""Fail-closed OS parser confinement: Landlock/seccomp on Linux, Seatbelt on macOS."""
import ctypes
import errno
import os
from pathlib import Path


def confine(job_dir: Path, read_paths: list[Path]):
    import sys
    job_dir = job_dir.resolve()
    read_paths = [p.resolve() for p in read_paths]
    if sys.platform == 'darwin':
        import json
        profile = '(version 1)(deny default)(allow process*)(allow sysctl-read)(allow file-read-metadata)'
        for path in [*read_paths, Path('/System'), Path('/Library/Fonts'), Path('/private/var/db/dyld')]:
            profile += '(allow file-read* (subpath ' + json.dumps(str(path)) + '))'
        profile += '(allow file-read* file-write* (subpath ' + json.dumps(str(job_dir)) + '))'
        sandbox = ctypes.CDLL('/usr/lib/libsandbox.dylib')
        sandbox.sandbox_init.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
        error = ctypes.c_char_p()
        if sandbox.sandbox_init(profile.encode(), 0, ctypes.byref(error)) != 0:
            raise RuntimeError('Unable to enter macOS parser sandbox')
        return
    if sys.platform != 'linux':
        raise RuntimeError('Isolated parsing requires Linux or macOS')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RuntimeError('Unable to disable privilege escalation')
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 1:
        raise RuntimeError('Linux kernel must support Landlock (5.13+)')
    rights = (1 << 13) - 1
    if abi >= 2:
        rights |= 1 << 13
    if abi >= 3:
        rights |= 1 << 14
    class Ruleset(ctypes.Structure):
        _fields_ = [('handled_access_fs', ctypes.c_uint64)]
    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int)]
    rules = Ruleset(rights)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise RuntimeError('Unable to create filesystem sandbox')
    try:
        for path, access in [(p, 4 | 8) for p in read_paths] + [(job_dir, rights)]:
            if not path.exists():
                continue
            opened = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                if not path.is_dir():
                    access &= ~8
                rule = PathRule(access, opened)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) != 0:
                    raise RuntimeError('Unable to configure filesystem sandbox')
            finally:
                os.close(opened)
        if libc.syscall(446, fd, 0) != 0:
            raise RuntimeError('Unable to enter filesystem sandbox')
    finally:
        os.close(fd)
    sec = ctypes.CDLL('libseccomp.so.2')
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    ctx = sec.seccomp_init(0x7fff0000)
    if not ctx:
        raise RuntimeError('Unable to initialize syscall sandbox')
    try:
        for name in [b'socket', b'connect', b'bind', b'listen', b'accept', b'accept4', b'ptrace', b'process_vm_readv', b'process_vm_writev', b'execve', b'execveat', b'io_uring_setup', b'io_uring_enter', b'io_uring_register', b'socketcall']:
            number = sec.seccomp_syscall_resolve_name(name)
            if number >= 0 and sec.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, number, 0) != 0:
                raise RuntimeError('Unable to deny unsafe syscall')
        if sec.seccomp_load(ctx) != 0:
            raise RuntimeError('Unable to enter syscall sandbox')
    finally:
        sec.seccomp_release(ctx)
