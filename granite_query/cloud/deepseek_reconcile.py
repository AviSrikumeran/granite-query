"""Optional wallet-derived usage accounting with an explicit funding assumption.

GET /user/balance is a balance observation, not an invoice or transaction ledger.
Only the user's declared original USD20 funding is attributed to this project;
new grants, observed credits, currencies or uncertain baselines fail closed.
All wallet details and provenance stay under private runs/supervisor.
"""
import argparse
import copy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud.budget_reconcile import ACTIVE,TERMINAL,ceil_cent,money,utc

STATE=ROOT/'runs/supervisor'
DOCS='https://api-docs.deepseek.com/api/get-user-balance/'
DEEPSEEK_ACTIVE=ACTIVE|{'in_progress','collecting','scheduled'}
ASSUMPTION=('Conditional on the user-declared original funding and no unrecorded '
    'top-ups, grants, refunds or balance adjustments. Whole-wallet consumption '
    'is conservatively attributed to this project. A balance difference is not an invoice.')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def wallet(snapshot):
    entries=snapshot.get('balance_infos',[])
    usd=[entry for entry in entries if entry.get('currency')=='USD']
    if len(usd)!=1:
        raise ValueError('Expected one USD wallet; no currency conversion is inferred')
    for entry in entries:
        if entry.get('currency')!='USD' and any(money(entry.get(key,0)) for key in ('total_balance','granted_balance','topped_up_balance')):
            raise ValueError('Another funded currency makes the funding baseline ambiguous')
    row=usd[0]
    values={key:money(row[key]) for key in ('total_balance','granted_balance','topped_up_balance')}
    if values['total_balance']!=values['granted_balance']+values['topped_up_balance']:
        raise ValueError('Wallet total does not equal its grant and topped-up components')
    return values


def user_declared_baseline(snapshot):
    """Record existing user authorization; never infer or increase paid funding."""
    values=wallet(snapshot)
    if values['granted_balance'] or values['total_balance']>20:
        raise ValueError('A clean USD20 user-declared baseline cannot be established')
    return {'schema_version':1,'currency':'USD','original_funding_usd':'20.00',
        'original_granted_usd':'0.00','project_service_ceiling_usd':'20.00',
        'source':'User explicitly declared the original DeepSeek funding in this project conversation',
        'user_statement_excerpt':'$20 worth of credits into DeepSeek',
        'not_a_provider_preusage_snapshot':True,
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'first_observation_sha256':digest(snapshot),
        'first_observation_queried_at_utc':snapshot['queried_at_utc'],
        'assumption':ASSUMPTION}


def peak_estimate(ledger):
    """Keep recorded peak-rate token estimates distinct from wallet inference."""
    previous=ledger.get('deepseek_budget_accounting',{})
    jobs=sum((money(job.get('accounted_upper_estimate_usd',0)) for job in ledger.get('jobs',[])
        if job.get('service')=='deepseek'),Decimal(0))
    if 'initial_unattributed_peak_estimate_usd' in previous:
        residual=money(previous['initial_unattributed_peak_estimate_usd'])
    else:
        residual=max(Decimal(0),money(ledger['estimated_spend']['deepseek'])-jobs)
    peak=max(money(ledger.get('deepseek_recorded_peak_estimate_usd',0)),jobs+residual)
    return peak,residual


def summarize_public(ledger):
    account=ledger['deepseek_budget_accounting']
    fields=('status','observed_project_usage_usd','observed_usage_high_water_usd',
        'recorded_peak_estimate_usd','collection_lag_buffer_usd','active_reservations_usd',
        'estimated_spend_usd','budget_committed_usd','budget_remaining_usd',
        'snapshot_age_seconds','new_paid_launches_allowed','assumption','note')
    return {key:account.get(key) for key in fields}


