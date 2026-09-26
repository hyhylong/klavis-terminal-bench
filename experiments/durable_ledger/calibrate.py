"""Measure a fair replay cache and an incremental index on identical streams.

No pass/fail threshold is inferred here. Timings are observations of this host;
the task budget must be separately calibrated inside its published environment.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import time

from .durablefs import MemoryDurableFS
from .incremental_store import Store as IncrementalStore
from .replay_store import Store as ReplayStore
from .workload import build_workload


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def run(store_class, workload):
    fs = MemoryDurableFS()
    start = time.perf_counter()
    store = store_class(fs)
    for event in workload['prefix']:
        store.ingest(event)
    loaded = time.perf_counter()
    store.compact()
    store.close()
    fs.crash()
    store = store_class(fs)
    reopened = time.perf_counter()
    digest = hashlib.sha256()
    for batch in workload['batches']:
        for event in batch['events']:
            store.ingest(event)
        for entity, valid_time in batch['queries']:
            digest.update(encoded(store.lookup(entity, valid_time)) + b'\n')
    queried = time.perf_counter()
    final = store.snapshot(10**12)
    digest.update(encoded(final))
    done = time.perf_counter()
    return {'load_seconds': loaded - start, 'compact_reopen_seconds': reopened - loaded,
            'stream_seconds': queried - reopened, 'final_snapshot_seconds': done - queried,
            'total_seconds': done - start, 'result_sha256': digest.hexdigest(),
            'filesystem_operations': fs.operation_count, 'storage': fs.storage_stats()}


def verify(workload):
    path = Path(__file__).resolve().parents[2] / 'tasks/temporal-ledger-repair/tests/reference.py'
    spec = importlib.util.spec_from_file_location('calibration_independent_reference', path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    store = IncrementalStore(MemoryDurableFS())
    events = list(workload['prefix'])
    for event in events:
        store.ingest(event)
    checked = 0
    selected = {0, len(workload['batches']) // 2, len(workload['batches']) - 1}
    for number, batch in enumerate(workload['batches']):
        for event in batch['events']:
            events.append(event)
            store.ingest(event)
        if number in selected:
            expected = reference.reconstruct(events, [{'id': 'snapshot', 'cutoff': events[-1]['arrival']}])['checkpoints'][0]
            if store.snapshot(events[-1]['arrival']) != expected:
                raise AssertionError(f'Independent reference mismatch after batch {number}')
            checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--entities', type=int, default=192)
    parser.add_argument('--versions', type=int, default=12)
    parser.add_argument('--rounds', type=int, default=180)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workload = build_workload(entities=args.entities, versions=args.versions, rounds=args.rounds)
    verified = verify(workload)
    # Warm the Python/runtime paths equally; never time verification work.
    warmup = build_workload(entities=8, versions=3, rounds=4)
    run(ReplayStore, warmup)
    run(IncrementalStore, warmup)
    samples = {'memoized_replay': [], 'incremental': []}
    for repetition in range(args.repetitions):
        choices = [('memoized_replay', ReplayStore), ('incremental', IncrementalStore)]
        if repetition % 2:
            choices.reverse()
        for name, store_class in choices:
            observation = run(store_class, workload)
            samples[name].append(observation)
            print(f'{name} run {repetition + 1}: stream={observation["stream_seconds"]:.4f}s total={observation["total_seconds"]:.4f}s', flush=True)
    hashes = {sample['result_sha256'] for entries in samples.values() for sample in entries}
    if len(hashes) != 1:
        raise AssertionError('Implementations returned different answers')
    medians = {name: statistics.median(sample['stream_seconds'] for sample in entries)
               for name, entries in samples.items()}
    result = {'purpose': 'Exploratory calibration, not formal task evaluation',
              'environment': {'python': platform.python_version(), 'platform': platform.platform()},
              'workload': {'seed': workload['seed'], **workload['parameters'],
                           'input_sha256': hashlib.sha256(encoded(workload)).hexdigest()},
              'independent_full_snapshots_checked': verified, 'samples': samples,
              'median_stream_seconds': medians,
              'median_stream_ratio': medians['memoized_replay'] / medians['incremental'],
              'pass_threshold_seconds': None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'All result hashes match; {verified} full snapshots match the independent verifier.', flush=True)


if __name__ == '__main__':
    main()
