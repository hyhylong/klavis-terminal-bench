"""Durable full-replay baseline with one current projection per revision.

Every accepted envelope remains in a source checkpoint or its generation WAL.
Compaction publishes a complete new generation before retiring old files.
All persistent I/O goes through the injected filesystem, never the host FS.
"""

import copy
import hashlib
import json
import re
import struct

from . import domain


FORMAT = 1
MANIFEST = "MANIFEST"
TEMP_MANIFEST = "MANIFEST.tmp"
GENERATION_FILE = re.compile(r"(?:checkpoint-([0-9]+)\.json|wal-([0-9]+)\.log)\Z")


def _json_bytes(value):
    return domain.canonical(value).encode("utf-8")


def _frame(payload):
    return struct.pack(">I", len(payload)) + payload + hashlib.sha256(payload).digest()


def _wal_records(contents):
    """Return complete verified records and the length of their byte prefix.

    An incomplete final frame was not acknowledged and is recoverable. A full
    frame with an invalid checksum is corruption, not an incomplete delivery.
    """
    events = []
    offset = 0
    while len(contents) - offset >= 4:
        size = struct.unpack_from(">I", contents, offset)[0]
        end = offset + 4 + size + 32
        if end > len(contents):
            break
        payload = contents[offset + 4:offset + 4 + size]
        digest = contents[offset + 4 + size:end]
        if hashlib.sha256(payload).digest() != digest:
            raise ValueError("Corrupt complete WAL frame")
        events.append(json.loads(payload))
        offset = end
    return events, offset


class Store:
    def __init__(self, fs):
        self.fs = fs
        self._events = []
        self._accepted = {}
        self._current_cache = None
        self._generation = 0
        try:
            manifest_bytes = fs.read(MANIFEST)
        except FileNotFoundError:
            self._install_generation()
            return

        manifest = json.loads(manifest_bytes)
        generation = manifest["generation"]
        if (manifest["format"] != FORMAT or type(generation) is not int or generation < 0
                or manifest["checkpoint"] != f"checkpoint-{generation}.json"
                or manifest["wal"] != f"wal-{generation}.log"):
            raise ValueError("Unsupported or inconsistent ledger manifest")
        self._generation = generation
        self._checkpoint_name = manifest["checkpoint"]
        self._wal_name = manifest["wal"]
        source = json.loads(fs.read(self._checkpoint_name))
        if source["format"] != FORMAT or source["generation"] != generation:
            raise ValueError("Ledger checkpoint does not match its manifest")
        for event in source["events"]:
            self._remember(event)
        contents = fs.read(self._wal_name)
        records, complete_length = _wal_records(contents)
        for event in records:
            self._remember(event)
        if complete_length != len(contents):
            # Otherwise a later acknowledged append would sit behind an unreadable
            # partial frame and disappear on the following restart.
            fs.write(self._wal_name, contents[:complete_length])
            fs.fsync(self._wal_name)

    def _validate_arrival(self, event, payload):
        arrival = event["arrival"]
        if type(arrival) is not int or arrival <= 0:
            raise ValueError("Arrival must be a positive integer")
        if arrival in self._accepted:
            if self._accepted[arrival] != payload:
                raise ValueError("Conflicting retry at an accepted arrival")
            return False
        if self._events and arrival <= self._events[-1]["arrival"]:
            raise ValueError("Previously unseen arrivals must increase")
        return True

    def _remember(self, event, payload=None):
        if payload is None:
            payload = _json_bytes(event)
        if self._validate_arrival(event, payload):
            owned = json.loads(payload)
            self._events.append(owned)
            self._accepted[owned["arrival"]] = payload
            self._current_cache = None

    def ingest(self, event):
        payload = _json_bytes(event)
        if not self._validate_arrival(event, payload):
            return
        self.fs.append(self._wal_name, _frame(payload))
        # The generation's WAL name was durably installed before it was used.
        # Persisting its inode is therefore sufficient for this acknowledgement.
        self.fs.fsync(self._wal_name)
        self._remember(event, payload)

    def _current(self):
        if self._current_cache is None:
            latest = self._events[-1]["arrival"] if self._events else 0
            self._current_cache = domain.checkpoint(self._events, {"id": "snapshot", "cutoff": latest})
        return self._current_cache

    def snapshot(self, cutoff):
        latest = self._events[-1]["arrival"] if self._events else 0
        if cutoff >= latest:
            return copy.deepcopy(self._current())
        return domain.checkpoint(self._events, {"id": "snapshot", "cutoff": cutoff})

    def lookup(self, entity, valid_time):
        for record in self._current()["entities"]:
            if record["entity"] != entity:
                continue
            for segment in record["segments"]:
                if segment["from"] <= valid_time and (segment["to"] is None or valid_time < segment["to"]):
                    return copy.deepcopy(segment)
            break
        return None

    def _install_generation(self):
        visible = self.fs.list_files()
        generations = [self._generation]
        for name in visible:
            match = GENERATION_FILE.fullmatch(name)
            if match:
                generations.append(int(match.group(1) or match.group(2)))
        generation = max(generations) + 1
        checkpoint_name, wal_name = f"checkpoint-{generation}.json", f"wal-{generation}.log"
        checkpoint = {"format": FORMAT, "generation": generation, "events": self._events}
        self.fs.write(checkpoint_name, _json_bytes(checkpoint) + b"\n")
        self.fs.fsync(checkpoint_name)
        self.fs.write(wal_name, b"")
        self.fs.fsync(wal_name)
        # A manifest must never durably name a missing checkpoint or WAL inode.
        self.fs.fsync_dir()

        manifest = {"format": FORMAT, "generation": generation, "checkpoint": checkpoint_name, "wal": wal_name}
        self.fs.write(TEMP_MANIFEST, _json_bytes(manifest) + b"\n")
        self.fs.fsync(TEMP_MANIFEST)
        self.fs.replace(TEMP_MANIFEST, MANIFEST)
        self.fs.fsync_dir()
        self._generation = generation
        self._checkpoint_name, self._wal_name = checkpoint_name, wal_name

        # This begins only after the new manifest is durable. A crash during
        # retirement can leave extra files, but cannot destroy the active state.
        retired = False
        for name in visible:
            if GENERATION_FILE.fullmatch(name) and name not in (checkpoint_name, wal_name):
                self.fs.unlink(name)
                retired = True
        if retired:
            self.fs.fsync_dir()

    def compact(self):
        self._install_generation()

    def close(self):
        # No open host handles or buffered writes: every ingest acknowledged its
        # own durability, and the in-memory cache is only a disposable view.
        return None
