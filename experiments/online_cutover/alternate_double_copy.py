"""Development-only alternate migrator; never include this in a task starter.

This is the callable export of the observed 19-line inline controller.  It
reuses 44 physical lines of reference helpers: copy_snapshot (33), is_active
(3), and ensure_routing (8), measured in review-probe.json.  Those 63 lines
exclude this documentation/CLI wrapper and the existing service, routing,
receipt handling, and transaction code on which the algorithm depends.

The first complete copy runs while the source accepts writes.  A second
complete copy runs under the same source fence that the existing service
honors, then atomically activates the target before releasing that fence.
No change queue or sequence watermark is required for these small workloads.
This is a legitimate-alternative regression, not a production latency claim
or evidence about how a model will perform on the complete coding task.
"""

import argparse
import json
import time

import psycopg

from orderbridge.backend import ensure_routing
from orderbridge.migrate import NAMESPACE, copy_snapshot, is_active


def migrate(source_dsn: str, target_dsn: str) -> dict:
    """Run the proven double-copy algorithm, returning sanitized timing data.

    final_fence_seconds starts after acquiring the source fence and ends after
    committing target activation.  It excludes lock-acquisition waiting, fence
    release, HTTP latency, process startup, and a production workload margin.
    Connections are scoped to this invocation; exceptions remain visible to
    the caller and retries use the target's durable activation state.
    """
    ensure_routing(source_dsn, target_dsn)
    with psycopg.connect(target_dsn, autocommit=True) as target:
        target.execute("SELECT pg_advisory_lock(%s,2)", (NAMESPACE,))
        if is_active(target):
            return {"already_active": True}
        copy_snapshot(source_dsn, target)
        with psycopg.connect(source_dsn, autocommit=True) as fence:
            fence.execute("SELECT pg_advisory_lock(%s,1)", (NAMESPACE,))
            started = time.perf_counter()
            copy_snapshot(source_dsn, target)
            with target.transaction():
                target.execute("UPDATE app.bridge_state SET active=true WHERE singleton=1")
            held = time.perf_counter() - started
        return {"already_active": False, "final_fence_seconds": held}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(migrate(args.source, args.target)))


if __name__ == "__main__":
    main()
