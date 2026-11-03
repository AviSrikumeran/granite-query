"""Reconcile budget against supported provider observations, not fake charges.

Metered workspace usage consumes the project allowance even when credits make
the invoiced amount zero. Collection lag, active jobs, and recent terminal jobs
are represented separately; this is conservative accounting, not a billing cap.
"""
import argparse
import copy
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_CEILING
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'runs/supervisor'
ACTIVE={'reserved','spawned','running','queued','spawning'}
TERMINAL={'completed','failed','cancelled','stopped'}


def utc(value):
    if isinstance(value,datetime):
        result=value
    else:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('Billing timestamps must contain a timezone')
    return result.astimezone(timezone.utc)


def money(value):
    result=Decimal(str(value))
    if not result.is_finite() or result<0:
        raise ValueError('Costs must be finite and nonnegative')
    return result


def ceil_cent(value):
    return value.quantize(Decimal('0.01'),rounding=ROUND_CEILING)


def summarize_public(ledger):
    account=ledger['modal_budget_accounting']
    return {key:account[key] for key in (
        'observed_metered_usd','observed_billed_usd','collection_lag_buffer_usd',
        'active_reservations_usd','pending_terminal_liability_usd',
        'estimated_spend_usd','budget_committed_usd','budget_remaining_usd',
        'snapshot_age_seconds','new_paid_launches_allowed','note')}


def reconcile(ledger,snapshot,*,apps=(),now=None,lag_minutes=15,lag_buffer_usd=3):
    now=utc(now or datetime.now(timezone.utc))
    if lag_minutes<1:
        raise ValueError('Collection-lag interval must be positive')
    result=copy.deepcopy(ledger)
    queried=utc(snapshot['queried_at_utc'])
    if queried>now+timedelta(seconds=60):
        raise ValueError('Provider observation is in the future')
    observed=money(snapshot['metered_cost'])
    billed=money(snapshot['billed_cost'])
    buffer=money(lag_buffer_usd)
    cycle=utc(snapshot['start_utc']).isoformat()
    previous=result.get('modal_budget_accounting')
    if previous is None:
        result.setdefault('accounting_audit',[]).append({
            'converted_at_utc':now.isoformat(),
            'previous_modal_estimated_spend':result['estimated_spend']['modal'],
            'previous_modal_reserved_total':result['reserved']['modal'],
            'reason':'Historical reservation ceilings are retained on jobs for audit; they are not provider charges.'})
    cycles=result.setdefault('modal_cycle_observations',{})
    old_cycle=cycles.get(cycle,{})
    # Keep an observed high-water mark to cover late adjustments conservatively.
    high=max(observed,money(old_cycle.get('high_water_metered_usd',0)))
    cycles[cycle]={'high_water_metered_usd':str(high),'latest_metered_usd':str(observed),
        'latest_billed_usd':str(billed),'queried_at_utc':queried.isoformat()}
    observed_for_budget=sum((money(item['high_water_metered_usd']) for item in cycles.values()),Decimal(0))
    app_by_id={item['app_id']:item for item in apps if item.get('app_id')}
    active=Decimal(0)
    pending=Decimal(0)
    issues=[]
    for job in result.get('jobs',[]):
        if job.get('service','modal')!='modal':
            continue
        amount=money(job.get('reserved_usd',0))
        status=job.get('status','unknown')
        if status in ACTIVE:
            active+=amount
            job['budget_liability']={'kind':'active_or_planned','amount_usd':float(amount)}
            continue
        if status not in TERMINAL:
            active+=amount
            issues.append('Unknown Modal job state: '+str(status))
            job['budget_liability']={'kind':'unknown_state_retained','amount_usd':float(amount)}
            continue
        app=app_by_id.get(job.get('app_id'),{})
        stopped=(job.get('finished_at_utc') or job.get('stopped_at_utc')
                 or app.get('stopped_at') or job.get('provider_app_stopped_at_utc'))
        if stopped:
            ended=utc(stopped)
            job.setdefault('terminal_observed_at_utc',now.isoformat())
            job['provider_app_stopped_at_utc']=ended.isoformat()
        else:
            # Unknown runtime/end time never becomes an invented resource cost.
            # Hold its reservation until we obtain a verified app stop/report.
            ended=None
            job.setdefault('terminal_observed_at_utc',now.isoformat())
        active_app=bool(app and str(app.get('state','')).lower()!='stopped' and
                        str(app.get('tasks','0')).isdigit() and int(app.get('tasks','0'))>0)
        reported_through=job.get('provider_report_covers_through_utc')
        report_confirms=bool(ended and reported_through and utc(reported_through)>=ended)
        lag_elapsed=bool(ended and queried>=ended+timedelta(minutes=lag_minutes))
        if not active_app and (report_confirms or lag_elapsed):
            job['budget_liability']={'kind':'covered_by_observation_after_lag_window',
                'amount_usd':0.0,'note':'Metered observations can still be revised; global lag buffer retained.'}
        else:
            pending+=amount
            job['budget_liability']={'kind':'terminal_usage_pending_collection','amount_usd':float(amount),
                'reason':'Active app or missing verified stop/report' if active_app or ended is None else
                         'Latest billing observation is less than collection-lag interval after app stop'}
    age=max(0.0,(now-queried).total_seconds())
    fresh=age<=lag_minutes*60
    estimated=ceil_cent(observed_for_budget)+buffer
    if previous and not fresh:
        estimated=max(estimated,money(result['estimated_spend']['modal']))
    reserved=active+pending
    committed=estimated+reserved
    ceiling=money(result['limits']['modal'])
    remaining=max(Decimal(0),ceiling-committed)
    # A launch already covered by its reservation can consume the final dollar;
    # reserve() must separately reject any new amount exceeding the ceiling.
    allowed=fresh and not issues and committed<=ceiling
    result['estimated_spend']['modal']=float(estimated)
    result['reserved']['modal']=float(reserved)
    result['observed_modal_spend']=float(observed)
    result['modal_observation']={'metered_usd':float(observed),'billed_usd':float(billed),
        'queried_at_utc':queried.isoformat(),'cycle_start_utc':cycle,
        'source':snapshot.get('source','Modal Workspace.billing.summary'),
        'scope':'Whole authenticated workspace billing cycle; may include unrelated usage, conservatively counted.'}
    result['modal_budget_accounting']={
        'basis':'provider_observed_metered_plus_collection_buffer_and_open_liabilities',
        'observed_metered_usd':float(observed),'observed_billed_usd':float(billed),
        'observed_cycles_high_water_total_usd':float(observed_for_budget),
        'collection_lag_buffer_usd':float(buffer),'collection_lag_minutes':lag_minutes,
        'active_reservations_usd':float(active),'pending_terminal_liability_usd':float(pending),
        'estimated_spend_usd':float(estimated),'budget_committed_usd':float(committed),
        'budget_remaining_usd':float(remaining),'snapshot_age_seconds':round(age,3),
        'new_paid_launches_allowed':allowed,'issues':issues,'updated_at_utc':now.isoformat(),
        'note':'Observed metered usage is distinct from cash billed, buffers, and reservations. Billing collection may lag; these totals are not a provider-enforced cap or final invoice.'}
    result['note']='Modal: observed workspace metered usage plus explicit lag buffer and open liabilities. DeepSeek: retained recorded peak-rate estimate, not invoice. Historical job reservation estimates remain audit records.'
    return result


