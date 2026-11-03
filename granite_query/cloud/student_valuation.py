"""Student-aware heuristic selection with exact supervised-token controls.

This estimates useful data; it does not measure causal training influence. Imports
never download models or launch GPU/API work. Only the pinned tokenizer is loaded
when prepare is requested. Candidate traces remain complete and unchanged.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import random
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parent
MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')
VERSION = 'student-skill-diversity-v1'
SKILL_PATTERNS = {
    'rates_and_units': r'\b(per|rate|speed|hours?|minutes?|seconds?|miles?|kilometers?|liters?|gallons?)\b',
    'cost_accounting': r'\$|\b(cost|price|dollars?|spent|spend|buy|bought|fee|monthly|payment|profit)\b',
    'percentages': r'%|\b(percent|percentage|discount|interest)\b',
    'geometry': r'\b(area|perimeter|rectangle|square|width|length|volume|feet|inches)\b',
    'fractions_and_ratios': r'\b(half|third|quarter|fraction|ratio|twice|double)\b|\d\s*/\s*\d',
    'counting_and_remainders': r'\b(total|remaining|left|more|less|sum|difference|each)\b',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def read_jsonl(path):
    path = Path(path)
    if path.name.casefold() in {'test.jsonl', 'test.json', 'official_test.jsonl'}:
        raise ValueError('Official test inputs are forbidden in data selection')
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').split('\n') if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Require nonempty object records')
    return rows


def normalized_question(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def skill_tags(text):
    tags = [name for name, pattern in SKILL_PATTERNS.items() if re.search(pattern, text, re.I)]
    return tags or ['general_arithmetic']


def load_tokenizer(*, local_files_only=False):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(MODEL, revision=REVISION,
        cache_dir=ROOT / 'runs/tokenizer_cache', local_files_only=local_files_only)


def encode_example(row, tokenizer):
    """Exact tokenization shared with the current Granite workers; no truncation."""
    rendered = tokenizer.apply_chat_template([{'role': 'user', 'content': PREFIX + row['prompt']}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prefix_ids = tokenizer(rendered, add_special_tokens=False)['input_ids']
    answer_ids = tokenizer(row['response'] + tokenizer.eos_token, add_special_tokens=False)['input_ids']
    return {'prefix_ids': prefix_ids, 'answer_ids': answer_ids,
            'prompt_tokens': len(prefix_ids), 'response_tokens': len(answer_ids),
            'input_tokens': len(prefix_ids) + len(answer_ids)}


def _verified(row):
    if row.get('finish_reason') in ('length', 'abort') or row.get('truncated') is True:
        return False
    generation = row.get('generation') if isinstance(row.get('generation'), dict) else {}
    verification = row.get('verification', generation.get('verification'))
    if (row.get('verified_final_answer') is True and isinstance(verification, dict)
            and verification.get('math_verify') is True and verification.get('complete') is True
            and verification.get('boxed_numeric_match') is True
            and verification.get('trace_truncated') is False):
        from decimal import Decimal, InvalidOperation
        matches = re.findall(r'\\boxed\{([+-]?(?:(?:\d[\d,]*)(?:\.\d*)?|\.\d+))\}', row.get('response', ''))
        try:
            if matches and Decimal(matches[-1].replace(',', '')) == Decimal(str(row.get('gold_answer', '')).replace(',', '')):
                recorded_hash = generation.get('raw_response_sha256')
                return recorded_hash is None or recorded_hash == digest_bytes(row['response'].encode('utf-8'))
        except InvalidOperation:
            return False
    try:
        sys.path.insert(0, str(ROOT.parent))
        from ranking.verification import teacher_eligible
        return teacher_eligible(row)[0]
    except (ImportError, TypeError, ValueError):
        return False


def _write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _write_jsonl(path, rows):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def freeze_weakness(predictions_path, questions_path, output_path, source_kind, source_run):
    """Aggregate errors by heuristic skill without exposing eval answers to ranking."""
    if source_kind not in ('training_probe_predictions', 'development_predictions'):
        raise ValueError('Weakness signal must come from training probes or declared development predictions')
    questions = read_jsonl(questions_path)
    by_id = {row['id']: row for row in questions}
    if len(by_id) != len(questions) or any(row.get('source_split') != 'train' for row in questions):
        raise ValueError('Question metadata must prove unique official-training-split records')
    text = Path(predictions_path).read_text(encoding='utf-8-sig')
    try:
        predictions = json.loads(text)
    except ValueError:
        predictions = [json.loads(line) for line in text.split('\n') if line.strip()]
    if not isinstance(predictions, list) or not predictions:
        raise ValueError('Predictions must be a nonempty JSON array or JSONL of evaluation rows')
    ids = [row['id'] for row in predictions]
    if len(set(ids)) != len(ids) or any(row_id not in by_id for row_id in ids):
        raise ValueError('Predictions need unique IDs present in training-split question metadata')
    try:
        from .comparison_metrics import score
    except ImportError:
        from comparison_metrics import score
    counts, errors = Counter(), Counter()
    for row in predictions:
        question = by_id[row['id']]
        checked = dict(row, gold_answer=question['gold_answer'])
        incorrect = not score(checked)['correct']
        for tag in skill_tags(question['prompt']):
            counts[tag] += 1
            errors[tag] += int(incorrect)
    signal = {'schema_version': 1, 'frozen_at_utc': now(),
        'provenance': {'source_kind': source_kind, 'source_run': source_run, 'source_split': 'train',
            'official_test_used': False, 'prediction_sha256': digest_bytes(Path(predictions_path).read_bytes()),
            'questions_sha256': digest_bytes(Path(questions_path).read_bytes()),
            'question_ids': ids, 'question_hashes': [digest_bytes(normalized_question(by_id[i]['prompt']).encode()) for i in ids],
            'interpretation': ('Independent training-probe signal' if source_kind == 'training_probe_predictions'
                               else 'Adaptive development-derived signal; downstream evaluation on this set is not independent')},
        'skill_tagger': 'Frozen lexical rules, not verified latent reasoning-skill labels',
        'skills': {tag: {'count': counts[tag], 'errors': errors[tag],
            'smoothed_error_rate': (errors[tag] + 1) / (counts[tag] + 2)} for tag in sorted(counts)}}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _write_new(output_path, signal)
    return signal


def prepare(candidates_path, weakness_path, output, *, exclude_paths=(), context_limit=2048,
            max_response_tokens=768, min_response_tokens=16, tokenizer=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Prepared artifacts are immutable; use a new output directory')
    candidates = read_jsonl(candidates_path)
    signal = json.loads(Path(weakness_path).read_text(encoding='utf-8-sig'))
    provenance = signal.get('provenance', {})
    if (provenance.get('source_kind') not in ('training_probe_predictions', 'development_predictions', 'development_skill_aggregates')
            or provenance.get('source_split') != 'train' or provenance.get('official_test_used') is not False
            or not signal.get('skills')):
        raise ValueError('Weakness provenance must establish declared training-probe/development use and no official test')
    forbidden_ids = set(provenance.get('question_ids', []))
    forbidden_questions = set(provenance.get('question_hashes', []))
    exclusion_sources = []
    for path in exclude_paths:
        rows = read_jsonl(path)
        if any(row.get('source_split', 'train') != 'train' for row in rows):
            raise ValueError('Exclusion metadata must be training-split probes/development, never official test')
        forbidden_ids.update(row['id'] for row in rows)
        forbidden_questions.update(digest_bytes(normalized_question(row['prompt']).encode()) for row in rows)
        exclusion_sources.append({'sha256': digest_bytes(Path(path).read_bytes()), 'count': len(rows)})
    tokenizer = tokenizer or load_tokenizer()
    prepared, exclusions, seen_ids, seen_questions = [], [], set(), set()
    for row in sorted(candidates, key=lambda r: str(r.get('id', ''))):
        row_id = row.get('id')
        if not isinstance(row_id, str) or not row_id or row_id in seen_ids:
            raise ValueError('Candidate IDs must be nonempty and unique')
        seen_ids.add(row_id)
        if row.get('source_split') != 'train':
            raise ValueError('Selection accepts source_split=train only')
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('prompt', 'gold_answer')):
            raise ValueError('Candidate requires nonempty prompt and gold_answer strings')
        question_hash = digest_bytes(normalized_question(row['prompt']).encode())
        reason = None
        if row_id in forbidden_ids or question_hash in forbidden_questions:
            reason = 'probe_or_development_overlap'
        elif question_hash in seen_questions:
            reason = 'duplicate_question'
        elif not isinstance(row.get('response'), str) or not row['response'].strip():
            reason = 'missing_response'
        elif not _verified(row):
            reason = 'verification_missing_or_failed'
        else:
            encoded = encode_example(row, tokenizer)
            if not min_response_tokens <= encoded['response_tokens'] <= max_response_tokens:
                reason = 'response_token_feasibility'
            elif encoded['input_tokens'] > context_limit:
                reason = 'context_limit'
        if reason:
            exclusions.append({'id': row_id, 'reason': reason})
            continue
        seen_questions.add(question_hash)
        tags = row.get('skills') if isinstance(row.get('skills'), list) and row['skills'] else skill_tags(row['prompt'])
        if any(not isinstance(tag, str) or not tag for tag in tags):
            raise ValueError('Skill tags must be nonempty strings')
        rates = [float(signal['skills'].get(tag, {}).get('smoothed_error_rate', 0.5)) for tag in tags]
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in rates):
            raise ValueError('Weakness rates must be finite probabilities')
        prepared.append(dict(row, **encoded, skills=sorted(set(tags)),
            weakness_score=sum(rates)/len(rates), question_sha256=question_hash,
            raw_response_sha256=digest_bytes(row['response'].encode('utf-8'))))
    if len(prepared) < 2:
        raise ValueError('Fewer than two feasible verified nonoverlapping candidates')
    output.mkdir(parents=True, exist_ok=False)
    _write_jsonl(output / 'eligible.jsonl', prepared)
    _write_jsonl(output / 'exclusions.jsonl', exclusions)
    backend = getattr(tokenizer, 'backend_tokenizer', None)
    tokenizer_hash = digest_bytes(backend.to_str().encode()) if backend is not None else 'test-tokenizer'
    manifest = {'schema_version': 1, 'prepared_at_utc': now(), 'method_version': VERSION,
        'tokenizer': {'model': MODEL, 'revision': REVISION, 'backend_sha256': tokenizer_hash,
            'chat_template_sha256': digest_bytes(str(tokenizer.chat_template).encode()),
            'encoding': 'apply_chat_template enable_thinking=False; separately encode prefix and exact response+EOS, add_special_tokens=False'},
        'inputs': {'candidates_sha256': digest_bytes(Path(candidates_path).read_bytes()),
            'weakness_sha256': digest_bytes(Path(weakness_path).read_bytes()), 'exclusions': exclusion_sources},
        'weakness_provenance': provenance, 'skill_signal': signal['skills'],
        'limits': {'context': context_limit, 'max_response_tokens': max_response_tokens, 'min_response_tokens': min_response_tokens},
        'counts': {'input': len(candidates), 'eligible': len(prepared), 'excluded': len(exclusions)},
        'eligible_sha256': digest_bytes((output / 'eligible.jsonl').read_bytes()),
        'official_test_used': False, 'training_ready': True,
        'interpretation': 'Student weakness, lexical diversity, and length feasibility are heuristic selection signals; not measured causal data value.'}
    _write_new(output / 'manifest.json', manifest)
    return manifest


def _shingles(text):
    words = re.findall(r'\w+|[^\w\s]', normalized_question(text))
    return {tuple(words[i:i+3]) for i in range(max(1, len(words)-2))}


def _choose_valued(rows, budget):
    remaining = list(rows)
    selected, decisions, used_skills, used_shingles = [], [], Counter(), []
    total = 0
    median = sorted(row['response_tokens'] for row in rows)[len(rows)//2]
    while total < budget and remaining:
        scored = []
        for row in remaining:
            shingles = _shingles(row['prompt'])
            novelty = 1.0 if not used_shingles else 1-max(len(shingles&prior)/max(1,len(shingles|prior)) for prior in used_shingles)
            coverage = sum(1/(1+used_skills[tag]) for tag in row['skills'])/len(row['skills'])
            length_factor = (row['response_tokens']/median)**0.25
            value = (0.65*row['weakness_score']+0.20*novelty+0.15*coverage)/length_factor
            scored.append((value, row['id'], row, novelty, coverage))
        value, _, chosen, novelty, coverage = sorted(scored, key=lambda item:(-item[0],item[1]))[0]
        selected.append(chosen)
        decisions.append({'id':chosen['id'],'score':value,'weakness':chosen['weakness_score'],
                          'novelty':novelty,'coverage':coverage,'response_tokens':chosen['response_tokens']})
        total += chosen['response_tokens']
        used_skills.update(chosen['skills'])
        used_shingles.append(_shingles(chosen['prompt']))
        remaining = [row for row in remaining if row['id'] != chosen['id']]
    if total < budget:
        raise ValueError('Shared eligible pool cannot supply requested supervised-token budget without repeats')
    return selected, decisions


def _exposure(rows, budget, seed, tokens_per_update):
    """Common hash-shuffle policy, exact label masks and equal-token update plan."""
    ordered = sorted(rows, key=lambda row:digest_bytes(f'{seed}:{row["id"]}'.encode()))
    remaining = budget
    training = []
    for row in ordered:
        if remaining == 0:
            break
        count = min(row['response_tokens'], remaining)
        prefix, answer = row['prefix_ids'], row['answer_ids']
        labels = [-100]*len(prefix) + answer[:count] + [-100]*(len(answer)-count)
        training.append({key:row[key] for key in ('id','prompt','response','gold_answer','skills','raw_response_sha256')})
        training[-1].update({'input_ids':prefix+answer,'labels':labels,'attention_mask':[1]*(len(prefix)+len(answer)),
            'prefix_tokens':len(prefix),'full_response_tokens':len(answer),'supervised_tokens':count,
            'partial_supervised_tail':count<len(answer)})
        remaining -= count
    if remaining:
        raise ValueError('Insufficient selected tokens')
    updates=[]
    current={'index':0,'supervised_tokens':0,'microbatches':[]}
    for row in training:
        start=0
        while start<row['supervised_tokens']:
            count=min(row['supervised_tokens']-start,tokens_per_update-current['supervised_tokens'])
            current['microbatches'].append({'id':row['id'],'answer_start':start,'answer_end':start+count,
                'supervised_tokens':count,'loss_weight':count/tokens_per_update})
            current['supervised_tokens']+=count
            start+=count
            if current['supervised_tokens']==tokens_per_update:
                updates.append(current)
                current={'index':len(updates),'supervised_tokens':0,'microbatches':[]}
    if current['supervised_tokens']:
        raise ValueError('Token budget must be a multiple of tokens_per_update')
    return training, updates


def select(prepared_path, output, token_budget, *, seed=42, tokens_per_update=1024):
    prepared_path, output = Path(prepared_path), Path(output)
    if output.exists():
        raise FileExistsError('Selection artifacts are immutable; use a new output directory')
    if token_budget<=0 or tokens_per_update<=0 or token_budget%tokens_per_update:
        raise ValueError('Use a positive budget divisible by tokens_per_update')
    prepared_manifest=json.loads((prepared_path/'manifest.json').read_text(encoding='utf-8'))
    eligible_path=prepared_path/'eligible.jsonl'
    if digest_bytes(eligible_path.read_bytes())!=prepared_manifest['eligible_sha256']:
        raise ValueError('Prepared pool changed after token counting')
    rows=read_jsonl(eligible_path)
    if sum(row['response_tokens'] for row in rows)<token_budget:
        raise ValueError('Shared eligible pool cannot supply requested budget without repeats')
    valued,decisions=_choose_valued(rows,token_budget)
    permutation=sorted(rows,key=lambda row:row['id'])
    random.Random(seed).shuffle(permutation)
    control=[];total=0
    for row in permutation:
        control.append(row);total+=row['response_tokens']
        if total>=token_budget:
            break
    output.mkdir(parents=True,exist_ok=False)
    arm_summaries={}
    for name, selected in [('valued',valued),('random',control)]:
        training,updates=_exposure(selected,token_budget,seed,tokens_per_update)
        artifact={'schema_version':1,'arm':name,'token_budget':token_budget,
            'tokens_per_update':tokens_per_update,'optimizer_updates':len(updates),
            'tokenizer':prepared_manifest['tokenizer'],'training':training,'updates':updates,
            'worker_contract':'For each update, build labels only for each microbatch answer_start:answer_end span. Backprop mean token loss multiplied by loss_weight, then clip and optimizer.step ONCE per update. Do not step per example or per microbatch.'}
        _write_new(output/(name+'_input.json'),artifact)
        arm_summaries[name]={'examples':len(training),'selected_ids':[row['id'] for row in training],
            'supervised_tokens':sum(row['supervised_tokens'] for row in training),'optimizer_updates':len(updates),
            'partial_supervised_tails':sum(row['partial_supervised_tail'] for row in training),
            'input_tokens_once':sum(len(row['input_ids']) for row in training),
            'input_tokens_forwarded':sum(len(next(row for row in training if row['id']==batch['id'])['input_ids'])
                                         for update in updates for batch in update['microbatches']),
            'unexposed_preselected_ids':[row['id'] for row in selected if row['id'] not in {r['id'] for r in training}]}
    _write_jsonl(output/'valuation_decisions.jsonl',decisions)
    manifest={'schema_version':1,'created_at_utc':now(),'method_version':VERSION,'seed':seed,
        'prepared_manifest_sha256':digest_bytes((prepared_path/'manifest.json').read_bytes()),
        'prepared_eligible_sha256':prepared_manifest['eligible_sha256'],'tokenizer':prepared_manifest['tokenizer'],
        'token_budget':token_budget,'tokens_per_update':tokens_per_update,'arms':arm_summaries,
        'shared_pool_count':len(rows),'arm_overlap':len(set(arm_summaries['valued']['selected_ids'])&set(arm_summaries['random']['selected_ids'])),
        'selection_policy':'valued: fixed heuristic weakness/novelty/skill-coverage utility with mild length penalty; random: seeded uniform candidate permutation until budget coverage',
        'order_policy':'Both arms hash-shuffled by SHA256(seed:id); overlapping examples have the same relative order',
        'weights':{'weakness':0.65,'lexical_novelty':0.20,'skill_coverage':0.15,'length_power':0.25},
        'matching':'Exactly equal supervised-token counts and optimizer updates; not necessarily equal example counts, input compute, or wall-clock cost',
        'tail_policy':'The last supervised record may have a partially masked answer tail. Full input trace is retained unchanged; complete-trace supervision is not claimed.',
        'weakness_provenance':prepared_manifest['weakness_provenance'],'official_test_used':False,
        'artifacts_sha256':{path.name:digest_bytes(path.read_bytes()) for path in sorted(output.glob('*.json'))}}
    _write_new(output/'manifest.json',manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='action',required=True)
    weak=commands.add_parser('weakness')
    weak.add_argument('--predictions',type=Path,required=True)
    weak.add_argument('--questions',type=Path,required=True)
    weak.add_argument('--output',type=Path,required=True)
    weak.add_argument('--source-kind',choices=['training_probe_predictions','development_predictions'],required=True)
    weak.add_argument('--source-run',required=True)
    prep=commands.add_parser('prepare')
    prep.add_argument('--candidates',type=Path,required=True)
    prep.add_argument('--weakness',type=Path,required=True)
    prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--exclude-questions',type=Path,action='append',default=[])
    prep.add_argument('--context-limit',type=int,default=2048)
    prep.add_argument('--max-response-tokens',type=int,default=768)
    prep.add_argument('--min-response-tokens',type=int,default=16)
    choose=commands.add_parser('select')
    choose.add_argument('--prepared',type=Path,required=True)
    choose.add_argument('--output',type=Path,required=True)
    choose.add_argument('--token-budget',type=int,required=True)
    choose.add_argument('--tokens-per-update',type=int,default=1024)
    choose.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    if args.action=='weakness':
        result=freeze_weakness(args.predictions,args.questions,args.output,args.source_kind,args.source_run)
        print(json.dumps({'skills':result['skills'],'source_kind':args.source_kind}))
    elif args.action=='prepare':
        result=prepare(args.candidates,args.weakness,args.output,exclude_paths=args.exclude_questions,
            context_limit=args.context_limit,max_response_tokens=args.max_response_tokens,min_response_tokens=args.min_response_tokens)
        print(json.dumps({'counts':result['counts'],'tokenizer':result['tokenizer']}))
    else:
        result=select(args.prepared,args.output,args.token_budget,seed=args.seed,tokens_per_update=args.tokens_per_update)
        print(json.dumps({'arms':result['arms'],'token_budget':result['token_budget']}))


if __name__=='__main__':
    main()
