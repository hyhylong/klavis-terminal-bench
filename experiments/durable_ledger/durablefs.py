"""Trusted, deterministic filesystem model; never touches the host filesystem.

File contents and directory entries have independent durability. ``write`` on
an existing name truncates its existing inode, whereas unlink/create and rename
can change which inode a name denotes. Newly allocated inodes start with empty
durable bytes, so publishing their name without fsync recovers an empty file.

Only the host controller should receive this object. A submitted child receives
the eight filesystem operations through a separate, explicitly limited protocol;
``crash``, image helpers, counters and hooks are host-only facilities.
"""
from collections.abc import Callable, Mapping
import re


AfterOperation = Callable[[str, int], None]
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,96}")


class MemoryDurableFS:
    """A single-client volatile/durable namespace with atomic operations.

    ``after_operation(name, count)`` runs after each successful public filesystem
    operation and before its reply, including reads and listings. Its exception
    propagates without rolling back that operation. A fault controller must kill
    the client before calling ``crash``; this class does not manage processes.
    Failed validation/missing-file calls and host helpers do not advance count.
    """

    def __init__(self, *, after_operation: AfterOperation | None = None):
        self._visible: dict[str, int] = {}
        self._durable_names: dict[str, int] = {}
        self._contents: dict[int, bytes] = {}
        self._durable_contents: dict[int, bytes] = {}
        self._next_inode = 0
        self._operation_count = 0
        self._after_operation = after_operation

    @property
    def operation_count(self) -> int:
        """Successful filesystem calls so far; crashes do not reset the count."""
        return self._operation_count

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str):
            raise TypeError("filename must be a string")
        if not _NAME.fullmatch(name) or name in {".", ".."}:
            raise ValueError("filename must be a plain 1-96 character ASCII name")

    @staticmethod
    def _validate_data(data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError("file contents must be bytes")

    def _inode(self, name: str) -> int:
        self._validate_name(name)
        try:
            return self._visible[name]
        except KeyError:
            raise FileNotFoundError(name) from None

    def _allocate(self, name: str) -> int:
        inode = self._next_inode
        self._next_inode += 1
        self._visible[name] = inode
        self._contents[inode] = b""
        self._durable_contents[inode] = b""
        return inode

    def _completed(self, operation: str) -> None:
        self._operation_count += 1
        if self._after_operation is not None:
            self._after_operation(operation, self._operation_count)

    def read(self, name: str) -> bytes:
        data = self._contents[self._inode(name)]
        self._completed("read")
        return data

    def write(self, name: str, data: bytes) -> None:
        self._validate_name(name)
        self._validate_data(data)
        inode = self._visible[name] if name in self._visible else self._allocate(name)
        self._contents[inode] = data
        self._completed("write")

    def append(self, name: str, data: bytes) -> None:
        self._validate_name(name)
        self._validate_data(data)
        inode = self._visible[name] if name in self._visible else self._allocate(name)
        self._contents[inode] += data
        self._completed("append")

    def fsync(self, name: str) -> None:
        inode = self._inode(name)
        self._durable_contents[inode] = self._contents[inode]
        self._completed("fsync")

    def replace(self, source: str, destination: str) -> None:
        self._validate_name(source)
        self._validate_name(destination)
        inode = self._inode(source)
        if source != destination:
            self._visible[destination] = inode
            del self._visible[source]
        self._completed("replace")

    def unlink(self, name: str) -> None:
        self._inode(name)
        del self._visible[name]
        self._completed("unlink")

    def list_files(self) -> list[str]:
        names = sorted(self._visible)
        self._completed("list_files")
        return names

    def fsync_dir(self) -> None:
        self._durable_names = self._visible.copy()
        # Before directory sync, the old durable mapping may be the only owner
        # of a replaced/unlinked inode. After publication, discard only inodes
        # absent from both namespaces so repeated compaction does not retain
        # every superseded checkpoint payload until the next simulated crash.
        referenced = set(self._visible.values()) | set(self._durable_names.values())
        for inode in self._contents.keys() - referenced:
            del self._contents[inode]
            del self._durable_contents[inode]
        self._completed("fsync_dir")

    def crash(self) -> None:
        """Discard volatile state; retain every inode named durably at the crash."""
        self._visible = self._durable_names.copy()
        self._durable_contents = {
            inode: self._durable_contents[inode]
            for inode in self._durable_names.values()
        }
        self._contents = self._durable_contents.copy()

    def export_image(self) -> dict[str, bytes]:
        """Return detached durable name/byte pairs, excluding volatile changes."""
        return {
            name: self._durable_contents[self._durable_names[name]]
            for name in sorted(self._durable_names)
        }

    def storage_stats(self) -> dict[str, int]:
        """Host metrics: retained inodes and logical bytes in both content states.

        Byte accounting counts volatile and durable contents separately, even if
        Python shares an immutable bytes object. It is not process RSS or a
        contestant resource budget. Reading these metrics is not a filesystem op.
        """
        return {
            "inode_count": len(self._contents),
            "content_bytes": sum(map(len, self._contents.values()))
            + sum(map(len, self._durable_contents.values())),
        }

    @classmethod
    def from_image(
        cls, image: Mapping[str, bytes], *, after_operation: AfterOperation | None = None
    ) -> "MemoryDurableFS":
        """Open a durable image with an identical visible state and zero count."""
        if not isinstance(image, Mapping):
            raise TypeError("image must map filenames to bytes")
        fs = cls(after_operation=after_operation)
        for name, data in image.items():
            fs._validate_name(name)
            fs._validate_data(data)
            inode = fs._allocate(name)
            fs._contents[inode] = data
            fs._durable_contents[inode] = data
        fs._durable_names = fs._visible.copy()
        return fs

    def clone(self, *, after_operation: AfterOperation | None = None) -> "MemoryDurableFS":
        """Copy both states/count, installing only the explicitly supplied hook."""
        other = type(self)(after_operation=after_operation)
        other._visible = self._visible.copy()
        other._durable_names = self._durable_names.copy()
        other._contents = self._contents.copy()
        other._durable_contents = self._durable_contents.copy()
        other._next_inode = self._next_inode
        other._operation_count = self._operation_count
        return other