def fetch_provider():
    import modal
    summary=modal.Workspace.from_context().billing.summary()
    snapshot={'start_utc':summary.start.isoformat(),'end_utc':summary.end.isoformat(),
        'metered_cost':str(summary.metered_cost),'billed_cost':str(summary.billed_cost),
        'cost_breakdown':{key:str(value) for key,value in summary.metered_cost_breakdown.items()},
        'adjustments':{key:str(value) for key,value in summary.adjustments.items()},
        'source':'Supported Modal Workspace.from_context().billing.summary()',
        'queried_at_utc':datetime.now(timezone.utc).isoformat()}
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    process=subprocess.run([sys.executable,'-m','modal','app','list','--json'],
        capture_output=True,timeout=30,check=True,env=env)
    apps=json.loads(process.stdout.decode('utf-8'))
    return snapshot,apps


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh',action='store_true',help='Read supported Modal billing summary and app status; no paid work')
    parser.add_argument('--lag-minutes',type=int,default=15)
    parser.add_argument('--lag-buffer-usd',type=Decimal,default=Decimal('3'))
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    STATE.mkdir(parents=True,exist_ok=True)
    if args.refresh:
        snapshot,apps=fetch_provider()
        (STATE/'modal_billing_snapshot.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
        (STATE/'modal_app_status_snapshot.json').write_text(json.dumps({'queried_at_utc':snapshot['queried_at_utc'],'apps':apps},indent=2),encoding='utf-8')
    else:
        snapshot=json.loads((STATE/'modal_billing_snapshot.json').read_text(encoding='utf-8-sig'))
        app_path=STATE/'modal_app_status_snapshot.json'
        apps=json.loads(app_path.read_text(encoding='utf-8-sig')).get('apps',[]) if app_path.exists() else []
    lock=STATE/'budget_reconcile.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        path=STATE/'budget.json'
        original=path.read_bytes()
        ledger=json.loads(original.decode('utf-8-sig'))
        updated=reconcile(ledger,snapshot,apps=apps,lag_minutes=args.lag_minutes,lag_buffer_usd=args.lag_buffer_usd)
        if not args.dry_run:
            temp=STATE/f'budget.reconcile.{os.getpid()}.tmp'
            temp.write_text(json.dumps(updated,indent=2),encoding='utf-8')
            if path.read_bytes()!=original:
                temp.unlink()
                raise RuntimeError('Ledger changed during reconciliation; retry after owner finishes')
            temp.replace(path)
        print(json.dumps(summarize_public(updated)))
    finally:
        os.close(fd)
        lock.unlink()


if __name__=='__main__':
    main()
