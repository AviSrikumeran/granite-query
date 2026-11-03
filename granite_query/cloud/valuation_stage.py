"""Idempotent LOCAL preparation of the reviewed32768-token/two-seed protocol.

No provider calls, budget reservations, or GPU launches. A finalized collector
summary and released lock are mandatory before reading its candidate pool.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud.student_valuation import prepare as prepare_pool,select,load_tokenizer
from cloud.valuation_control import prepare as prepare_arm
from cloud.progress import record


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collector_ready(folder):
    folder=Path(folder)
    summary_path=folder/'teacher_summary.json'
    if not summary_path.exists():
        return False,'collector summary missing'
    summary=json.loads(summary_path.read_text(encoding='utf-8'))
    if summary.get('stage')!='completed':
        return False,'collector not finalized: '+str(summary.get('stage'))
    if (folder/'collector.lock').exists():
        return False,'collector lock still held'
    if summary.get('completed')!=summary.get('requested') or summary.get('requested')!=512:
        raise ValueError('Unexpected finalized collection size')
    return True,'finalized512 collection with released lock'


def run_stage():
    source=ROOT/'runs/student_valuation_pool512_v1'
    ready,reason=collector_ready(source)
    if not ready:
        result={'stage':'waiting','reason':reason,'paid_work_launched':False}
        print(json.dumps(result))
        return result
    candidates=source/'eligible.jsonl'
    weakness=ROOT/'runs/student_valuation_dev64_v1/weakness.json'
    prepared=ROOT/'runs/student_valuation_pool512_prepared_v1'
    development=ROOT/'runs/matched_eval64_v1/development.jsonl'
    exclusions=[development,ROOT/'runs/ranked_random_32_seed42_v1/development.jsonl',
        ROOT/'runs/ranked_random_32_seed42_v1/candidates.jsonl',
        ROOT/'runs/deepseek32b_pilot16_seed42/local_sources.jsonl',
        ROOT.parent/'ranking/runs/gsm8k_preview_128_seed42/target_queries.jsonl']
    if not prepared.exists():
        prepare_pool(candidates,weakness,prepared,exclude_paths=exclusions,
            context_limit=2048,max_response_tokens=768,min_response_tokens=16,
            tokenizer=load_tokenizer(local_files_only=True))
    prepared_manifest=json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    if (prepared_manifest['inputs']['candidates_sha256']!=sha(candidates)
            or prepared_manifest['inputs']['weakness_sha256']!=sha(weakness)
            or prepared_manifest['eligible_sha256']!=sha(prepared/'eligible.jsonl')):
        raise ValueError('Prepared source or weakness signal changed; do not mutate frozen artifacts')
    outputs=[]
    for seed in (42,43):
        selection=ROOT/f'runs/student_valuation32768_seed{seed}_v1'
        if not selection.exists():
            select(prepared,selection,32768,seed=seed,tokens_per_update=1024)
        manifest=json.loads((selection/'manifest.json').read_text(encoding='utf-8'))
        if (manifest['seed']!=seed or manifest['token_budget']!=32768
                or manifest['prepared_manifest_sha256']!=sha(prepared/'manifest.json')):
            raise ValueError('Existing selection differs from frozen protocol')
        for arm in ('random','valued'):
            folder=ROOT/f'runs/student_valuation32768_seed{seed}_{arm}_v1'
            if not folder.exists():
                prepare_arm(selection,arm,development,folder,
                    probe_pool=prepared/'eligible.jsonl' if seed==42 and arm=='random' else None)
            plan=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
            if (plan['seed']!=seed or plan['arm']!=arm or plan['token_budget']!=32768
                    or plan['selection_manifest_sha256']!=sha(selection/'manifest.json')
                    or plan['arm_source_sha256']!=sha(selection/(arm+'_input.json'))
                    or plan['input_sha256']!=sha(folder/'input.json')
                    or plan['development_source_sha256']!=sha(development)):
                raise ValueError('Existing arm worker differs from frozen protocol')
            outputs.append({'run_id':folder.name,'path':str(folder),'seed':seed,'arm':arm,
                'token_budget':plan['token_budget'],'launch_exists':(folder/'launch.json').exists()})
    record('planned','Two-seed exact-token valuation protocol prepared',
        'Finalized the shared verified512-attempt teacher pool, excluded monitoring/probe overlaps, and prepared valued/random arms for seeds42 and43. Each arm has32768 supervised answer tokens and32 token-weighted optimizer updates, learning rate0.00002, and the same64 development questions. Weakness signals are explicitly development-derived; no official test was accessed. Preparation launched no GPU jobs.','valuation32768-two-seed-prepared')
    result={'stage':'prepared','eligible':prepared_manifest['counts']['eligible'],'arms':outputs,
        'first_run_id':'student_valuation32768_seed42_random_v1','paid_work_launched':False}
    print(json.dumps(result))
    return result


if __name__=='__main__':
    run_stage()