def reconcile(ledger,snapshot,baseline,*,now=None,lag_buffer_usd=Decimal('.10'),max_age_minutes=15):
    now=utc(now or datetime.now(timezone.utc))
    if max_age_minutes<=0:
        raise ValueError('Balance observation freshness interval must be positive')
    buffer=money(lag_buffer_usd)
    result=copy.deepcopy(ledger)
    previous=result.get('deepseek_budget_accounting',{})
    peak,residual=peak_estimate(result)
    result['deepseek_recorded_peak_estimate_usd']=float(peak)
    queried=utc(snapshot['queried_at_utc'])
    age=max(0.0,(now-queried).total_seconds())
    issues=[]
    funding_ambiguous=bool(previous.get('funding_history_ambiguous'))
    if funding_ambiguous:
        issues.append('Previously observed wallet credit or baseline change remains unresolved')
    if queried>now+timedelta(seconds=60):
        issues.append('Balance observation timestamp is in the future')
    if money(result['limits']['deepseek'])>20:
        issues.append('Project service ceiling exceeds existing user authorization')
    baseline_hash=digest(baseline) if baseline is not None else None
    baseline_valid=not (not baseline or baseline.get('source')!='User explicitly declared the original DeepSeek funding in this project conversation'
            or baseline.get('currency')!='USD' or money(baseline.get('original_funding_usd',0))!=20
            or money(baseline.get('original_granted_usd',0))!=0
            or money(baseline.get('project_service_ceiling_usd',0))!=20
            or baseline.get('not_a_provider_preusage_snapshot') is not True)
    if not baseline_valid:
        issues.append('Original funding baseline is missing or ambiguous')
    if previous.get('funding_baseline_sha256') and baseline_hash!=previous['funding_baseline_sha256']:
        issues.append('Funding baseline changed; do not infer additional credits')
        funding_ambiguous=True
    values=None
    try:
        values=wallet(snapshot)
    except (ValueError,KeyError,TypeError):
        issues.append('Wallet currency or balance components cannot support the baseline')
        funding_ambiguous=True
    prior=result.get('deepseek_wallet_observation',{})
    if values:
        if values['granted_balance']:
            issues.append('A grant balance makes project-funded usage ambiguous')
            funding_ambiguous=True
        if values['total_balance']>20:
            issues.append('Observed balance exceeds declared original funding')
            funding_ambiguous=True
        if prior and queried<utc(prior['queried_at_utc']):
            issues.append('Balance observation predates the saved observation')
        if prior and values['total_balance']>money(prior['total_balance_usd']):
            issues.append('Wallet balance increased; possible top-up, refund or adjustment')
            funding_ambiguous=True
    if snapshot.get('is_available') is not True:
        issues.append('Provider reports the wallet unavailable')
    reserved=Decimal(0)
    for job in result.get('jobs',[]):
        if job.get('service')!='deepseek':
            continue
        status=job.get('status','unknown')
        if status not in TERMINAL:
            reserved+=money(job.get('reserved_usd',0))
            if status not in DEEPSEEK_ACTIVE:
                issues.append('Unknown DeepSeek job state retains its reservation')
    high=money(previous.get('observed_usage_high_water_usd',0))
    observed=None
    valid=not issues
    if valid:
        observed=Decimal(20)-values['total_balance']
        high=max(high,observed)
        estimated=ceil_cent(high)+buffer
        result['deepseek_wallet_observation']={'queried_at_utc':queried.isoformat(),
            'total_balance_usd':str(values['total_balance']),
            'granted_balance_usd':str(values['granted_balance']),
            'topped_up_balance_usd':str(values['topped_up_balance']),
            'snapshot_sha256':digest(snapshot),'source':'Official GET /user/balance'}
    else:
        estimated=max(peak,money(result['estimated_spend']['deepseek']))
    fresh=age<=max_age_minutes*60
    if not fresh:
        estimated=max(estimated,money(result['estimated_spend']['deepseek']))
    committed=estimated+reserved
    ceiling=money(result['limits']['deepseek'])
    allowed=valid and fresh and committed<=ceiling
    result['estimated_spend']['deepseek']=float(estimated)
    result['reserved']['deepseek']=float(reserved)
    result['deepseek_budget_accounting']={
        'basis':'user_declared_funding_minus_observed_wallet' if valid else 'recorded_peak_estimate_fallback',
        'status':'conditional_wallet_inference' if valid and fresh else ('stale_observation' if valid else 'needs_clarification'),
        'funding_history_ambiguous':funding_ambiguous,
        'funding_baseline_sha256':previous.get('funding_baseline_sha256') or (baseline_hash if baseline_valid else None),
        'observed_project_usage_usd':float(observed) if observed is not None else previous.get('observed_project_usage_usd'),
        'observed_usage_high_water_usd':float(high),'recorded_peak_estimate_usd':float(peak),
        'initial_unattributed_peak_estimate_usd':float(residual),
        'collection_lag_buffer_usd':float(buffer),'active_reservations_usd':float(reserved),
        'estimated_spend_usd':float(estimated),'budget_committed_usd':float(committed),
        'budget_remaining_usd':float(max(Decimal(0),ceiling-committed)),
        'snapshot_age_seconds':round(age,3),'max_snapshot_age_minutes':max_age_minutes,
        'new_paid_launches_allowed':allowed,'issues':issues,'assumption':ASSUMPTION,
        'updated_at_utc':now.isoformat(),
        'note':'Wallet-derived usage, peak-price token estimates and reservations are different quantities. No credit or project ceiling is increased. The small collection buffer is conservative bookkeeping, not a provider-enforced cap.'}
    return result


