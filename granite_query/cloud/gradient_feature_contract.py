"""Dependency-free protocol, masks and deterministic CountSketch reference."""
import hashlib
import json
import math
import random

MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
METHOD = 'less-inspired-countsketch-v1'
PROJECTION_FAMILY = 'countsketch_shake256_v1'


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixed_config(seed=20261103, dimension=1024):
    if dimension not in (512,1024,2048):
        raise ValueError('Reviewed CountSketch dimensions are512,1024,2048')
    return dict(method=METHOD,model=MODEL,revision=REVISION,seed=seed,
        lora_r=8,lora_alpha=16,lora_dropout=0.0,lora_target_modules=['q_proj','v_proj'],
        learning_rate=2e-5,lr_warmup_updates=2,weight_decay=0.0,optimizer='AdamW',
        beta1=0.9,beta2=0.999,eps=1e-8,max_grad_norm=1.0,
        warmup_examples=24,warmup_tokens=8192,tokens_per_update=1024,checkpoint_updates=[4,8],
        projection_family=PROJECTION_FAMILY,projection_dimension=dimension,projection_seed=seed,
        projection_device='cpu',projection_accumulation_dtype='float32',
        context_limit=2048,max_response_tokens=768,max_candidates=1800,max_targets=32,
        calibration_examples=16,calibration_margin=1.25,calibration_io_allowance_seconds=90,
        calibration_finish_limit_seconds=1550,collection_guard_seconds=1550,
        application_guard_seconds=1650,timeout_seconds=1800,startup_timeout_seconds=120,
        gpu='A100-80GB',cpu_cores=4,memory_mib=32768,commit_interval=16,
        enable_thinking=False,official_test_used=False,target_role='selection_development',
        candidate_gradient_type='less_adam',target_gradient_type='sgd',
        reduction='mean_per_target_cosine',group_aggregation='max_after_checkpoint_sum')


def validate_row(row, config, target=False):
    if not isinstance(row.get('id'),str) or not row['id'] or row.get('source_split') != 'train':
        raise ValueError('Require stable IDs and explicit source_split=train')
    if row.get('verified_final_answer') is not True:
        raise ValueError('Unverified/incomplete traces cannot enter gradient collection')
    prefix, answer = row.get('prefix_ids'),row.get('answer_ids')
    if not isinstance(prefix,list) or not isinstance(answer,list) or not prefix or not answer:
        raise ValueError('Require separately encoded complete prompt/response tokens')
    if any(type(value) is not int or value < 0 for value in prefix+answer):
        raise ValueError('Token IDs must be nonnegative integers')
    if len(prefix)+len(answer)>config['context_limit'] or len(answer)>config['max_response_tokens']:
        raise ValueError('Never truncate input/response to fit gradient collection')
    for field in ('question_sha256','raw_response_sha256'):
        value=row.get(field)
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Require frozen normalized-question and raw-response hashes')
    if target and (not row.get('group') or row.get('reference_match_is_independent_gold') is not True):
        raise ValueError('Targets require a frozen group and independent human-reference provenance')


def labels_for(row,start=0,end=None):
    answer=row['answer_ids']
    end=len(answer) if end is None else end
    if not 0 <= start < end <= len(answer):
        raise ValueError('Invalid answer supervision span')
    return [-100]*len(row['prefix_ids'])+[-100]*start+answer[start:end]+[-100]*(len(answer)-end)


