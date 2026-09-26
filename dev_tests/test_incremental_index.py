"""Stateful projection invalidation, checked against an independent replay model."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

from dev_tests.test_oracle import Feed, SCHEMA_TWO, action, row, commit, live
from experiments.durable_ledger.incremental_index import ProjectionIndex

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IncrementalProjectionTests(unittest.TestCase):
    def index(self, feed):
        result = ProjectionIndex()
        for event in feed.events:
            result.add(event)
        return result

    def test_aborting_historical_put_does_not_resurrect_a_later_patch(self):
        feed = Feed()
        feed.tx('base', 10, action('put'))
        feed.tx('later', 20, action('patch', q=7))
        index = self.index(feed)
        self.assertEqual(index.lookup('a', 4)['values']['quota'], 7)
        feed.add('abort', {'tx': 'base'})
        index.add(feed.events[-1])
        self.assertIsNone(index.lookup('a', 4))

    def test_aborting_latest_amendment_reveals_prior_replacement(self):
        feed = Feed()
        feed.tx('base', 10, action('put', q=1))
        target = {'tx': 'base', 'part': 0}
        feed.tx('fix1', 20, {'op': 'amend', 'target': target,
                            'replacement': action('put', q=2)})
        feed.tx('fix2', 30, {'op': 'amend', 'target': target, 'replacement': None})
        index = self.index(feed)
        self.assertIsNone(index.lookup('a', 0))
        feed.add('abort', {'tx': 'fix2'})
        index.add(feed.events[-1])
        self.assertEqual(index.lookup('a', 0), live(0, None, 'fix1/0', {'quota': 2}))

    def test_schema_delivery_wakes_only_previously_ineligible_source_operations(self):
        feed = Feed()
        feed.tx('late-schema', 5, action('put', epoch='two', limit='-0.001'))
        index = self.index(feed)
        self.assertIsNone(index.lookup('a', 0))
        feed.add('schema', SCHEMA_TWO)
        index.add(feed.events[-1])
        self.assertEqual(index.lookup('a', 0)['values']['quota'], -1)
        self.assertEqual(index.snapshot()['transactions'][0]['state'], 'applied')

    def test_conflicting_duplicate_retracts_previously_applied_rows(self):
        feed = Feed()
        feed.tx('base', 1, action('put', entity='a'), action('put', entity='b'))
        index = self.index(feed)
        self.assertIsNotNone(index.lookup('b', 0))
        feed.add('row', row('base', 0, action('put', q=999)))
        index.add(feed.events[-1])
        self.assertIsNone(index.lookup('a', 0))
        self.assertIsNone(index.lookup('b', 0))
        self.assertEqual(index.snapshot()['transactions'][0]['reason'], 'conflicting_row')

    def test_caller_cannot_mutate_accepted_input_or_returned_cache(self):
        feed = Feed()
        feed.tx('base', 1, action('put'))
        index = self.index(feed)
        feed.events[1]['body']['action']['values']['q'] = 123
        first = index.lookup('a', 1)
        first['values']['quota'] = 456
        snapshot = index.snapshot()
        snapshot['entities'][0]['segments'][0]['origins']['quota'] = 'wrong/0'
        self.assertEqual(index.lookup('a', 1), live(0, None, 'base/0'))

    def test_every_generated_prefix_matches_independent_pointwise_replay(self):
        verifier = load('incremental_truth', 'tasks/temporal-ledger-repair/tests/reference.py')
        generator = load('incremental_corpus', 'tools/generate_corpus.py')
        for seed in (20260926, 41):
            events, _ = generator.build_corpus(seed)
            index = ProjectionIndex()
            prefix = []
            for event in events:
                prefix.append(event)
                index.add(event)
                expected = verifier.reconstruct(prefix, [{'id': 'snapshot', 'cutoff': event['arrival']}])['checkpoints'][0]
                self.assertEqual(index.snapshot(), expected, (seed, event['arrival']))
                for entity in expected['entities'][::7]:
                    for segment in entity['segments']:
                        self.assertEqual(index.lookup(entity['entity'], segment['from']), segment)


if __name__ == '__main__':
    unittest.main()
