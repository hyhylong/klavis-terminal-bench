"""Measure both correct stores through the final unprivileged RPC boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import tempfile
import time

from .calibrate import encoded, verify
from .controller import WorkerSession
from .durablefs import MemoryDurableFS
from .workload import build_workload


LIMITS = dict(timeout_sec=30, max_frame_bytes=8388608, max_memory_bytes=536870912,
              max_fs_operations=100000, max_write_bytes=134217728, cpu_seconds=180)


def package(destination, implementation):
    target = Path(destination) / 'ledgerstore'
    target.mkdir()
    for name in ('domain', 'replay_store', 'incremental_index', 'incremental_store'):
        shutil.copyfile(Path(__file__).with_name(name + '.py'), target / (name + '.py'))
    (target / '__init__.py').write_text(f'from .{implementation} import Store\n')


def run(directory, workload):
    fs = MemoryDurableFS()
    start = time.perf_counter()
    with WorkerSession(directory, fs, **LIMITS) as worker:
        for event in workload['prefix']:
            worker.call('ingest', event)
        loaded = time.perf_counter()
        worker.call('compact')
        worker.call('close')
    fs.crash()
    digest = hashlib.sha256()
    with WorkerSession(directory, fs, **LIMITS) as worker:
        reopened = time.perf_counter()
        for batch in workload['batches']:
            for event in batch['events']:
                worker.call('ingest', event)
            for entity, valid_time in batch['queries']:
                digest.update(encoded(worker.call('lookup', entity, valid_time)) + b'\n')
        queried = time.perf_counter()
        final = worker.call('snapshot', 10**12)
        digest.update(encoded(final))
        done = time.perf_counter()
    return {'load_seconds': loaded - start, 'compact_reopen_seconds': reopened - loaded,
            'stream_seconds': queried - reopened, 'final_snapshot_seconds': done - queried,
            'total_seconds': done - start, 'result_sha256': digest.hexdigest(),
            'filesystem_operations': fs.operation_count, 'storage': fs.storage_stats()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workload = build_workload()
    checked = verify(workload)
    samples = {'memoized_replay': [], 'incremental': []}
    with tempfile.TemporaryDirectory(prefix='ledger-calibration-') as root:
        packages = {}
        for name, module in [('memoized_replay', 'replay_store'), ('incremental', 'incremental_store')]:
            folder = Path(root) / name
            folder.mkdir()
            package(folder, module)
            packages[name] = folder
            run(folder, build_workload(entities=8, versions=3, rounds=4))
        for repeat in range(args.repetitions):
            names = list(samples)
            if repeat % 2:
                names.reverse()
            for name in names:
                result = run(packages[name], workload)
                samples[name].append(result)
                print(f'{name} run {repeat + 1}: stream={result["stream_seconds"]:.4f}s total={result["total_seconds"]:.4f}s', flush=True)
    hashes = {entry['result_sha256'] for entries in samples.values() for entry in entries}
    if len(hashes) != 1:
        raise AssertionError('Isolated stores disagree')
    medians = {name: statistics.median(sample['stream_seconds'] for sample in entries)
               for name, entries in samples.items()}
    output = {'purpose': 'Exploratory isolated calibration; no model results',
              'environment': {'python': platform.python_version(), 'platform': platform.platform()},
              'workload': {'seed': workload['seed'], **workload['parameters'],
                           'input_sha256': hashlib.sha256(encoded(workload)).hexdigest()},
              'worker_limits': LIMITS, 'independent_full_snapshots_checked': checked,
              'samples': samples, 'median_stream_seconds': medians,
              'median_stream_ratio': medians['memoized_replay'] / medians['incremental'],
              'pass_threshold_seconds': None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print('All isolated result hashes match.', flush=True)


if __name__ == '__main__':
    main()
