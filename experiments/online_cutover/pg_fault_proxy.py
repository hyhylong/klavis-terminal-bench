"""Trusted PostgreSQL TCP fault fixture; never imported by submitted code.

Point only the migration process's target DSN at ``127.0.0.1:proxy.port`` and
explicitly set ``sslmode=disable gssencmode=disable``. TLS/GSS negotiation is
unsupported and closes that connection with a metadata-only protocol_error.

The proxy forwards framed bytes without decoding SQL, credentials, rows or
authentication. Payload bytes exist only in transient forwarding buffers, never
events or logs. A backend CommandComplete with exact tag COMMIT is numbered in
the order the proxy observes complete frames across its connections. This is
not a database transaction sequence or a claim about concurrent commit order.

``fail_commit=N`` drops that one acknowledgement and closes both sockets of its
connection after receiving the server's response. Later connections operate
normally. ``ack_dropped=False`` means no intentional fault, not guaranteed client
receipt. The upstream server's durability settings still govern durability.

Protocol reference: https://www.postgresql.org/docs/17/protocol-message-formats.html
"""

from copy import deepcopy
import socket
import struct
import threading
import time


MAX_FRAME_LENGTH = 16 * 1024 * 1024  # PostgreSQL Int32 length, including itself.
_POLL_SECONDS = 0.1


class _Closed(Exception):
    pass


class _ProtocolError(Exception):
    """Only constant diagnostic reasons, never packet content."""


class _Pair:
    def __init__(self, number, client):
        self.number = number
        self.client = client
        self.upstream = None
        self.closed = threading.Event()
        self.lock = threading.Lock()

    def attach(self, upstream):
        with self.lock:
            if self.closed.is_set():
                upstream.close()
                raise _Closed()
            self.upstream = upstream

    def close(self):
        with self.lock:
            self.closed.set()
            for stream in (self.client, self.upstream):
                if stream is not None:
                    try:
                        stream.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    stream.close()


def _read(stream, size, pair):
    result = bytearray()
    while len(result) < size:
        if pair.closed.is_set():
            raise _Closed()
        try:
            part = stream.recv(min(size - len(result), 65536))
        except socket.timeout:
            continue
        if not part:
            raise _Closed()
        result.extend(part)
    return bytes(result)


def _send(stream, data, pair):
    remaining = memoryview(data)
    while remaining:
        if pair.closed.is_set():
            raise _Closed()
        try:
            sent = stream.send(remaining)
        except socket.timeout:
            continue
        if sent == 0:
            raise _Closed()
        remaining = remaining[sent:]


def _message(stream, pair):
    header = _read(stream, 5, pair)
    length = struct.unpack("!I", header[1:])[0]
    if not 4 <= length <= MAX_FRAME_LENGTH:
        raise _ProtocolError("invalid_frame_length")
    return header, _read(stream, length - 4, pair)


