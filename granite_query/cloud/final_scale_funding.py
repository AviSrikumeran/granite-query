"""Pure whole-bundle escrow accounting. No files, providers or authorization.

The controller must physically verify the seal and sources, refresh both
providers and hold the shared ledger lock before committing returned copies.
Reservations, including escrow transfers, are never represented as charges.
"""
from copy import deepcopy
from decimal import Decimal
import re
from cloud import final_scale_contract as contract_api

ACTIVE = {'reserved', 'spawning', 'spawned', 'running', 'queued'}
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')


def _name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('Require a safe unique bundle or run identifier')
    return value


def snapshot(ledger, *, as_of_utc):
    """Normalize supported observations, preserving all existing liabilities."""
    current = contract_api._time(as_of_utc)
    observations = {'modal': ledger.get('modal_observation', {}),
                    'deepseek': ledger.get('deepseek_wallet_observation', {})}
    accounts = {service: ledger.get(service+'_budget_accounting', {}) for service in observations}
    basis = {'modal':'provider_observed_metered_plus_collection_buffer_and_open_liabilities',
             'deepseek':'user_declared_funding_minus_observed_wallet'}
    for service, ceiling in (('modal',30), ('deepseek',20)):
        account = accounts[service]
        stamp = observations[service].get('queried_at_utc')
        if (account.get('basis') != basis[service] or account.get('issues')
                or account.get('new_paid_launches_allowed') is not True
                or not stamp or not 0 <= (current-contract_api._time(stamp)).total_seconds() <= 900):
            raise ValueError('Fresh supported unambiguous provider accounting is required')
        if service == 'deepseek' and (account.get('status') != 'conditional_wallet_inference'
                or account.get('funding_history_ambiguous') is not False):
            raise ValueError('DeepSeek funding inference is not supported and unambiguous')
        limit = contract_api.money(ledger['limits'][service])
        spent = contract_api.money(ledger['estimated_spend'][service])
        reserved = contract_api.money(ledger['reserved'][service])
        if not 0 < limit <= ceiling or spent+reserved > limit:
            raise ValueError('Existing service ceiling is exceeded')
        if contract_api.money(account['estimated_spend_usd']) != spent:
            raise ValueError('Ledger spend differs from supported accounting')
    return {'observed_at_utc':{s:observations[s]['queried_at_utc'] for s in observations},
        'new_paid_work_allowed':{s:True for s in observations},
        'limits_usd':{s:str(ledger['limits'][s]) for s in observations},
        'spent_usd':{s:str(ledger['estimated_spend'][s]) for s in observations},
        'reserved_usd':{s:str(ledger['reserved'][s]) for s in observations}}


def _recount(ledger):
    """Update reservation summaries only; provider reconciliation remains separate."""
    for service in ('modal','deepseek'):
        # Existing unknown and terminal collection liabilities are already in
        # reserved; callers apply exact deltas rather than dropping those jobs.
        spent = contract_api.money(ledger['estimated_spend'][service])
        held = contract_api.money(ledger['reserved'][service])
        account = ledger[service+'_budget_accounting']
        account['budget_committed_usd'] = float(spent+held)
        account['budget_remaining_usd'] = float(contract_api.money(ledger['limits'][service])-spent-held)
        if account['budget_remaining_usd'] < 0:
            raise ValueError('Reservation would exceed the existing ceiling')
    return ledger


def allocate(ledger, contract, review, *, seal_sha256, bundle_id, as_of_utc,
             actual_source_hashes, calibration_record):
    """Reserve all original GPU calls, one recovery and teacher before access."""
    contract_api.require_hash(seal_sha256); _name(bundle_id)
    observed = snapshot(ledger, as_of_utc=as_of_utc)
    contract_api.validate_review(contract, review, actual_source_hashes=actual_source_hashes,
        calibration_record=calibration_record, funding_snapshot=observed,
        as_of_utc=as_of_utc, actual_pricing_sha256=contract_api.digest(contract['protocol']['pricing']))
    ids = {bundle_id+'-modal-escrow', bundle_id+'-teacher'}
    if any(job.get('run_id') in ids or job.get('bundle_id') == bundle_id
           or job.get('final_scale_bundle_id') == bundle_id for job in ledger.get('jobs', [])):
        raise ValueError('Whole-bundle allocation already exists; reconcile instead of reserving twice')
    result = deepcopy(ledger)
    envelope = review['budget_envelope']
    modal = contract_api.money(envelope['modal_compute_bundle_usd'])+contract_api.money(envelope['modal_recovery_allowance_usd'])
    teacher = contract_api.money(envelope['deepseek_teacher_usd'])
    common = {'created_at_utc':as_of_utc, 'status':'reserved', 'freeze_sha256':contract['freeze_sha256'],
        'seal_sha256':seal_sha256, 'bundle_id':bundle_id, 'reservation_is_not_paid_charge':True}
    result['jobs'].append(dict(common,run_id=bundle_id+'-modal-escrow',service='modal',
        reserved_usd=float(modal), original_escrow_usd=float(modal), transferred_usd=0.,
        recovery_claimed=False, additional_protected_usd=float(contract_api.money(envelope['additional_protected_modal_usd']))))
    result['jobs'].append(dict(common,run_id=bundle_id+'-teacher',service='deepseek',reserved_usd=float(teacher),
        final_scale_freeze_sha256=contract['freeze_sha256'],final_scale_seal_sha256=seal_sha256,
        final_scale_bundle_id=bundle_id))
    for service, amount in (('modal',modal),('deepseek',teacher)):
        result['reserved'][service] = float(contract_api.money(result['reserved'][service])+amount)
        account = result[service+'_budget_accounting']
        account['active_reservations_usd'] = float(contract_api.money(account.get('active_reservations_usd',0))+amount)
    return _recount(result)