def require_fresh_deepseek_budget(ledger,*,now=None,new_reservation=False):
    if 'deepseek_budget_accounting' not in ledger:
        return
    account=ledger['deepseek_budget_accounting']
    stamp=ledger.get('deepseek_wallet_observation',{}).get('queried_at_utc')
    if (not stamp or account.get('issues') or
            (new_reservation and not account.get('new_paid_launches_allowed',False))):
        raise RuntimeError('Refresh or clarify DeepSeek balance accounting before new paid work')
    age=(utc(now or datetime.now(timezone.utc))-utc(stamp)).total_seconds()
    if age<0 or age>account.get('max_snapshot_age_minutes',15)*60:
        raise RuntimeError('DeepSeek balance observation is stale; refresh deepseek_reconcile.py')
    if money(ledger['estimated_spend']['deepseek'])+money(ledger['reserved']['deepseek'])>money(ledger['limits']['deepseek']):
        raise RuntimeError('DeepSeek budget commitments exceed the ceiling')


def fetch_provider():
    from cloud.run_api_pilot import credential
    key=credential('DEEPSEEK_API_KEY')
    if not key:
        raise RuntimeError('DeepSeek credential missing')
    request=urllib.request.Request('https://api.deepseek.com/user/balance',
        headers={'Authorization':'Bearer '+key,'Accept':'application/json'},method='GET')
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            payload=json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError('DeepSeek balance HTTP '+str(exc.code)) from None
    except urllib.error.URLError:
        raise RuntimeError('DeepSeek balance network request failed') from None
    return dict(payload,queried_at_utc=datetime.now(timezone.utc).isoformat(),
        source='Official DeepSeek GET /user/balance')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true',help='Read only the documented balance endpoint; no generation')
    parser.add_argument('--initialize-user-declared-20',action='store_true',help='Save existing user-declared USD20 funding provenance; never infer a top-up')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--lag-buffer-usd',type=Decimal,default=Decimal('.10'))
    args=parser.parse_args()
    STATE.mkdir(parents=True,exist_ok=True)
    snapshot_path=STATE/'deepseek_balance_snapshot.json'
    snapshot=fetch_provider() if args.refresh else json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
    lock=STATE/'budget_reconcile.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        path=STATE/'budget.json'; original=path.read_bytes();ledger=json.loads(original)
        baseline_path=STATE/'deepseek_funding_baseline.json'
        baseline=json.loads(baseline_path.read_text(encoding='utf-8-sig')) if baseline_path.exists() else None
        if baseline is None and args.initialize_user_declared_20:
            baseline=user_declared_baseline(snapshot)
        updated=reconcile(ledger,snapshot,baseline,lag_buffer_usd=args.lag_buffer_usd)
        if not args.dry_run:
            if path.read_bytes()!=original:
                raise RuntimeError('Ledger changed concurrently; retry after the owner finishes')
            if baseline is not None and not baseline_path.exists():
                baseline_path.write_text(json.dumps(baseline,indent=2),encoding='utf-8')
            if args.refresh:
                snapshot_path.write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
            temp=STATE/f'budget.deepseek.{os.getpid()}.tmp'
            temp.write_text(json.dumps(updated,indent=2),encoding='utf-8');temp.replace(path)
        print(json.dumps(summarize_public(updated)))
    finally:
        os.close(fd);lock.unlink()


if __name__=='__main__':
    main()
