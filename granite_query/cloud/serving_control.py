"""Prepare and enforce the short, request-capped public Granite trial.

No deployment happens here. `prepare` freezes checkpoint choice, evaluation,
research clearance and an existing reservation. `initialize` is a separate,
explicit durable-control write; it never clears or refunds consumed slots.

Concurrency uses Modal's documented put(skip_if_exists=True) locking primitive,
not a read/increment/write counter. Even overlapping web containers cannot admit
more than the fixed slot count. Failed/ambiguous calls consume their slot.

Official references (checked 2026-11-03):
https://modal.com/docs/guide/webhooks
https://modal.com/docs/guide/timeouts
https://modal.com/docs/sdk/py/latest/Dict
https://modal.com/blog/cache-dict-launch
https://modal.com/pricing
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import uuid

MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
DICT_NAME = 'granite-query-serving-control-v1'
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')
LIMITS = dict(max_requests=20, max_input_chars=2400, max_input_tokens=768,
              max_output_tokens=256, max_body_bytes=16384, context_limit=2048,
              gpu='L4', max_containers=1, min_containers=0, buffer_containers=0,
              timeout_seconds=90, startup_timeout_seconds=60,
              scaledown_window_seconds=2, single_use_containers=True,
              cpu_cores=1, memory_mib=12288, expiry_hours=24,
              slot_reservation_usd='0.05', total_reservation_usd='1.00')
PRICE_BASIS = dict(checked_at_utc='2026-11-03', source='https://modal.com/pricing',
                   gpu_per_second='0.000222', cpu_per_core_second='0.0000131',
                   memory_per_gib_second='0.00000222', allowance_seconds_per_call=170,
                   note='90 execution +60 startup +2 scaledown +18 timing slack. '
                        'Fixed request envelope is not a provider-enforced invoice cap. '
                        'Denied HTTP traffic still incurs CPU costs; stop the app after trial.')
TERMINAL = {'completed', 'failed', 'cancelled', 'canceled', 'stopped', 'reconciled'}


class ServingRefused(ValueError):
    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ServingRefused('UTC timestamps must include an offset')
    return parsed.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def safe_name(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value))


def safe_hash(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))


def validate_selection(value):
    """Require an evaluated, deliberately chosen immutable adapter artifact."""
    if value.get('final_choice') is not True or not safe_name(value.get('checkpoint_id')):
        raise ServingRefused('An explicit final chosen checkpoint is required')
    if value.get('model') != MODEL or value.get('revision') != REVISION:
        raise ServingRefused('The served base must match the pinned evaluated Granite model')
    artifact = value.get('artifact', {})
    if not safe_name(artifact.get('run_id')):
        raise ServingRefused('Chosen adapter run ID is invalid')
    subpath = artifact.get('adapter_subpath')
    if not isinstance(subpath, str) or subpath not in {'adapter', 'ranked_adapter', 'random_adapter'}:
        raise ServingRefused('Chosen adapter directory is invalid')
    hashes = artifact.get('files_sha256', {})
    if not all(k in hashes for k in ('adapter_config.json', 'adapter_model.safetensors')):
        raise ServingRefused('Both adapter configuration and weights need frozen SHA256 hashes')
    if any(PurePosixPath(k).name != k or not safe_hash(v) for k, v in hashes.items()):
        raise ServingRefused('Invalid checkpoint file hash inventory')
    evaluation = value.get('evaluation', {})
    n, correct = evaluation.get('n'), evaluation.get('correct')
    if evaluation.get('stage') != 'completed' or type(n) is not int or n < 1:
        raise ServingRefused('Chosen checkpoint evaluation has not completed')
    if type(correct) is not int or not 0 <= correct <= n:
        raise ServingRefused('Invalid measured accuracy')
    if evaluation.get('split_role') not in {'development_monitoring', 'final_test'}:
        raise ServingRefused('Evaluation must explicitly identify development versus final test')
    if not safe_hash(evaluation.get('artifact_sha256')):
        raise ServingRefused('Measured evaluation must have an immutable artifact hash')
    if not str(evaluation.get('report_url', '')).startswith('https://avisrikumeran.github.io/granite-query/'):
        raise ServingRefused('A public result report is required')
    return value


def estimated_slot_compute_usd():
    per_second = (Decimal(PRICE_BASIS['gpu_per_second']) +
                  Decimal(PRICE_BASIS['cpu_per_core_second']) * LIMITS['cpu_cores'] +
                  Decimal(PRICE_BASIS['memory_per_gib_second']) * Decimal(LIMITS['memory_mib']) / 1024)
    return per_second * PRICE_BASIS['allowance_seconds_per_call']


def prepare(selection_path, budget_path, clearance_path, output, *, reservation_id, now=None):
    """Create a new immutable manifest; this does not reserve funds or deploy."""
    now = now or utcnow()
    selection, budget, clearance = read(selection_path), read(budget_path), read(clearance_path)
    validate_selection(selection)
    if not safe_name(reservation_id):
        raise ServingRefused('Invalid serving reservation ID')
    if clearance.get('research_phase_closed') is not True or clearance.get('active_gpu_call_ids') != []:
        raise ServingRefused('Research GPU phase must finish before public serving')
    checked = parse_time(clearance.get('checked_at_utc', ''))
    if not timedelta(0) <= now - checked <= timedelta(minutes=15):
        raise ServingRefused('Research GPU clearance must be checked within 15 minutes')
    active = [j for j in budget.get('jobs', []) if j.get('service', 'modal') == 'modal'
              and j.get('run_id') != reservation_id and j.get('status') not in TERMINAL]
    if active:
        raise ServingRefused('Another Modal reservation/call still needs reconciliation')
    jobs = [j for j in budget.get('jobs', []) if j.get('run_id') == reservation_id]
    if len(jobs) != 1 or jobs[0].get('service') != 'modal' or jobs[0].get('status') != 'reserved':
        raise ServingRefused('An existing, unused Modal serving reservation is required')
    amount = Decimal(str(jobs[0].get('reserved_usd', 0)))
    if amount != Decimal(LIMITS['total_reservation_usd']):
        raise ServingRefused('This trial requires exactly the saved $1 serving reservation')
    if Decimal(str(budget.get('limits', {}).get('modal', 0))) > Decimal('30'):
        raise ServingRefused('Modal service ceiling changed from the authorized $30')
    accounted = (Decimal(str(budget.get('estimated_spend', {}).get('modal', 0))) +
                 Decimal(str(budget.get('reserved', {}).get('modal', 0))))
    if accounted > Decimal('30') or Decimal(str(budget.get('reserved', {}).get('modal', 0))) < amount:
        raise ServingRefused('Serving reservation is not within the remaining service ceiling')
    manifest = dict(schema_version=1, selection=selection,
                    quota_namespace=reservation_id, created_at_utc=stamp(now),
                    expires_at_utc=stamp(now + timedelta(hours=24)),
                    research_phase_closed=True, limits=copy.deepcopy(LIMITS),
                    price_basis=copy.deepcopy(PRICE_BASIS),
                    slot_compute_estimate_usd=str(estimated_slot_compute_usd()),
                    sources_sha256={'selection':digest(selection), 'budget':digest(budget),
                                    'research_clearance':digest(clearance)},
                    reservation={'run_id':reservation_id, 'reserved_usd':str(amount)},
                    allowed_origin='https://avisrikumeran.github.io')
    manifest['manifest_sha256'] = digest(manifest)
    validate_manifest(manifest, now=now)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    return manifest


def validate_manifest(manifest, *, now=None):
    value = dict(manifest)
    claimed = value.pop('manifest_sha256', None)
    if claimed != digest(value):
        raise ServingRefused('Serving manifest changed after checkpoint selection')
    validate_selection(value.get('selection', {}))
    if value.get('limits') != LIMITS or value.get('price_basis') != PRICE_BASIS:
        raise ServingRefused('Bounded serving policy differs from this implementation')
    if value.get('research_phase_closed') is not True:
        raise ServingRefused('Research GPU phase is still active')
    if not safe_name(value.get('quota_namespace')):
        raise ServingRefused('Invalid quota namespace')
    reservation = value.get('reservation', {})
    if reservation.get('run_id') != value['quota_namespace'] or Decimal(str(reservation.get('reserved_usd', 0))) != Decimal('1'):
        raise ServingRefused('Missing serving budget reservation')
    start, end = parse_time(value['created_at_utc']), parse_time(value['expires_at_utc'])
    if end - start != timedelta(hours=24):
        raise ServingRefused('Trial must expire 24 hours after preparation')
    now = now or utcnow()
    if not start <= now < end:
        raise ServingRefused('Serving trial has expired or has not begun', 410)
    if estimated_slot_compute_usd() >= Decimal(LIMITS['slot_reservation_usd']):
        raise ServingRefused('Resource estimate no longer fits the fixed slot reservation')
    return manifest


def public_model(manifest):
    """Exact allowlist: no account details, hashes of private paths, or keys."""
    selection = manifest['selection']
    measured = selection['evaluation']
    return dict(model=MODEL, revision=REVISION, checkpoint_id=selection['checkpoint_id'],
                training_method='LoRA sequence supervised fine-tuning',
                measured_accuracy={'correct':measured['correct'], 'n':measured['n'],
                                   'split_role':measured['split_role'], 'report_url':measured['report_url']},
                expires_at_utc=manifest['expires_at_utc'],
                limits={k:LIMITS[k] for k in ('max_requests', 'max_input_chars', 'max_input_tokens',
                                           'max_output_tokens', 'context_limit')},
                note='Small research trial; cold starts possible. A failed or cancelled request consumes quota. The API caps output at256 tokens; benchmark results in the report may use a512-token cap and do not measure this serving configuration.')


def validate_request(body):
    if not isinstance(body, dict) or set(body) - {'prompt', 'max_new_tokens', 'request_id'}:
        raise ServingRefused('Expected prompt, optional max_new_tokens, and UUID request_id only', 422)
    prompt = body.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > LIMITS['max_input_chars']:
        raise ServingRefused('Prompt must contain 1 to 2400 characters', 422)
    cap = body.get('max_new_tokens', LIMITS['max_output_tokens'])
    if type(cap) is not int or not 1 <= cap <= LIMITS['max_output_tokens']:
        raise ServingRefused('max_new_tokens must be between 1 and 256', 422)
    try:
        request_id = str(uuid.UUID(body['request_id']))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ServingRefused('A UUID request_id is required for safe request deduplication', 422) from None
    return dict(prompt=prompt, max_new_tokens=cap, request_id=request_id)


class Admission:
    """A fixed set of atomic, nonrefundable durable permit records.

    store must provide get and put(key,value,skip_if_exists=True). Every permit,
    request nonce and dispatch marker remains until after the trial has expired.
    There is deliberately no reset, release, refund, or automatic recovery path.
    """
    def __init__(self, store, manifest):
        self.store, self.manifest = store, manifest
        self.prefix = 'trial:' + manifest['quota_namespace'] + ':'

    def initialize(self, *, now=None):
        validate_manifest(self.manifest, now=now)
        control = {'manifest_sha256':self.manifest['manifest_sha256'], 'enabled':True}
        added = self.store.put(self.prefix+'control', control, skip_if_exists=True)
        if not added and self.store.get(self.prefix+'control') != control:
            raise ServingRefused('Existing reservation namespace cannot be reused or reset')
        return {'initialized':True, 'new':added}

    def ready(self, *, now=None):
        validate_manifest(self.manifest, now=now)
        control = self.store.get(self.prefix+'control')
        if control != {'manifest_sha256':self.manifest['manifest_sha256'], 'enabled':True}:
            raise ServingRefused('Trial has not been initialized or was disabled')

    def used(self):
        return sum(self.store.get(self.prefix+f'slot:{index}') is not None
                   for index in range(LIMITS['max_requests']))

    def claim(self, body, *, now=None):
        now = now or utcnow()
        self.ready(now=now)
        body = validate_request(body)
        # Advisory only; permanent conditional slot inserts below enforce the cap.
        # Once full, avoid creating new nonce records for denied public traffic.
        if self.store.get(self.prefix+'exhausted') is True or self.used() >= LIMITS['max_requests']:
            self.store.put(self.prefix+'exhausted', True, skip_if_exists=True)
            raise ServingRefused('The 20-request research trial quota is exhausted', 429)
        nonce = body['request_id']
        fingerprint = digest(body)
        if not self.store.put(self.prefix+'request:'+nonce, {'payload_sha256':fingerprint}, skip_if_exists=True):
            raise ServingRefused('Request ID was already attempted; it will not dispatch again', 409)
        record = dict(request_id=nonce, payload_sha256=fingerprint,
                      manifest_sha256=self.manifest['manifest_sha256'], admitted_at_utc=stamp(now))
        for index in range(LIMITS['max_requests']):
            key = self.prefix+f'slot:{index}'
            if self.store.put(key, record, skip_if_exists=True):
                # Read acknowledgement before authorizing any GPU dispatch.
                if self.store.get(key) != record:
                    raise ServingRefused('Admission persistence is ambiguous; request consumed')
                return dict(record, slot=index)
        self.store.put(self.prefix+'exhausted', True, skip_if_exists=True)
        raise ServingRefused('The 20-request research trial quota is exhausted', 429)

    def mark_dispatch(self, ticket, body, *, now=None):
        self.ready(now=now)
        index = ticket.get('slot')
        if type(index) is not int or not 0 <= index < LIMITS['max_requests']:
            raise ServingRefused('Invalid admission ticket')
        expected = dict(ticket)
        del expected['slot']
        if self.store.get(self.prefix+f'slot:{index}') != expected or digest(body) != ticket['payload_sha256']:
            raise ServingRefused('Admission ticket does not match persisted request')
        if not self.store.put(self.prefix+f'dispatch:{index}', {'request_id':ticket['request_id']}, skip_if_exists=True):
            raise ServingRefused('Dispatch already attempted; no automatic retry is allowed', 409)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('prepare')
    for key in ('selection', 'budget', 'clearance', 'output', 'reservation-id'):
        item.add_argument('--'+key, required=True)
    for name in ('validate', 'initialize', 'status'):
        item = sub.add_parser(name)
        item.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        value = prepare(args.selection, args.budget, args.clearance, args.output, reservation_id=args.reservation_id)
        print(json.dumps({'prepared':True, 'manifest_sha256':value['manifest_sha256'], 'deployed':False}))
        return
    value = read(args.manifest)
    validate_manifest(value)
    if args.command == 'validate':
        print(json.dumps({'valid':True, 'slot_compute_estimate_usd':str(estimated_slot_compute_usd()), 'deployed':False}))
        return
    import modal
    control = Admission(modal.Dict.from_name(DICT_NAME, create_if_missing=args.command=='initialize'), value)
    if args.command == 'initialize':
        print(json.dumps(control.initialize()))
    else:
        control.ready()
        print(json.dumps({'ready':True, 'used_requests':control.used(), 'expires_at_utc':value['expires_at_utc']}))


if __name__ == '__main__':
    main()