def validate_escrow(ledger, contract, *, bundle_id, seal_sha256, as_of_utc):
    snapshot(ledger,as_of_utc=as_of_utc)
    jobs = [job for job in ledger['jobs'] if job.get('run_id') == bundle_id+'-modal-escrow' and job.get('service','modal') == 'modal']
    if len(jobs) != 1:
        raise ValueError('One whole-bundle Modal escrow is required')
    escrow = jobs[0]
    if (escrow.get('freeze_sha256') != contract['freeze_sha256'] or escrow.get('seal_sha256') != seal_sha256
            or escrow.get('bundle_id') != bundle_id or escrow.get('status') != 'reserved'):
        raise ValueError('Escrow owner or frozen identity differs')
    children = [job for job in ledger['jobs'] if job.get('bundle_id') == bundle_id
                and job.get('service','modal') == 'modal' and job['run_id'] != escrow['run_id']]
    transferred = sum((contract_api.money(job['reserved_usd']) for job in children),Decimal(0))
    if (transferred != contract_api.money(escrow['transferred_usd'])
            or transferred+contract_api.money(escrow['reserved_usd']) != contract_api.money(escrow['original_escrow_usd'])):
        raise ValueError('Escrow transfers lost, duplicated or silently released liabilities')
    required = contract_api.money(contract['protocol']['bounds']['modal_bundle_including_recovery_usd'])
    if contract_api.money(escrow['original_escrow_usd']) < required:
        raise ValueError('Whole frozen GPU bundle including recovery is underfunded')
    if sum(bool(job.get('is_recovery')) for job in children) > 1:
        raise ValueError('Whole bundle exceeds one recovery call')
    if sum(bool(job.get('is_recovery')) for job in children) != int(escrow['recovery_claimed']):
        raise ValueError('Recovery slot does not match its durable claim')
    protected = contract_api.money(escrow['additional_protected_usd'])
    free = contract_api.money(ledger['limits']['modal'])-contract_api.money(ledger['estimated_spend']['modal'])-contract_api.money(ledger['reserved']['modal'])
    if free < protected:
        raise ValueError('Declared final/API protection is no longer available')
    return escrow


def transfer(ledger, contract, *, bundle_id, seal_sha256, run_id, intent_sha256,
             claim_sha256, as_of_utc, checkpoint, shard_id, is_recovery=False):
    """Move an existing allowance to one pre-dispatch claim, never add spend."""
    _name(run_id);contract_api.require_hash(intent_sha256);contract_api.require_hash(claim_sha256)
    if type(is_recovery) is not bool or checkpoint not in ('base','chosen'):
        raise ValueError('Unknown GPU role or recovery policy')
    if shard_id not in {s['id'] for s in contract['protocol']['shards']}:
        raise ValueError('Unknown shard')
    escrow = validate_escrow(ledger,contract,bundle_id=bundle_id,seal_sha256=seal_sha256,as_of_utc=as_of_utc)
    if any(job.get('run_id') == run_id for job in ledger['jobs']):
        raise ValueError('Dispatch claim already exists; never transfer twice')
    if any(job.get('bundle_id') == bundle_id and job.get('service','modal') == 'modal'
           and job.get('run_id') != escrow['run_id'] and job.get('status') in ACTIVE for job in ledger['jobs']):
        raise ValueError('An existing claimed/running call must reconcile before the next dispatch')
    peers = [j for j in ledger['jobs'] if j.get('bundle_id') == bundle_id
             and j.get('checkpoint') == checkpoint and j.get('shard_id') == shard_id]
    if (not is_recovery and peers) or (is_recovery and (len(peers) != 1 or peers[0].get('status') not in ('failed','cancelled'))):
        raise ValueError('Recovery requires exactly one terminal failed parent; original roles cannot duplicate')
    if is_recovery and escrow['recovery_claimed']:
        raise ValueError('Global recovery slot is already used')
    amount = contract_api.money(contract['protocol']['bounds']['gpu_call_reservation_usd'])
    if contract_api.money(escrow['reserved_usd']) < amount:
        raise ValueError('Escrow cannot fund this call')
    result = deepcopy(ledger);target = next(j for j in result['jobs'] if j['run_id'] == escrow['run_id'])
    target['reserved_usd'] = float(contract_api.money(target['reserved_usd'])-amount)
    target['transferred_usd'] = float(contract_api.money(target['transferred_usd'])+amount)
    target['recovery_claimed'] = target['recovery_claimed'] or is_recovery
    result['jobs'].append({'run_id':run_id,'service':'modal','status':'spawning','reserved_usd':float(amount),
        'freeze_sha256':contract['freeze_sha256'],'seal_sha256':seal_sha256,'bundle_id':bundle_id,
        'checkpoint':checkpoint,'shard_id':shard_id,'is_recovery':is_recovery,
        'intent_sha256':intent_sha256,'claim_sha256':claim_sha256,'created_at_utc':as_of_utc,
        'reservation_is_not_paid_charge':True})
    # Total reserved is unchanged, even when a dispatched child later becomes
    # ambiguous. Only supported provider reconciliation may retire its charge.
    return _recount(result)
