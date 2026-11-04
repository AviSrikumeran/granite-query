"""Versioned accounting for proven zero-valued native envelope transfers.

The immutable legacy accountant remains unchanged. Only a complete, balanced
native transfer DAG may normalize a superseded ZERO envelope in a planning
copy. Real statuses, audit receipts and historical child allowances survive.
No import or pure reconciliation function queries providers or writes files.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

from cloud import budget_reconcile as legacy

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / 'runs'
STATE = PRIVATE / 'supervisor'
VERSION = 'native-transfer-aware-accounting-v1'
V2 = 'native-reasoning-unused-envelope-migration-v2'
V3 = 'native-reasoning-config-stage-funding-v3'
HEX = re.compile(r'[0-9a-f]{64}\Z')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z')
V2_KEYS = set(('version original_envelope_id new_envelope_id migrated_usd new_reservation_created '
    'old_failed_child_run_id old_failed_child_allowance_held_usd original_failure new_design_sha256 '
    'new_manifest_sha256 recovery_review_sha256 new_source_sha256 remote_owner_absent remote_artifacts_absent '
    'validated_outputs created_at_utc migration_sha256').split())
V3_KEYS = set(('version parent_envelope_id new_envelope_id transferred_unused_usd additional_new_reservation_usd '
    'funded_envelope_usd new_reservation_created total_commitment_increase_usd parent_failed_child_run_id '
    'v1_failed_child_run_id historical_failed_allowance_each_usd parent_failure config_proof '
    'parent_migration_receipt_sha256 new_design_sha256 new_manifest_sha256 config_recovery_review_sha256 '
    'new_source_sha256 parent_remote_owner_and_artifacts_exist parent_mount_source_tokenizer_verified '
    'validated_outputs created_at_utc funding_sha256').split())


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value): return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()
def _file_bytes(value): return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
def _file_digest(value): return hashlib.sha256(_file_bytes(value)).hexdigest()


def _money(value):
    if isinstance(value, bool): raise ValueError('Boolean is not a monetary amount')
    try: result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError): raise ValueError('Malformed monetary amount') from None
    if not result.is_finite() or result < 0: raise ValueError('Finite nonnegative USD required')
    return result


def _hash(value): return isinstance(value, str) and HEX.fullmatch(value) is not None


def _inventory(value):
    if (not isinstance(value, dict) or not 1 <= len(value) <= 64
            or any(not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.py', key)
                or not _hash(item) for key, item in value.items())):
        raise ValueError('Bounded exact source hash inventory required')


def _stamp(value):
    if not isinstance(value, str): raise ValueError('Transfer timestamp must be explicit text')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('Transfer timestamp needs a timezone')
    return result


def _id(value):
    if not isinstance(value, str) or not NAME.fullmatch(value) or not value.endswith('-envelope'):
        raise ValueError('Explicit native envelope identity required')
    return value


def _edges(ledger):
    jobs = ledger.get('jobs')
    if not isinstance(jobs, list) or any(not isinstance(job, dict) or not isinstance(job.get('run_id'), str) for job in jobs):
        raise ValueError('Explicit unique accounting job identities required')
    if len({job['run_id'] for job in jobs}) != len(jobs): raise ValueError('Duplicate accounting job identity')
    by_id = {job['run_id']: job for job in jobs}
    records = {}
    for job in jobs:
        for key in ('native_migration', 'native_config_funding'):
            if key not in job: continue
            record = job[key]
            if not isinstance(record, dict): raise ValueError('Native transfer receipt must be an object')
            version = record.get('version')
            if version == V2 and key == 'native_migration':
                if set(record) != V2_KEYS or record.get('new_reservation_created') is not False:
                    raise ValueError('Exact V2 transfer schema required')
                if any(record.get(flag) is not True for flag in ('remote_owner_absent', 'remote_artifacts_absent')):
                    raise ValueError('Original reviewed V2 transfer flags differ')
                src, amount, addition, target_amount, hash_key = record['original_envelope_id'], Decimal('5.25'), Decimal(0), Decimal('5.25'), 'migration_sha256'
                if _money(record['migrated_usd']) != amount or _money(record['old_failed_child_allowance_held_usd']) != Decimal('1.75'):
                    raise ValueError('V2 transfer allowance differs')
                facts = record['original_failure']; child = record['old_failed_child_run_id']
            elif version == V3 and key == 'native_config_funding':
                if set(record) != V3_KEYS or record.get('new_reservation_created') is not True:
                    raise ValueError('Exact V3 transfer plus new reservation schema required')
                if any(record.get(flag) is not True for flag in ('parent_remote_owner_and_artifacts_exist', 'parent_mount_source_tokenizer_verified')):
                    raise ValueError('Actual V2 startup proof flags differ')
                src, amount, addition, target_amount, hash_key = record['parent_envelope_id'], Decimal('3.50'), Decimal('1.75'), Decimal('5.25'), 'funding_sha256'
                if (_money(record['transferred_unused_usd']) != amount or _money(record['additional_new_reservation_usd']) != addition
                        or _money(record['total_commitment_increase_usd']) != addition or _money(record['funded_envelope_usd']) != target_amount
                        or _money(record['historical_failed_allowance_each_usd']) != Decimal('1.75')):
                    raise ValueError('V3 transfer/new-reservation amounts differ')
                facts = record['parent_failure']; child = record['parent_failed_child_run_id']
            else: raise ValueError('Unsupported native transfer receipt version or attachment')
            if type(record.get('validated_outputs')) is not int or record['validated_outputs'] != 0:
                raise ValueError('Transferred failed stage must have explicit zero validated outputs')
            source, target = _id(src), _id(record['new_envelope_id'])
            if source == target or source not in by_id or target not in by_id or job['run_id'] not in (source, target):
                raise ValueError('Source/target transfer attachment is missing, foreign or self-referential')
            if record.get(hash_key) != digest({k: v for k, v in record.items() if k != hash_key}):
                raise ValueError('Full native transfer audit hash differs')
            for name in ('new_design_sha256', 'new_manifest_sha256', 'recovery_review_sha256' if version == V2 else 'config_recovery_review_sha256'):
                if not _hash(record.get(name)): raise ValueError('Transfer proof hash missing')
            _inventory(record['new_source_sha256']); _stamp(record['created_at_utc'])
            receipt_hash = digest(record)
            edge = dict(source=source, target=target, amount=amount, addition=addition, target_amount=target_amount,
                record=record, key=key, facts=facts, child=child, receipt_hash=receipt_hash)
            if receipt_hash in records and canonical(records[receipt_hash]['record']) != canonical(record):
                raise ValueError('Conflicting native audit digest')
            records[receipt_hash] = edge
    return by_id, list(records.values())


def _child(by_id, envelope, facts, identity):
    if not isinstance(facts, dict) or facts.get('original_baseline_run_id') != identity or identity not in by_id:
        raise ValueError('Original failed child source proof missing')
    child = by_id[identity]
    required = {'native_design_sha256': 'original_design_sha256', 'native_claim_id': 'original_claim_id',
        'native_intent_sha256': 'original_intent_sha256', 'native_terminal_sha256': 'original_provider_terminal_sha256',
        'call_id': 'original_call_id'}
    if (child.get('service', 'modal') != 'modal' or child.get('status') != 'failed'
            or child.get('native_envelope_parent') != envelope['run_id'] or _money(child.get('reserved_usd', 0)) != Decimal('1.75')
            or any(child.get(k) != facts.get(v) for k, v in required.items())
            or child.get('native_design_sha256') != envelope.get('native_design_sha256')
            or not re.fullmatch(r'[0-9a-f]{32}', str(child.get('native_claim_id', '')))
            or not re.fullmatch(r'fc-[A-Za-z0-9-]+', str(child.get('call_id', '')))):
        raise ValueError('Original failed child allowance, status, claim, call or terminal proof differs')
    for key in ('original_design_sha256', 'original_manifest_sha256', 'original_launch_sha256', 'original_provider_terminal_sha256'):
        if not _hash(facts.get(key)): raise ValueError('Original source receipt hash missing')
    _inventory(facts.get('original_source_sha256'))
    launch = {'run_id': identity, 'call_id': child['call_id'], 'claim_id': child['native_claim_id'], 'intent_sha256': child['native_intent_sha256']}
    if facts['original_launch_sha256'] != _file_digest(launch): raise ValueError('Original launch hash does not bind exact failed claim')
    return child


def verify_transfers(ledger):
    """Pure embedded-audit DAG proof; physical artifact checks are separate.

    Controllers verify their exact on-disk design/review/receipts before writing
    these double-attached audits. This function does not authenticate a provider
    or claim a ledger receipt by itself proves a remote terminal.
    """
    by_id, edges = _edges(ledger); outgoing, incoming = {}, {}
    for edge in edges:
        src, dst, record = edge['source'], edge['target'], edge['record']
        if src in outgoing or dst in incoming: raise ValueError('Native transfer DAG cannot fork or merge allowances')
        outgoing[src], incoming[dst] = edge, edge
        source, target = by_id[src], by_id[dst]
        for job in (source, target):
            if job.get('service', 'modal') != 'modal' or job.get('native_envelope') is not True or not _hash(job.get('native_design_sha256')):
                raise ValueError('Only explicit native Modal envelopes can transfer')
            if canonical(job.get(edge['key'])) != canonical(record): raise ValueError('Source and target must retain the exact same transfer audit')
        if (source.get('status') != 'superseded' or _money(source.get('reserved_usd', -1)) != 0
                or source.get('superseded_by') != dst or target.get('native_design_sha256') != record['new_design_sha256']
                or _money(target.get('initial_reserved_usd', 0)) != edge['target_amount']):
            raise ValueError('Superseded zero source or funded target identity differs')
        child = _child(by_id, source, edge['facts'], edge['child'])
        if source.get('dispatches') != [child['run_id']]: raise ValueError('Transferred source must retain its exact single failed original')
        if edge['key'] == 'native_migration':
            if _money(source.get('initial_reserved_usd', 0)) != Decimal('7'):
                raise ValueError('V1 original envelope must be seven dollars')
            proof = edge['facts'].get('original_failure_evidence')
            if (not isinstance(proof, dict) or proof.get('evidence_sha256') != digest({k: v for k, v in proof.items() if k != 'evidence_sha256'})
                    or proof.get('evidence_sha256') != edge['facts'].get('original_failure_evidence_sha256')
                    or proof.get('call_id') != child['call_id'] or proof.get('provider_status') != 'FAILURE'
                    or type(proof.get('provider_status_value')) is not int or proof['provider_status_value'] != 2
                    or proof.get('positive_provider_failure_status') is not True):
                raise ValueError('V1 positive failed-call evidence differs')
        else:
            parent = edge['facts']; prior = parent.get('parent_migration_receipt')
            prior_edge = incoming.get(src) or next((e for e in edges if e['target'] == src), None)
            if (prior_edge is None or prior_edge['key'] != 'native_migration' or canonical(prior) != canonical(prior_edge['record'])
                    or record.get('parent_migration_receipt_sha256') != _file_digest(prior)
                    or parent.get('parent_migration_receipt_sha256') != _file_digest(prior)
                    or canonical(parent.get('v1_failure_source')) != canonical(prior_edge['facts'])
                    or parent.get('parent_mount_source_tokenizer_verified') is not True
                    or parent.get('parent_remote_owner_and_artifacts_exist') is not True
                    or parent.get('runtime_model_load_verified') is not False
                    or type(parent.get('validated_outputs')) is not int or parent['validated_outputs'] != 0
                    or record.get('v1_failed_child_run_id') != prior_edge['child']):
                raise ValueError('V3 must preserve the complete incoming V1 to V2 proof chain')
            _child(by_id, by_id[prior_edge['source']], prior_edge['facts'], prior_edge['child'])
    # Cycle and chronology checks are independent of the order of ledger jobs.
    for start in outgoing:
        seen, node = set(), start
        while node in outgoing:
            if node in seen: raise ValueError('Native transfer graph contains a cycle')
            seen.add(node); node = outgoing[node]['target']
    nodes = set(outgoing) | set(incoming)
    for identity in nodes:
        envelope = by_id[identity]
        children = [job for job in by_id.values() if job.get('native_envelope_parent') == identity]
        if (envelope.get('dispatches') != [job['run_id'] for job in children]
                or len(children) > (4 if identity not in incoming else 3)
                or any(job.get('service', 'modal') != 'modal' or _money(job.get('reserved_usd', 0)) != Decimal('1.75')
                    or job.get('native_design_sha256') != envelope['native_design_sha256'] for job in children)):
            raise ValueError('Native child identities or historical allowances differ')
        used = sum((_money(job['reserved_usd']) for job in children), Decimal(0))
        outgoing_amount = outgoing[identity]['amount'] if identity in outgoing else Decimal(0)
        if _money(envelope['initial_reserved_usd']) != _money(envelope['reserved_usd']) + used + outgoing_amount:
            raise ValueError('Native envelope initial, children, remainder and outgoing allowance do not conserve')
        if identity in incoming and _money(envelope['initial_reserved_usd']) != incoming[identity]['amount'] + incoming[identity]['addition']:
            raise ValueError('Incoming transfer plus explicit new reservation does not equal funded envelope')
        if identity in incoming and identity in outgoing and _stamp(outgoing[identity]['record']['created_at_utc']) < _stamp(incoming[identity]['record']['created_at_utc']):
            raise ValueError('Outgoing transfer predates its incoming funding')
        if identity not in outgoing and envelope.get('status') != 'reserved':
            raise ValueError('Untransferred native envelope must remain a reserved allowance')
    superseded = [job for job in by_id.values() if job.get('service', 'modal') == 'modal' and job.get('status') == 'superseded']
    if any(job['run_id'] not in outgoing for job in superseded):
        raise ValueError('Unproven superseded Modal job cannot be normalized')
    return {'version': VERSION, 'verified_superseded_ids': sorted(outgoing),
        'conservation_verified': True, 'edges': [{'source': e['source'], 'target': e['target'],
            'transferred_usd': float(e['amount']), 'new_reservation_usd': float(e['addition']),
            'receipt_sha256': e['receipt_hash']} for e in sorted(edges, key=lambda e: e['source'])]}


def reconcile(ledger, snapshot, *, apps=(), now=None, lag_minutes=15, lag_buffer_usd=3):
    proof = verify_transfers(ledger)
    planning = deepcopy(ledger)
    for job in planning['jobs']:
        if job['run_id'] in proof['verified_superseded_ids']:
            job['status'] = 'reserved'  # ZERO planned reservation, never a fabricated terminal.
    result = legacy.reconcile(planning, snapshot, apps=apps, now=now,
        lag_minutes=lag_minutes, lag_buffer_usd=lag_buffer_usd)
    for job in result['jobs']:
        if job['run_id'] in proof['verified_superseded_ids']:
            job['status'] = 'superseded'
            job['budget_liability'] = {'kind': 'verified_transferred_native_envelope_zero', 'amount_usd': 0.0,
                'note': 'Historical transfer remains superseded; unused allowance is conserved in its audited target. This is not a provider terminal or charge.'}
    result['native_transfer_accounting'] = proof
    return result


def _safe(path, root=PRIVATE):
    root = Path(root).absolute(); path = Path(os.path.abspath(path))
    if not path.is_relative_to(root): raise ValueError('Audit path escaped private run root')
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)(): raise ValueError('Linked audit path forbidden')
        if part == root: break
    return path


def _read(path):
    path = _safe(path)
    if not 0 < path.stat().st_size <= 64 * 1024 * 1024: raise ValueError('Bounded private audit metadata required')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('Duplicate audit JSON key')
            value[key] = item
        return value
    return json.loads(path.read_bytes().decode('utf-8-sig'), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite audit JSON')))


def validate_local_audits(ledger):
    """Read exact final source/target audit files; no provider or ledger writes."""
    proof = verify_transfers(ledger)
    _, edges = _edges(ledger)
    for edge in edges:
        record, facts = edge['record'], edge['facts']
        output = _safe(PRIVATE / edge['target'][:-len('-envelope')])
        receipt = output / ('migration.json' if edge['key'] == 'native_migration' else 'funding.json')
        if canonical(_read(receipt)) != canonical(record) or receipt.read_bytes() != _file_bytes(record):
            raise ValueError('Physical source/target transfer receipt differs')
        mappings = {'new_design_sha256': output / 'design.json', 'new_manifest_sha256': output / 'study_manifest.json',
            'recovery_review_sha256' if edge['key'] == 'native_migration' else 'config_recovery_review_sha256':
                output / ('review_recovery.json' if edge['key'] == 'native_migration' else 'review_config_recovery.json')}
        original = _safe(PRIVATE / facts['original_output']); folder = _safe(original / 'arms' / facts['original_baseline_run_id'])
        mappings.update(original_design_sha256=original / 'design.json', original_manifest_sha256=original / 'study_manifest.json',
            original_launch_sha256=folder / 'launch.json', original_provider_terminal_sha256=folder / 'provider_terminal.json')
        for key, name in (('original_call_graph_sha256', 'first_observed_call_graph.private.json'),
                ('original_error_sha256', 'first_observed_provider_error.private.log'), ('original_provider_result_sha256', 'provider_result.json'),
                ('original_plan_sha256', 'plan.json'), ('original_input_sha256', 'input.json')):
            if key in facts: mappings[key] = folder / name
        for key, path in mappings.items():
            path = _safe(path)
            if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError('Original transfer proof artifact missing or oversized')
            expected = record.get(key) if key.startswith('new_') or key.endswith('review_sha256') else facts.get(key)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected: raise ValueError('Physical transfer proof hash differs')
        for source_hashes in (record['new_source_sha256'], facts['original_source_sha256']):
            for name, expected in source_hashes.items():
                path = ROOT / name
                if (not path.is_file() or path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
                        or not 0 < path.stat().st_size <= 4 * 1024 * 1024
                        or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                    raise ValueError('Frozen transfer source bytes changed')
    return proof


def _write(path, value):
    path = _safe(path); temporary = path.with_name(path.name + f'.native-budget.{os.getpid()}.pending')
    with temporary.open('xb') as handle: handle.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()); handle.flush(); os.fsync(handle.fileno())
    for attempt in range(4):
        try: temporary.replace(path); return
        except PermissionError:
            if attempt == 3: raise
            time.sleep(.05 * 2**attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Read supported actual provider observations')
    parser.add_argument('--write', action='store_true', help='Explicitly save reconciled budget and refreshed observations')
    parser.add_argument('--lag-minutes', type=int, default=15); parser.add_argument('--lag-buffer-usd', type=Decimal, default=Decimal('3'))
    args = parser.parse_args()
    if args.refresh: snapshot, apps = legacy.fetch_provider()
    else:
        snapshot = _read(STATE / 'modal_billing_snapshot.json')
        apps = _read(STATE / 'modal_app_status_snapshot.json').get('apps', [])
    lock = _safe(STATE / 'budget_reconcile.lock'); fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode()); os.fsync(fd)
        path = _safe(STATE / 'budget.json'); original = path.read_bytes(); ledger = _read(path)
        validate_local_audits(ledger)
        updated = reconcile(ledger, snapshot, apps=apps, lag_minutes=args.lag_minutes, lag_buffer_usd=args.lag_buffer_usd)
        if args.write:
            if path.read_bytes() != original: raise RuntimeError('Ledger owner changed during reconciliation')
            if args.refresh:
                _write(STATE / 'modal_billing_snapshot.json', snapshot)
                _write(STATE / 'modal_app_status_snapshot.json', {'apps': apps})
            _write(path, updated)
        print(json.dumps(dict(legacy.summarize_public(updated), native_transfer_accounting=updated['native_transfer_accounting'])))
    finally: os.close(fd); lock.unlink()


if __name__ == '__main__': main()