class PostgresFaultProxy:
    """A loopback listener with bounded, idempotent context-manager cleanup.

    ``events`` returns owned metadata copies. Commit events contain event,
    connection, ordinal and ack_dropped. Malformed/encrypted connections append
    protocol_error plus a constant reason and direction, then close. Unexpected
    network failures append transport_error without exception text or payloads.
    A proxy instance may be entered only once; ``close()`` is idempotent.
    """

    def __init__(self, upstream_host, upstream_port, fail_commit=None):
        if fail_commit is not None and (type(fail_commit) is not int or fail_commit < 1):
            raise ValueError("fail_commit must be a positive integer or None")
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.fail_commit = fail_commit
        self.port = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener = None
        self._threads = set()
        self._pairs = set()
        self._events = []
        self._connection_count = 0
        self._commit_count = 0
        self._fault_fired = False
        self._entered = False

    @property
    def events(self):
        with self._lock:
            return deepcopy(self._events)

    def _spawn(self, function, *args):
        def run():
            try:
                function(*args)
            finally:
                with self._lock:
                    self._threads.discard(threading.current_thread())

        worker = threading.Thread(target=run, name="pg-fault-proxy", daemon=True)
        with self._lock:
            if self._stop.is_set():
                return False
            self._threads.add(worker)
            worker.start()
        return True

    def __enter__(self):
        if self._entered or self._stop.is_set():
            raise RuntimeError("a proxy instance may be entered only once")
        self._entered = True
        listener = socket.socket()
        self._listener = listener
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(32)
            listener.settimeout(_POLL_SECONDS)
            self.port = listener.getsockname()[1]
            self._spawn(self._accept)
            return self
        except BaseException:
            self.close()
            raise

    def _accept(self):
        while not self._stop.is_set():
            try:
                client, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            client.settimeout(_POLL_SECONDS)
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                self._connection_count += 1
                pair = _Pair(self._connection_count, client)
                self._pairs.add(pair)
            if not self._spawn(self._guard, pair, "frontend", self._frontend):
                pair.close()
                with self._lock:
                    self._pairs.discard(pair)

    def _guard(self, pair, direction, function):
        try:
            function(pair)
        except _ProtocolError as error:
            with self._lock:
                self._events.append({"event": "protocol_error", "connection": pair.number,
                                     "direction": direction, "reason": error.args[0]})
        except _Closed:
            pass
        except OSError:
            if not pair.closed.is_set() and not self._stop.is_set():
                with self._lock:
                    self._events.append({"event": "transport_error", "connection": pair.number,
                                         "direction": direction, "reason": "connection_lost"})
        finally:
            pair.close()
            with self._lock:
                self._pairs.discard(pair)

    def _frontend(self, pair):
        length_bytes = _read(pair.client, 4, pair)
        length = struct.unpack("!I", length_bytes)[0]
        if not 8 <= length <= MAX_FRAME_LENGTH:
            raise _ProtocolError("invalid_startup_length")
        payload = _read(pair.client, length - 4, pair)
        code = struct.unpack("!I", payload[:4])[0]
        if code == 80877103:
            raise _ProtocolError("ssl_not_supported")
        if code == 80877104:
            raise _ProtocolError("gss_not_supported")
        upstream = socket.create_connection((self.upstream_host, self.upstream_port), timeout=1)
        upstream.settimeout(_POLL_SECONDS)
        upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        pair.attach(upstream)
        _send(upstream, length_bytes + payload, pair)
        del payload
        if not self._spawn(self._guard, pair, "backend", self._backend):
            return
        while not pair.closed.is_set():
            header, payload = _message(pair.client, pair)
            _send(upstream, header, pair)
            _send(upstream, payload, pair)
            del header, payload  # Do not retain a previous request while idle.

    def _backend(self, pair):
        while not pair.closed.is_set():
            header, payload = _message(pair.upstream, pair)
            if header[:1] == b"C" and payload == b"COMMIT\0":
                with self._lock:
                    self._commit_count += 1
                    drop = self._commit_count == self.fail_commit and not self._fault_fired
                    self._fault_fired = self._fault_fired or drop
                    self._events.append({"event": "commit", "connection": pair.number,
                                         "ordinal": self._commit_count, "ack_dropped": drop})
                if drop:
                    return
            _send(pair.client, header, pair)
            _send(pair.client, payload, pair)
            del header, payload  # Do not retain a previous data/auth response.

    def close(self):
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        with self._lock:
            pairs = list(self._pairs)
        for pair in pairs:
            pair.close()
        deadline = time.monotonic() + 3
        while True:
            with self._lock:
                workers = list(self._threads)
            if not workers:
                return
            for worker in workers:
                worker.join(max(0, deadline - time.monotonic()))
            if time.monotonic() >= deadline:
                with self._lock:
                    if self._threads:
                        raise RuntimeError("PostgreSQL proxy workers did not stop within cleanup bound")

    def __exit__(self, exc_type, exc, traceback):
        self.close()