def build_warmup(rows,config):
    """Repeat only the frozen random warmup subset, with exact token updates."""
    ids=sorted(row['id'] for row in rows)
    if len(ids)!=len(set(ids)) or len(ids)!=config['warmup_examples']:
        raise ValueError('Warmup requires the frozen24 distinct random candidates')
    random.Random(config['seed']+17).shuffle(ids)
    by_id={row['id']:row for row in rows}
    remaining=config['warmup_tokens']; per=config['tokens_per_update']
    updates=[]; current=dict(index=0,supervised_tokens=0,microbatches=[])
    cursor=0
    while remaining:
        key=ids[cursor%len(ids)]
        answer=by_id[key]['answer_ids']; start=0
        while start<len(answer) and remaining:
            count=min(len(answer)-start,remaining,per-current['supervised_tokens'])
            current['microbatches'].append(dict(id=key,answer_start=start,answer_end=start+count,
                supervised_tokens=count,loss_weight=count/per,exposure_pass=cursor//len(ids)))
            current['supervised_tokens']+=count; remaining-=count; start+=count
            if current['supervised_tokens']==per:
                updates.append(current)
                current=dict(index=len(updates),supervised_tokens=0,microbatches=[])
        cursor+=1
    if current['supervised_tokens']:
        raise ValueError('Warmup budget must divide into complete effective batches')
    return dict(ids=ids,updates=updates,supervised_tokens=config['warmup_tokens'],
                repetition_policy='Cycle the same fixed shuffled24-example subset until8192 tokens; record partial final exposure')


def calibration_ids(rows,count):
    ordered=sorted(rows,key=lambda row:(len(row['prefix_ids'])+len(row['answer_ids']),row['id']))
    if len(ordered)<count or count<2:
        raise ValueError('Insufficient length-stratified calibration candidates')
    return [ordered[round(index*(len(ordered)-1)/(count-1))]['id'] for index in range(count)]


def mapping_bytes(parameters,seed):
    if type(parameters) is not int or not 1<=parameters<=10000000:
        raise ValueError('Unexpected trainable parameter count')
    return hashlib.shake_256(f'gq-countsketch-v1:{seed}'.encode()).digest(parameters*5)


def countsketch_mapping(parameters,dimension,seed):
    """Fixture mapping; production worker vectorizes this identical byte stream."""
    raw=mapping_bytes(parameters,seed)
    buckets=[int.from_bytes(raw[5*i:5*i+4],'little')%dimension for i in range(parameters)]
    signs=[1 if raw[5*i+4]&1 else -1 for i in range(parameters)]
    return buckets,signs,sha(raw)


def countsketch_reference(values,dimension,seed=42):
    if len(values)>100000:
        raise ValueError('Use the vectorized worker for large gradients')
    if type(dimension) is not int or dimension<1:
        raise ValueError('Invalid projection dimension')
    buckets,signs,_=countsketch_mapping(len(values),dimension,seed)
    result=[0.0]*dimension
    for value,bucket,sign in zip(values,buckets,signs):
        if not math.isfinite(value):
            raise ValueError('Nonfinite gradients cannot be projected')
        result[bucket]+=value*sign
    return result


def validate_input(data,plan):
    config=plan['protocol']['config']
    if config!=fixed_config(config['seed'],config['projection_dimension']):
        raise ValueError('Reviewed bounded feature configuration changed')
    if sha(canonical(plan['protocol']))!=plan['protocol_hash']:
        raise ValueError('Feature protocol hash mismatch')
    if sha(canonical(data))!=plan['protocol']['input_sha256']:
        raise ValueError('Feature input changed after preparation')
    candidates,targets=data['candidates'],data['targets']
    if not 24<=len(candidates)<=1800 or not 1<=len(targets)<=32:
        raise ValueError('Bounded candidate/target size violated')
    if any(len({row['id'] for row in rows})!=len(rows) for rows in (candidates,targets)):
        raise ValueError('Duplicate gradient record IDs')
    for row in candidates:
        validate_row(row,config)
    for row in targets:
        validate_row(row,config,target=True)
    candidate_ids={row['id'] for row in candidates}; target_ids={row['id'] for row in targets}
    if candidate_ids&target_ids or ({row['question_sha256'] for row in candidates}&{row['question_sha256'] for row in targets}):
        raise ValueError('Candidate and selection-development target overlap')
    if [row['id'] for row in candidates]!=plan['protocol']['candidate_ids'] or [row['id'] for row in targets]!=plan['protocol']['target_ids']:
        raise ValueError('Frozen feature identities/order changed')
    warmup_ids=set(data['warmup']['ids'])
    if not warmup_ids.issubset(candidate_ids) or data['warmup']!=build_warmup([r for r in candidates if r['id'] in warmup_ids],config):
        raise ValueError('Warmup labels/repetitions differ from frozen protocol')
    if data['calibration_ids']!=calibration_ids(candidates,config['calibration_examples']):
        raise ValueError('Calibration selection changed')
    return config


def validate_resume(previous,current):
    if previous['protocol_hash']!=current['protocol_hash'] or previous['protocol']!=current['protocol']:
        raise ValueError('Resume would change input identities, masks, tokenizer, or protocol')


def validate_feature(record,row,checkpoint_id,layout_hash,mapping_hash,dimension):
    unsigned={key:value for key,value in record.items() if key!='record_sha256'}
    if record.get('record_sha256')!=sha(canonical(unsigned)):
        raise ValueError('Saved feature content hash changed')
    expected=dict(id=row['id'],question_sha256=row['question_sha256'],raw_response_sha256=row['raw_response_sha256'],
                  checkpoint_id=checkpoint_id,parameter_layout_sha256=layout_hash,projection_mapping_sha256=mapping_hash)
    if any(record.get(key)!=value for key,value in expected.items()):
        raise ValueError('Saved feature identity/checkpoint/projection changed')
    values=record.get('feature',[])
    if len(values)!=dimension or any(not math.isfinite(value) for value in values):
        raise ValueError('Saved projected feature is invalid')
    if math.fsum(value*value for value in values)<=1e-30:
        raise ValueError('Zero projected feature cannot be ranked')
    return record
