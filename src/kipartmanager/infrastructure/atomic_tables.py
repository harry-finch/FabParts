"""Atomic exclusive installs/exchanges, retaining every displaced inode for recovery."""

import ctypes
import errno
import os
import sys
from pathlib import Path

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.workspace_backup import sync_dir


def move(source: Path, target: Path, *, exchange: bool) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        # RENAME_NOFOLLOW_ANY | (RENAME_SWAP or RENAME_EXCL), Darwin sys/stdio.h.
        result = function(os.fsencode(source), os.fsencode(target), 0x10 | (2 if exchange else 4))
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            -100, os.fsencode(source), -100, os.fsencode(target), 2 if exchange else 1
        )
    else:
        raise DomainError("ATOMIC_RENAME_REQUIRED: filesystem/platform not supported")
    if result:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(target))
    sync_dir(source.parent)
    if source.parent != target.parent:
        sync_dir(target.parent)


def replace(path: Path, expected: bytes | None, content: bytes | None, capture: Path) -> None:
    # Local import avoids a dependency cycle; read() refuses links and special files.
    from kipartmanager.infrastructure.kicad_integration import read

    if read(path) != expected:
        raise DomainError("TABLE_CHANGED: external modification; no overwrite")
    if expected == content:
        return
    if expected is not None and (
        path.stat().st_uid != os.geteuid() or not path.stat().st_mode & 0o200
    ):
        raise PermissionError(errno.EACCES, "Table is not user-writable", str(path))
    if capture.exists() or capture.is_symlink() or capture.absolute() != capture.resolve():
        raise DomainError("UNSAFE_PATH: capture path is not private")
    if content is None:
        move(path, capture, exchange=False)
        if read(capture) != expected:
            # Restore only into an absent name. A concurrent replacement is preserved.
            try:
                move(capture, path, exchange=False)
            except OSError:
                pass
            raise DomainError("TABLE_CHANGED: displaced external edit retained")
        return
    with capture.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(capture, path.stat().st_mode & 0o777 if expected is not None else 0o600)
    sync_dir(capture.parent)
    if read(path) != expected:
        raise DomainError("TABLE_CHANGED: external modification before exchange")
    move(capture, path, exchange=expected is not None)
    if expected is not None and read(capture) != expected:
        # Exchange back; any further concurrent inode remains in the capture.
        try:
            move(capture, path, exchange=True)
        except OSError:
            pass
        raise DomainError("TABLE_CHANGED: concurrent bytes preserved; inspect recovery")
    if read(path) != content:
        raise DomainError("TABLE_CHANGED: table changed after exchange")
    # Never unlink displaced inodes: an external writer may still have them open.
