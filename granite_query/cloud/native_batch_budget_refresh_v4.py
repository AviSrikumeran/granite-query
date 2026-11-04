"""Supported Modal budget refresh outside the frozen V4 runtime graph.

Default execution reads saved observations only. Explicit --refresh queries the
existing supported helper once; --write saves a checked three-file transaction
under the shared GPU/budget locks, with budget last. No GPU or teacher is called.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from cloud import budget_reconcile as provider
from cloud import native_batch_budget_reconcile_v4 as accounting
from cloud import native_reasoning_batch_control_v4 as control

VERSION = 'native-batch-supported-budget-refresh-v4'
STATE = control.STATE
FILES = ('modal_billing_snapshot.json', 'modal_app_status_snapshot.json', 'budget.json')
TRANSACTIONS = 'native_batch_refresh_transactions'


class RecoveryRequired(RuntimeError):
    pass


def now(): return datetime.now(timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def parse(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 64 * 1024 * 1024:
        raise ValueError('Bounded local metadata bytes required')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate local JSON key')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite local metadata')))


def _bytes(path):
    path = control.safe(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError('Original metadata file missing or oversized')
    return path.read_bytes()


def _new(path, raw):
    path = control.safe(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _atomic_replace(path, raw):
    """Local filesystem retries only; never wraps a provider request."""
    path = control.safe(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.refresh.pending')
    _new(temporary, raw)
    for attempt in range(4):
        try: temporary.replace(path); return
        except PermissionError:
            if attempt == 3: raise
            time.sleep(.05 * 2**attempt)


class Locks:
    def __init__(self, state): self.state = control.safe(state); self.owned = []; self.retain = False
    def __enter__(self):
        try:
            for name in ('native_batch_budget_refresh.lock', 'gpu_launch.lock', 'budget_reconcile.lock'):
                path = control.safe(self.state / name)
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                self.owned.append((path, fd, os.fstat(fd).st_ino))
                os.write(fd, str(os.getpid()).encode('ascii')); os.fsync(fd)
        except BaseException:
            self.__exit__(None, None, None); raise
        return self
    def __exit__(self, *error):
        for path, fd, inode in reversed(self.owned):
            os.close(fd)
            if (not self.retain and path.exists() and path.stat().st_ino == inode
                    and path.read_bytes() == str(os.getpid()).encode('ascii')):
                path.unlink()
        self.owned = []


def physical_proof(run, ledger):
    """Actual frozen V4 sources/input/parent/funding checks; no provider access."""
    jobs = control.load_jobs(run)
    control.validate_stage_funding(run, ledger)
    if len(jobs) != 3: raise ValueError('Three frozen V4 plans required')
    return {'run_id': Path(run).name,
        'design_sha256': control.sha(Path(run) / 'design.json'),
        'manifest_sha256': control.sha(Path(run) / 'study_manifest.json'),
        'funding_sha256': control.sha(Path(run) / 'funding.json'),
        'source_sha256': control.source_inventory(),
        'job_artifacts': {job['run_id']: {'folder': str(job['folder_path']),
            'input_sha256': control.sha(job['folder_path'] / 'input.json'),
            'plan_sha256': control.sha(job['folder_path'] / 'plan.json')} for job in jobs}}


def recheck_proof(run, proof):
    if (proof['design_sha256'] != control.sha(Path(run) / 'design.json')
            or proof['manifest_sha256'] != control.sha(Path(run) / 'study_manifest.json')
            or proof['funding_sha256'] != control.sha(Path(run) / 'funding.json')
            or proof['source_sha256'] != control.source_inventory()):
        raise ValueError('Frozen physical proof changed during refresh')
    for entry in proof['job_artifacts'].values():
        folder = control.safe(entry['folder'])
        if (entry['input_sha256'] != control.sha(folder / 'input.json')
                or entry['plan_sha256'] != control.sha(folder / 'plan.json')):
            raise ValueError('Frozen job input/plan changed during refresh')


def _apps(apps):
    if (not isinstance(apps, list) or any(not isinstance(app, dict) or not isinstance(app.get('app_id'), str)
            or not app['app_id'] or not isinstance(app.get('state'), str) or not app['state']
            or type(app.get('tasks')) not in (int, str) or not str(app['tasks']).isdigit() for app in apps)
            or len({app['app_id'] for app in apps}) != len(apps)):
        raise ValueError('Unknown or malformed actual Modal app inventory requires reconciliation')
    # Active tasks are permitted: accounting retains their actual reservations.


def _history(ledger):
    derived = {'budget_liability', 'terminal_observed_at_utc', 'provider_app_stopped_at_utc'}
    return [{key: value for key, value in job.items() if key not in derived} for job in ledger['jobs']]


def _derive(ledger, snapshot, apps):
    _apps(apps)
    updated = accounting.reconcile(ledger, snapshot, apps=apps)
    if (_history(updated) != _history(ledger)
            or updated['reserved']['deepseek'] != ledger['reserved']['deepseek']
            or updated['estimated_spend']['deepseek'] != ledger['estimated_spend']['deepseek']
            or any(updated.get(key) != value for key, value in ledger.items() if key.startswith('deepseek'))):
        raise ValueError('Modal refresh must preserve all nominal job history and DeepSeek holds')
    return updated


def _stage(state, old, new, proof):
    identity = uuid.uuid4().hex
    directory = control.safe(state / TRANSACTIONS / identity)
    directory.mkdir(parents=True, exist_ok=False)
    for kind, values in (('old', old), ('new', new)):
        for name in FILES: _new(directory / kind / name, values[name])
    body = {'version': VERSION, 'transaction_id': identity, 'created_at_utc': now(), 'pid': os.getpid(),
        'files': {name: {'old_sha256': sha(old[name]), 'new_sha256': sha(new[name])} for name in FILES},
        'physical_proof': proof, 'commit_order': list(FILES)}
    manifest = dict(body, manifest_sha256=control.digest(body))
    _new(directory / 'transaction.json', encode(manifest))
    return directory, manifest


def _load_transaction(directory, state):
    directory = control.safe(directory)
    if (directory.parent != state / TRANSACTIONS or not re.fullmatch(r'[0-9a-f]{32}', directory.name)):
        raise ValueError('Explicit staged refresh transaction directory required')
    manifest = parse(_bytes(directory / 'transaction.json'))
    if (manifest.get('version') != VERSION or manifest.get('transaction_id') != directory.name
            or manifest.get('commit_order') != list(FILES) or set(manifest.get('files', {})) != set(FILES)
            or manifest.get('manifest_sha256') != control.digest({key:value for key,value in manifest.items() if key != 'manifest_sha256'})):
        raise ValueError('Immutable refresh transaction manifest differs')
    values = {}
    for kind in ('old', 'new'):
        values[kind] = {name: _bytes(directory / kind / name) for name in FILES}
        if any(sha(values[kind][name]) != manifest['files'][name][kind + '_sha256'] for name in FILES):
            raise ValueError('Staged original/new bytes differ from the manifest')
    return manifest, values


def _rollback(directory, state):
    manifest, values = _load_transaction(directory, state)
    current = {name: _bytes(state / name) for name in FILES}
    if any(sha(current[name]) not in (manifest['files'][name]['old_sha256'], manifest['files'][name]['new_sha256']) for name in FILES):
        raise RecoveryRequired('Unknown third-party state bytes; never overwrite during refresh recovery')
    for name in reversed(FILES):
        live = _bytes(state / name)
        if sha(live) not in (manifest['files'][name]['old_sha256'], manifest['files'][name]['new_sha256']):
            raise RecoveryRequired('State changed during exact-byte rollback; never overwrite unknown bytes')
        if live != values['old'][name]: _atomic_replace(state / name, values['old'][name])
    if any(_bytes(state / name) != values['old'][name] for name in FILES):
        raise RecoveryRequired('Exact original state was not restored')
    if not (directory / 'rolled_back.json').exists():
        _new(directory / 'rolled_back.json', encode({'manifest_sha256':manifest['manifest_sha256'], 'rolled_back_at_utc':now()}))
    return manifest


def refresh_budget(run=control.DEFAULT, *, refresh=False, write=False, state=STATE, fetch_provider=None,
                   proof_validator=None, proof_recheck=None):
    """One supported observation and optional guarded local commit, no paid work."""
    state, run = control.safe(state), control.safe(run)
    fresh = (fetch_provider or provider.fetch_provider)() if refresh else None
    validator = proof_validator or physical_proof; recheck = proof_recheck or recheck_proof
    def prepare():
        old = {name:_bytes(state / name) for name in FILES}
        ledger = parse(old['budget.json'])
        if fresh is None:
            snapshot = parse(old['modal_billing_snapshot.json'])
            apps = parse(old['modal_app_status_snapshot.json']).get('apps', [])
        else: snapshot, apps = fresh
        proof = validator(run, ledger)
        updated = _derive(ledger, snapshot, apps)
        recheck(run, proof)
        if any(_bytes(state / name) != old[name] for name in FILES): raise ValueError('Live state changed during physical budget validation')
        new = dict(old, **{'budget.json':encode(updated)})
        if fresh is not None:
            new['modal_billing_snapshot.json'] = encode(snapshot)
            new['modal_app_status_snapshot.json'] = encode({'apps':apps,'queried_at_utc':snapshot['queried_at_utc'],
                'source':'Supported Modal app inventory captured with billing observation'})
        return old, new, proof, updated
    if not write:
        _, _, proof, updated = prepare()
        return dict(provider.summarize_public(updated), version=VERSION, wrote=False, refreshed=refresh,
            physical_proof_verified=True, run_id=proof['run_id'])
    with Locks(state) as locks:
        old, new, proof, updated = prepare()
        directory, manifest = _stage(state, old, new, proof)
        locks.retain = True  # Even Python interrupts must not unlock mixed files.
        try:
            recheck(run, proof)
            for name in FILES:
                if _bytes(state / name) != old[name]: raise RecoveryRequired('Live metadata changed before guarded commit')
                if new[name] != old[name]: _atomic_replace(state / name, new[name])
            if any(_bytes(state / name) != new[name] for name in FILES): raise RecoveryRequired('Guarded commit bytes differ')
            _new(directory / 'committed.json', encode({'manifest_sha256':manifest['manifest_sha256'], 'committed_at_utc':now()}))
            locks.retain = False
        except BaseException:
            try:
                _rollback(directory, state)
                locks.retain = False
            except BaseException as rollback_error:
                raise RecoveryRequired('Refresh rollback needs explicit local recovery; shared locks retained') from rollback_error
            raise
    return dict(provider.summarize_public(updated), version=VERSION, wrote=True, refreshed=refresh,
        physical_proof_verified=True, run_id=proof['run_id'], transaction_id=manifest['transaction_id'])


def recover_transaction(directory, *, state=STATE):
    """Explicit known-byte rollback; inspect stale owners before clearing locks."""
    state = control.safe(state)
    with Locks(state) as locks:
        locks.retain = True
        try:
            manifest, values = _load_transaction(directory, state)
            committed = control.safe(Path(directory) / 'committed.json')
            if committed.exists():
                receipt = parse(_bytes(committed))
                if (receipt.get('manifest_sha256') != manifest['manifest_sha256']
                        or any(_bytes(state / name) != values['new'][name] for name in FILES)):
                    raise RecoveryRequired('Previously committed transaction now has foreign state bytes')
                locks.retain = False
                return {'version':VERSION,'stage':'already_committed','transaction_id':manifest['transaction_id']}
            _rollback(Path(directory), state)
            locks.retain = False
            return {'version':VERSION,'stage':'rolled_back','transaction_id':manifest['transaction_id']}
        except BaseException:
            locks.retain = True; raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=control.DEFAULT)
    parser.add_argument('--refresh', action='store_true'); parser.add_argument('--write', action='store_true')
    parser.add_argument('--recover', type=Path, help='Explicit local rollback of an exact staged pending transaction; no provider call')
    args = parser.parse_args()
    if args.recover:
        if args.refresh or args.write: parser.error('--recover cannot be combined with provider refresh/write flags')
        result = recover_transaction(args.recover)
    else: result = refresh_budget(args.run, refresh=args.refresh, write=args.write)
    print(json.dumps(result))


if __name__ == '__main__': main()
