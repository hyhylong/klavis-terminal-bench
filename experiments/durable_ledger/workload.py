"""Deterministic streaming workload for measuring legitimate replay alternatives."""
from copy import deepcopy
import hashlib
import json
import random


def build_workload(seed=41, entities=192, versions=12, rounds=180, queries_per_round=12):
    randomizer = random.Random(seed)
    events = []
    sequence = 0
    rows_by_id = {}
    names = [f'account-{number:04d}' for number in range(entities)]
    schema = {'epoch': 'billing-v1', 'fields': {
        'tier': {'name': 'tier', 'codec': 'text', 'default': 'basic'},
        'region': {'name': 'region', 'codec': 'text', 'default': 'eu'},
        'quota': {'name': 'quota', 'codec': 'integer', 'default': 1000},
        'enabled': {'name': 'enabled', 'codec': 'boolean', 'default': True},
        'note': {'name': 'note', 'codec': 'nullable_text', 'default': None}}}

    def add(kind, body):
        event = {'arrival': len(events) + 1, 'kind': kind, 'body': deepcopy(body)}
        events.append(event)
        return event

    def seal(tx, operation):
        nonlocal sequence
        sequence += 1
        row = {'tx': tx, 'part': 0, 'action': operation}
        wire = json.dumps([row], sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        add('row', row)
        add('commit', {'tx': tx, 'seq': sequence, 'parts': 1,
                       'sha256': hashlib.sha256(wire.encode()).hexdigest()})
        return row

    add('schema', schema)
    for version in range(versions):
        for number, name in enumerate(names):
            tx = f'source-{number:04d}-{version:03d}'
            operation = {'op': 'put' if version == 0 else 'patch', 'entity': name,
                         'from': 0 if version == 0 else version * 7,
                         'to': None if version == 0 else version * 7 + 43,
                         'epoch': 'billing-v1',
                         'values': {'quota': 1000 + number + version, 'note': f'v{version}'}}
            rows_by_id[tx] = seal(tx, operation)
    prefix = deepcopy(events)
    batches = []
    source_ids = list(rows_by_id)
    for round_number in range(rounds):
        start = len(events)
        target = randomizer.choice(source_ids)
        if round_number % 7 == 0:
            add('abort', {'tx': target})
        else:
            replacement = deepcopy(rows_by_id[target]['action'])
            replacement['values']['quota'] = -round_number
            replacement['values']['note'] = f'correction-{round_number}'
            if round_number % 11 == 0:
                replacement = None
            seal(f'correction-{round_number:05d}',
                 {'op': 'amend', 'target': {'tx': target, 'part': 0},
                  'replacement': replacement})
        queries = [[rows_by_id[target]['action']['entity'], randomizer.randrange(versions * 7 + 50)]]
        queries.extend([[randomizer.choice(names), randomizer.randrange(versions * 7 + 50)]
                        for _ in range(queries_per_round - 1)])
        batches.append({'events': deepcopy(events[start:]), 'queries': queries})
    return {'seed': seed, 'prefix': prefix, 'batches': batches,
            'parameters': {'entities': entities, 'versions': versions, 'rounds': rounds,
                           'queries_per_round': queries_per_round}}
