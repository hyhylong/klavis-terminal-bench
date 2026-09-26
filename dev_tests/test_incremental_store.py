"""Persistence and projection must agree through retries, compaction and reopen."""
import unittest

from dev_tests.test_replay_store import correction_history, expected_patched, REFERENCE
from experiments.durable_ledger.durablefs import MemoryDurableFS
from experiments.durable_ledger.incremental_store import Store
from experiments.durable_ledger.workload import build_workload


class IncrementalStoreTests(unittest.TestCase):
    def test_late_abort_after_compaction_and_restart_reveals_original_history(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        events = correction_history()
        for event in events[:-1]:
            store.ingest(event)
        self.assertIsNone(store.lookup('a', 4))
        store.compact()
        fs.crash()
        store = Store(fs)
        store.ingest(events[-1])
        self.assertEqual(store.snapshot(8), expected_patched(True))
        self.assertEqual(store.snapshot(5), expected_patched())
        self.assertEqual(store.lookup('a', 4)['values']['tier'], 'gold')

    def test_duplicate_and_rejected_conflict_do_not_change_projection(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        event = correction_history()[0]
        store.ingest(event)
        original = store.snapshot(100)
        count = fs.operation_count
        store.ingest(event)
        self.assertEqual(fs.operation_count, count)
        with self.assertRaises(ValueError):
            store.ingest({'arrival': 1, 'kind': 'abort', 'body': {'tx': 'base'}})
        self.assertEqual(store.snapshot(100), original)

    def test_streaming_workload_matches_independent_reference_across_restarts(self):
        workload = build_workload(entities=10, versions=5, rounds=20, queries_per_round=8)
        fs = MemoryDurableFS()
        store = Store(fs)
        events = list(workload['prefix'])
        for event in events:
            store.ingest(event)
        for number, batch in enumerate(workload['batches']):
            for event in batch['events']:
                events.append(event)
                store.ingest(event)
            expected = REFERENCE.reconstruct(events, [{'id': 'snapshot', 'cutoff': events[-1]['arrival']}])['checkpoints'][0]
            self.assertEqual(store.snapshot(events[-1]['arrival']), expected)
            for entity, time in batch['queries']:
                answer = None
                for record in expected['entities']:
                    if record['entity'] == entity:
                        answer = next((part for part in record['segments'] if part['from'] <= time and
                                       (part['to'] is None or time < part['to'])), None)
                self.assertEqual(store.lookup(entity, time), answer)
            if number % 4 == 0:
                store.compact()
                fs.crash()
                store = Store(fs)


if __name__ == '__main__':
    unittest.main()
