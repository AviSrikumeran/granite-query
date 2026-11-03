"""Unpaid reference math for a future LESS-inspired selection experiment.

This module imports no tensor/model packages, collects no gradients, and launches
no cloud work. Feature collection needs a separate reviewed GPU worker. The small
Rademacher projector here is a bounded reference implementation for correctness
fixtures, not the production projector for millions of LoRA parameters.

The default score matches the released LESS matching code: normalize each example
feature, average cosine scores within a target group, accumulate checkpoint
weights, then take the maximum group. The paper's cosine-to-mean-vector reduction
is exposed separately and must be explicitly predeclared.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

METHOD = 'projected-lora-gradient-alignment-v1'
REDUCTIONS = {'mean_per_target_cosine', 'cosine_to_mean_gradient'}


def _vector(values):
    result = [float(value) for value in values]
    if not result or any(not math.isfinite(value) for value in result):
        raise ValueError('Features must be nonempty finite vectors')
    return result


def normalize(values):
    values = _vector(values)
    norm = math.sqrt(math.fsum(value*value for value in values))
    if not math.isfinite(norm) or norm <= 1e-30:
        raise ValueError('Zero/nonfinite gradient features cannot be ranked')
    return [value/norm for value in values]


def dot(first, second):
    if len(first) != len(second):
        raise ValueError('Feature dimensions differ')
    return math.fsum(a*b for a,b in zip(first,second))


def less_adam_direction(gradient, moment, second_moment, *, beta1=0.9, beta2=0.999, eps=1e-8):
    """Match LESS collect_grad_reps.py's hypothetical candidate direction.

    Warmup moments are read-only. The authors' proxy uses sqrt(v'+eps) and omits
    bias correction, weight decay and clipping; this is NOT the exact PyTorch
    AdamW parameter update or the marginal effect of adding an example to a batch.
    """
    gradient, moment, second_moment = map(_vector,(gradient,moment,second_moment))
    if len(gradient) != len(moment) or len(moment) != len(second_moment):
        raise ValueError('Gradient/moment parameter layouts differ')
    if not 0 <= beta1 < 1 or not 0 <= beta2 < 1 or not math.isfinite(eps) or eps <= 0:
        raise ValueError('Invalid optimizer proxy configuration')
    if any(value < 0 for value in second_moment):
        raise ValueError('Second moments cannot be negative')
    return [(beta1*m+(1-beta1)*g)/math.sqrt(beta2*v+(1-beta2)*g*g+eps)
            for g,m,v in zip(gradient,moment,second_moment)]


def rademacher_reference(values, dimension, *, seed=42, max_work=1000000):
    """Dense +/-1/sqrt(d) JL fixture; refuse accidental large Python projection.

    Parameter coordinate order must already match the frozen named layout. A
    SHAKE256-generated sign row avoids allocating a full P-by-d matrix. This
    deterministic reference is not bit-compatible with TRAK's CUDA projector.
    """
    values = _vector(values)
    if type(dimension) is not int or dimension < 1 or type(seed) is not int:
        raise ValueError('Require positive dimension and integer projection seed')
    if len(values)*dimension > max_work:
        raise ValueError('Reference projection work cap exceeded; use a reviewed batched CUDA projector')
    output = [0.0]*dimension
    for index,value in enumerate(values):
        bits = hashlib.shake_256(f'gradient-jl-v1:{seed}:{index}'.encode()).digest((dimension+7)//8)
        for column in range(dimension):
            output[column] += value*(1 if (bits[column//8] >> (column%8)) & 1 else -1)
    scale = 1/math.sqrt(dimension)
    return [value*scale for value in output]


def _records(rows, dimension, role):
    result = {}
    for row in rows:
        key = row.get('id')
        if not isinstance(key,str) or not key or key in result:
            raise ValueError('Feature IDs must be unique and nonempty')
        if row.get('source_split') != 'train':
            raise ValueError('Only official-training-split records may be used for selection')
        question_hash = row.get('question_sha256')
        if not isinstance(question_hash,str) or len(question_hash) != 64 or any(c not in '0123456789abcdef' for c in question_hash):
            raise ValueError('Each feature needs a normalized-question SHA256 for overlap exclusion')
        if role == 'candidate' and row.get('verified_final_answer') is not True:
            raise ValueError('Correctness/completion gate must precede gradient usefulness scoring')
        if role == 'target' and (not isinstance(row.get('group'),str) or not row['group']):
            raise ValueError('Target development gradients require a frozen task group')
        vector = _vector(row['feature'])
        if len(vector) != dimension:
            raise ValueError('Projection dimensions differ from manifest')
        result[key] = dict(row,feature=vector,unit=normalize(vector))
    if not result:
        raise ValueError('Require both candidates and target development features')
    return result


def score_projected(payload, *, reduction='mean_per_target_cosine'):
    """Return deterministic signed first-order utility proxies, not causal values."""
    if reduction not in REDUCTIONS:
        raise ValueError('Unknown target aggregation policy')
    if payload.get('official_test_used') is not False or payload.get('target_role') != 'selection_development':
        raise ValueError('A separate explicitly labeled selection-development set is required')
    projection = payload.get('projection',{})
    dimension = projection.get('dimension')
    if type(dimension) is not int or not 1 <= dimension <= 8192 or projection.get('family') != 'rademacher_jl':
        raise ValueError('Require frozen Rademacher JL features of dimension at most8192')
    layout = projection.get('parameter_layout_sha256')
    if not isinstance(layout,str) or len(layout) != 64 or any(c not in '0123456789abcdef' for c in layout):
        raise ValueError('A frozen named trainable-parameter layout hash is required')
    if type(projection.get('seed')) is not int:
        raise ValueError('Projection seed must be frozen')
    checkpoints = payload.get('checkpoints',[])
    if not checkpoints or len(checkpoints) > 4:
        raise ValueError('Require one to four bounded warmup checkpoints')
    weights = [float(checkpoint['weight']) for checkpoint in checkpoints]
    if any(not math.isfinite(value) or value <= 0 for value in weights):
        raise ValueError('Checkpoint weights must be finite positive average learning rates')
    total_weight = math.fsum(weights)
    weights = [value/total_weight for value in weights]
    accumulated, candidate_ids, target_identity, checkpoint_ids = {}, None, None, set()
    for checkpoint,weight in zip(checkpoints,weights):
        if checkpoint.get('id') in checkpoint_ids or not checkpoint.get('id'):
            raise ValueError('Warmup checkpoint IDs must be unique')
        checkpoint_ids.add(checkpoint['id'])
        if checkpoint.get('candidate_gradient_type') != 'less_adam' or checkpoint.get('target_gradient_type') != 'sgd':
            raise ValueError('Do not silently mix optimizer-aware candidate and raw target gradients')
        candidates = _records(checkpoint['candidates'],dimension,'candidate')
        targets = _records(checkpoint['targets'],dimension,'target')
        if len(candidates) > 10000 or len(targets) > 256:
            raise ValueError('Reference scoring row cap exceeded')
        if set(candidates)&set(targets) or ({row['question_sha256'] for row in candidates.values()} &
                                           {row['question_sha256'] for row in targets.values()}):
            raise ValueError('Candidate and target development questions must be disjoint')
        identity = {key:(row['question_sha256'],row['group']) for key,row in targets.items()}
        if candidate_ids is None:
            candidate_ids = {key:row['question_sha256'] for key,row in candidates.items()}
            target_identity = identity
        if candidate_ids != {key:row['question_sha256'] for key,row in candidates.items()} or target_identity != identity:
            raise ValueError('Feature identities changed between warmup checkpoints')
        groups = sorted({row['group'] for row in targets.values()})
        group_features = {}
        for group in groups:
            rows = [row for row in targets.values() if row['group'] == group]
            values = [row['unit'] if reduction == 'mean_per_target_cosine' else row['feature'] for row in rows]
            mean = [math.fsum(row[column] for row in values)/len(values) for column in range(dimension)]
            # Under code-aligned averaging, do NOT renormalize the mean unit
            # target feature; doing so silently changes relative group scores.
            group_features[group] = normalize(mean) if reduction == 'cosine_to_mean_gradient' else mean
        for key,row in candidates.items():
            scores = accumulated.setdefault(key,{group:0.0 for group in groups})
            for group,target in group_features.items():
                scores[group] += weight*dot(row['unit'],target)
    result = [dict(id=key,score=max(scores.values()),per_group=scores,
                   most_aligned_group=min(scores,key=lambda group:(-scores[group],group)))
              for key,scores in accumulated.items()]
    return sorted(result,key=lambda row:(-row['score'],row['id']))


def score_file(source, output, *, reduction='mean_per_target_cosine'):
    source,output = Path(source),Path(output)
    if source.name.casefold() in {'test.jsonl','test.json','official_test.jsonl','official_test.json'}:
        raise ValueError('Official test files cannot be opened by selection')
    raw = source.read_bytes()
    payload = json.loads(raw)
    scores = score_projected(payload,reduction=reduction)
    output.mkdir(parents=True,exist_ok=False)
    lines = ''.join(json.dumps(row,sort_keys=True)+'\n' for row in scores)
    (output/'scores.jsonl').write_text(lines,encoding='utf-8',newline='\n')
    summary = dict(method=METHOD,source_sha256=hashlib.sha256(raw).hexdigest(),
                   scores_sha256=hashlib.sha256(lines.encode()).hexdigest(),
                   candidates=len(scores),reduction=reduction,group_aggregation='max_after_checkpoint_sum',
                   projection=payload['projection'],official_test_used=False,
                   interpretation='Signed gradient-alignment proxy for first-order target-loss reduction; '
                                  'not causal Shapley value, not observed accuracy improvement.',
                   paid_work_launched=False)
    (output/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--reduction',choices=sorted(REDUCTIONS),default='mean_per_target_cosine')
    args = parser.parse_args()
    print(json.dumps(score_file(args.input,args.output,reduction=args.reduction)))


if __name__ == '__main__':
    main()
