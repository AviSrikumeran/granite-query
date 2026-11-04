/* Pure public-feed adapter. No network or DOM work. Payloads may use FEEDS keys
   or filenames. Unsupported protocols/cohorts throw; absent optional metrics
   remain null. Accuracy is always derived from validated numeric counts. */
export const FEEDS=Object.freeze({capacity:'overnight-capacity-results.json',feedback:'overnight-feedback-results.json',human:'human-study-results.json',teacher:'development-teacher200.json',valuation:'valuation-results.json',research:'research.json'});

const MODEL='ibm-granite/granite-4.2-3b';
const REVISION='4e9c275e232f10211ec88644d106a1f6a1b60e06';
const HUMAN_COHORT='cccdce864d728e6b43d9d4de866e719bfd9c706cc735a3a3d429095835c767c7';
const TOKEN_IDS='b00a7d78fa3514b3279c8c228c831d52199a9319eef3f3dc79cfefe265b733ec';
const TOKEN_BASE_SOURCE='a190292a79ebc7a4ce23fb54d698871adc76c7680af4ecb2c2de602d2bafb1af';
const OVERNIGHT_PLANS={feedback:'238a889108de842c3ba5399b1e739fa90b1999edee0915074ad2f9810194628d',capacity:'c86af5a17840abbb7087e207df1444deffd4aa14a3868c64d2f6e755c2eab950'};
const own=(object,key)=>Object.prototype.hasOwnProperty.call(object,key);
const fail=message=>{throw new TypeError(`Study unavailable: ${message}`);};
function object(value,name){if(!value||typeof value!=='object'||Array.isArray(value))fail(`${name} must be an object`);return value;}
function equal(value,expected,name){if(value!==expected)fail(`${name} does not match the supported study`);return value;}
function integer(value,min,max,name){if(!Number.isInteger(value)||value<min||value>max)fail(`${name} is invalid`);return value;}
function finite(value,min,max,name){if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)fail(`${name} is invalid`);return value;}
function optionalInteger(value,name){return value==null?null:integer(value,0,Number.MAX_SAFE_INTEGER,name);}
function text(value,name){if(typeof value!=='string'||!value.trim()||value.length>6000)fail(`${name} is invalid`);return value;}
function hash(value,name,{optional=false}={}){if(value==null&&optional)return null;if(typeof value!=='string'||!/^[a-f0-9]{64}$/.test(value))fail(`${name} is invalid`);return value;}
function date(value,name){if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T/.test(value)||!Number.isFinite(Date.parse(value)))fail(`${name} is invalid`);return value;}
function rejectNonfinite(value,path){
  if(typeof value==='number'&&!Number.isFinite(value))fail(`${path} is nonfinite`);
  if(Array.isArray(value))value.forEach((item,index)=>rejectNonfinite(item,`${path}[${index}]`));
  else if(value&&typeof value==='object')for(const [key,item] of Object.entries(value))rejectNonfinite(item,`${path}.${key}`);
}
function feed(payloads,key,{schema=true}={}){
  object(payloads,'payloads');const value=own(payloads,key)?payloads[key]:payloads[FEEDS[key]];
  object(value,FEEDS[key]);rejectNonfinite(value,FEEDS[key]);
  if(schema)equal(value.schema_version,1,`${key} schema`);
  return value;
}
function completed(value,name){equal(value,'completed',`${name} status`);}
function noTest(value,name){equal(value,false,`${name} official-test boundary`);}
function metrics(value,count,name){
  object(value,name);equal(value.count,count,`${name} count`);
  const correct=integer(value.numeric_correct,0,count,`${name} correct`);
  const truncated=value.truncated==null?null:integer(value.truncated,0,count,`${name} truncated`);
  if(truncated!==null&&correct+truncated>count)fail(`${name} counts overlap`);
  if(value.strict_format_correct!=null)integer(value.strict_format_correct,0,correct,`${name} strict-format count`);
  if(value.scoring_policy!=null)text(value.scoring_policy,`${name} scoring policy`);
  return {correct,total:count,accuracy:correct/count*100,truncated,scoring:value.scoring_policy??null};
}
function reportedAccuracy(value,metric,name){if(value!=null&&Math.abs(finite(value,0,100,name)-metric.accuracy)>1e-7)fail(`${name} disagrees with counts`);}
function paired(value,before,after,count,label,{overnight=false}={}){
  object(value,`${label} comparison`);
  equal(overnight?value.question_count:value.count,count,`${label} comparison count`);
  if(overnight){equal(value.before_correct,before,`${label} before`);equal(value.after_correct,after,`${label} after`);}
  const delta=finite(overnight?value.delta_percentage_points:value.difference_percentage_points,-100,100,`${label} delta`);
  if(Math.abs(delta-(after-before)/count*100)>1e-7)fail(`${label} delta disagrees with outcomes`);
  const corrected=integer(value.corrected,0,count-before,`${label} corrected`),regressed=integer(value.regressed,0,before,`${label} regressed`);
  if(corrected+regressed>count||before+corrected-regressed!==after)fail(`${label} paired changes disagree`);
  const interval=overnight?value.paired_question_bootstrap95_pp:value.paired_bootstrap_95_interval_pp;
  if(!Array.isArray(interval)||interval.length!==2)fail(`${label} interval is missing`);
  interval.forEach((number,index)=>finite(number,-100,100,`${label} interval ${index}`));
  if(interval[0]>interval[1]||delta<interval[0]-1e-7||delta>interval[1]+1e-7)fail(`${label} interval is inconsistent`);
  if(value.mcnemar_exact_two_sided_p!=null)finite(value.mcnemar_exact_two_sided_p,0,1,`${label} p-value`);
  return {label,delta,interval:[...interval],corrected,regressed};
}
function descriptiveComparison(before,after,count){return {label:'vs original Granite (descriptive)',delta:(after-before)/count*100,interval:null,corrected:null,regressed:null};}
function row({id,label,role,metric,updates=null,tokens=null,seed=null,sourcePath,comparison=null,receipt=null,extra=[],note=''}){
  updates=optionalInteger(updates,`${id} updates`);tokens=optionalInteger(tokens,`${id} training tokens`);seed=optionalInteger(seed,`${id} seed`);
  receipt=hash(receipt,`${id} receipt`,{optional:true});
  const evidence=[{label:'Numeric matches',value:`${metric.correct} / ${metric.total}`},{label:'Optimizer updates',value:updates===null?'Not published':String(updates)},{label:'Training seed',value:seed===null?'Not published':String(seed)}];
  if(tokens!==null)evidence.push({label:'Reported training loss tokens',value:String(tokens)});
  if(metric.scoring)evidence.push({label:'Scoring',value:metric.scoring});
  if(receipt)evidence.push({label:'Artifact / result SHA-256',value:receipt});
  evidence.push(...extra);
  return {id,label,role,correct:metric.correct,total:metric.total,accuracy:metric.accuracy,truncated:metric.truncated,updates,trainingTokens:tokens,seed,sourcePath,comparison,evidence,note};
}
function sameMetric(a,b,name){for(const key of ['correct','total','truncated'])if(a[key]!==b[key])fail(`${name} reused baseline differs`);}

function overnight(payloads){
  const capacity=feed(payloads,'capacity'),feedback=feed(payloads,'feedback');
  for(const [name,data] of [['capacity',capacity],['feedback',feedback]]){
    completed(data.stage,name);noTest(data.official_test_used,name);equal(hash(data.plan_sha256,`${name} plan`),OVERNIGHT_PLANS[name],`${name} frozen plan identity`);
    for(const role of ['error','random'])equal(data.role_states?.[role],'validated_completed',`${name} ${role} validation`);
  }
  equal(feedback.role_states?.baseline,'validated_completed','feedback baseline validation');
  const updatedAt=[date(capacity.updated_at_utc,'capacity timestamp'),date(feedback.updated_at_utc,'feedback timestamp')].sort((a,b)=>Date.parse(b)-Date.parse(a))[0];
  const definitions=[['base','Original Granite','baseline',capacity,'baseline',FEEDS.capacity],['small-error','Small correction adapter','trained',feedback,'error',FEEDS.feedback],['small-random','Small random control','trained',feedback,'random',FEEDS.feedback],['large-error','Larger correction adapter','trained',capacity,'error',FEEDS.capacity],['large-random','Larger random control','trained',capacity,'random',FEEDS.capacity]];
  const splits=['development','retention'].map(split=>{
    const count=32,base=metrics(capacity.metrics?.baseline?.[split],count,`capacity baseline ${split}`);
    sameMetric(base,metrics(feedback.metrics?.baseline?.[split],count,`feedback baseline ${split}`),split);
    const rows=definitions.map(([id,label,role,data,key,sourcePath])=>{
      const source=object(data.metrics?.[key],`${id} metrics`),metric=metrics(source[split],count,`${id} ${split}`);
      const updates=optionalInteger(source.updates,`${id} updates`);
      if(updates!==null)equal(updates,role==='baseline'?0:sourcePath===FEEDS.feedback?8:64,`${id} training dose`);
      const tokens=sourcePath===FEEDS.feedback?source.planned_actual_loss_tokens:source.full_target_loss_tokens_from_validated_updates;
      const comparison=role==='baseline'?null:paired(data.comparisons?.[`${key}_vs_base`]?.[split],base.correct,metric.correct,count,'vs original Granite',{overnight:true});
      return row({id,label,role,metric,updates,tokens,seed:source.seed,sourcePath,comparison,receipt:source.adapter_weight_sha256??source.adapter_sha256,note:role==='baseline'?'Hash-bound historical baseline reused by both doses; not a fresh rerun.':'Complete targets produce unequal loss-token exposure between correction and random arms.'});
    });
    // Validate the separately published correction-vs-random comparison too.
    for(const [name,data] of [['capacity',capacity],['feedback',feedback]])paired(data.comparisons?.error_vs_random?.[split],data.metrics.random[split].numeric_correct,data.metrics.error[split].numeric_correct,count,`${name} correction vs random`,{overnight:true});
    return {id:split,label:split==='development'?'Development · 32 questions':'Same-task retention · 32 questions',count,rows};
  });
  const improved=splits[0].rows.slice(1).some(item=>item.correct>splits[0].rows[0].correct);
  return {id:'overnight',title:'Fitting without demonstrated transfer',label:'Latest · local correction study',question:'Did teacher corrections improve answers on separate questions?',summary:improved?'Development changes must be read with retention and paired uncertainty. No robust transfer is established by this adaptive pilot.':'No trained arm improved development accuracy. Every trained arm lost same-task retention relative to the original model.',limitation:'Small adaptive TRAIN-development samples, one seed and same-task retention. Only eight distinct mistakes plus eight replay examples per arm. Capacity, dose and learning rate changed together; this is correction-target SFT, not token-distribution matching. Official test remains sealed.',updatedAt,sourcePath:FEEDS.capacity,splits};
}

function matched200(payloads){
  const human=feed(payloads,'human'),teacher=feed(payloads,'teacher');
  completed(human.status,'human');equal(teacher.stage,'completed_validated','teacher stage');
  noTest(human.official_test_used,'human');noTest(teacher.official_test_used,'teacher');equal(teacher.training_eligible,false,'teacher development exclusion');
  equal(human.study_id,'human-reference64k-dev200-v2','human study identity');equal(human.completed_jobs,3,'completed student jobs');
  equal(human.cohort?.development_count,200,'human cohort count');equal(human.cohort?.split,'train','human split');equal(human.cohort?.role,'development','human cohort role');
  equal(human.cohort?.development_source_sha256,HUMAN_COHORT,'human cohort identity');equal(teacher.source_sha256,HUMAN_COHORT,'teacher cohort identity');
  equal(teacher.source_split,'train','teacher split');equal(teacher.role,'development_teacher_measurement','teacher role');equal(teacher.count,200,'teacher count');
  equal(human.protocol?.model,MODEL,'student model');equal(human.protocol?.revision,REVISION,'student revision');equal(human.protocol?.seed,42,'student seed');
  equal(human.protocol?.enable_thinking,false,'human thinking');equal(human.protocol?.max_new_tokens,512,'human output cap');equal(human.protocol?.do_sample,false,'human decoding');
  equal(teacher.settings?.thinking,false,'teacher thinking');equal(teacher.settings?.max_output_tokens,512,'teacher output cap');equal(teacher.settings?.same_user_prompt,true,'teacher prompt');equal(teacher.settings?.temperature,0,'teacher temperature');
  const student={};
  for(const key of ['baseline','random','skill']){
    const job=object(human.jobs?.[key],`${key} job`);completed(job.status,key);
    student[key]=metrics(job.metrics,200,`${key} metrics`);reportedAccuracy(job.accuracy_percent,student[key],`${key} accuracy`);
    const echo=metrics(teacher.granite?.[key]?.metrics,200,`teacher echoed ${key}`);sameMetric(student[key],echo,key);
    for(const field of ['protocol_hash','result_sha256']){
      const a=hash(job[field],`${key} ${field}`,{optional:true}),b=hash(teacher.granite?.[key]?.[field],`teacher ${key} ${field}`,{optional:true});
      if(a&&b)equal(a,b,`${key} echoed receipt`);
    }
  }
  const teacherMetric=metrics(teacher.teacher?.metrics,200,'teacher metrics');equal(teacher.teacher_correct,teacherMetric.correct,'teacher headline count');
  const humanComparisons={};
  for(const [name,before,after] of [['skill_vs_random','random','skill'],['random_vs_baseline','baseline','random'],['skill_vs_baseline','baseline','skill']]){
    equal(human.comparisons?.[name]?.status,'completed',`${name} status`);
    humanComparisons[name]=paired(human.comparisons[name].statistics,student[before].correct,student[after].correct,200,after==='skill'&&before==='random'?'vs random-trained Granite':'vs original Granite');
  }
  const teacherComparisons={};for(const key of ['baseline','random','skill'])teacherComparisons[key]=paired(teacher.same_question_statistics?.[`deepseek_minus_${key}`],student[key].correct,teacherMetric.correct,200,key==='baseline'?'vs original Granite (teacher gap)':`teacher vs ${key}`);
  const teacherRow=row({id:'teacher',label:'DeepSeek teacher',role:'teacher',metric:teacherMetric,sourcePath:FEEDS.teacher,comparison:teacherComparisons.baseline,note:'Mutable DeepSeek API alias; numeric matches include a final-line fallback. Teacher headroom is not a trained-student gain.',extra:[{label:'Strict-format matches',value:String(teacher.teacher.metrics.strict_format_correct??'Not published')}]});
  const rows=[teacherRow,...['baseline','random','skill'].map(key=>{
    const source=human.jobs[key],updates=optionalInteger(source.actual_optimizer_updates,`${key} updates`),tokens=optionalInteger(source.actual_supervised_tokens,`${key} tokens`);
    if(updates!==null)equal(updates,key==='baseline'?0:64,`${key} updates`);if(tokens!==null)equal(tokens,key==='baseline'?0:65536,`${key} tokens`);
    if(source.seed!=null)equal(source.seed,42,`${key} seed`);
    return row({id:key==='baseline'?'base':key,label:key==='baseline'?'Original Granite':key==='random'?'Random-data trained Granite':'Skill-ranked Granite',role:key==='baseline'?'baseline':'trained',metric:student[key],updates,tokens,seed:source.seed??human.protocol.seed,sourcePath:FEEDS.human,receipt:source.result_sha256,comparison:key==='baseline'?null:humanComparisons[key==='skill'?'skill_vs_random':'random_vs_baseline'],note:key==='baseline'?'Pinned original checkpoint; nonthinking greedy 512-token inference.':'Same supervised tokens and updates, but unequal examples, forwarded tokens and runtime.'});
  })];
  const updatedAt=[date(teacher.validated_at_utc,'teacher timestamp'),date(human.generated_at_utc,'human timestamp')].sort((a,b)=>Date.parse(b)-Date.parse(a))[0];
  return {id:'matched-200',title:'Teacher headroom, no student improvement',label:'Matched · 200-question diagnostic',question:'Did ranked teaching beat random teaching on the same 200 questions?',summary:'The teacher’s advantage measures headroom. The tested student adapters scored below the original checkpoint; skill selection did not beat random in this run.',limitation:'Same GSM8K TRAIN-development questions, prompt and nominal nonthinking 512-token cap; not equal FLOPs or latency. One training seed, adaptive study, exploratory question-bootstrap intervals and no multiplicity correction. Numeric matches do not verify reasoning steps. Official test remains sealed.',updatedAt,sourcePath:FEEDS.teacher,splits:[{id:'development',label:'Matched development · 200 questions',count:200,rows}]};
}

function token64(payloads){
  const valuation=feed(payloads,'valuation'),research=feed(payloads,'research',{schema:false}),protocol=object(valuation.protocol,'valuation protocol');
  completed(valuation.status,'valuation');noTest(valuation.official_test_used,'valuation');equal(valuation.completed_pairs,2,'valuation pairs');equal(valuation.completed_arms,4,'valuation arms');
  equal(protocol.model,MODEL,'valuation model');equal(protocol.revision,REVISION,'valuation revision');equal(protocol.development_count,64,'valuation count');equal(protocol.evaluation_kind,'development','valuation role');equal(protocol.development_ids_sha256,TOKEN_IDS,'valuation cohort');
  equal(protocol.token_budget,32768,'valuation token budget');equal(protocol.optimizer_updates,32,'valuation updates');equal(protocol.enable_thinking,false,'valuation thinking');equal(protocol.max_new_tokens,512,'valuation cap');equal(protocol.evaluation_batch_size,8,'valuation batch');equal(protocol.do_sample,false,'valuation decoding');
  const reference=object(research.token_matched32768,'matched64 reference');equal(reference.count,64,'reference count');equal(reference.selection_adaptive_to_development,true,'reference adaptive boundary');
  const baseline=object(reference.batched_baseline,'matched batch baseline');completed(baseline.status,'batch baseline');equal(baseline.training_performed,false,'batch baseline training');equal(baseline.development_source_sha256,TOKEN_BASE_SOURCE,'batch baseline cohort');
  for(const [key,value] of Object.entries({model:MODEL,revision:REVISION,evaluation_batch_size:8,max_new_tokens:512,enable_thinking:false,do_sample:false,evaluation_kind:'development',checkpoint_name:'baseline',training_performed:false}))equal(baseline.protocol?.[key],value,`baseline ${key}`);
  const base=metrics(baseline.metrics,64,'batch baseline metrics');reportedAccuracy(baseline.accuracy_percent,base,'batch baseline accuracy');
  const rows=[row({id:'base',label:'Original Granite · batch 8 control',role:'baseline',metric:base,updates:baseline.actual_optimizer_updates,tokens:baseline.actual_supervised_tokens,seed:baseline.seed,sourcePath:FEEDS.research,note:'Matched batch-8 control. Earlier serial 58/64 is separate history; no training performed.'})];
  let anySkillWin=false;
  for(const seed of [42,43]){
    const pair=object(valuation.pairs?.[String(seed)],`seed ${seed}`);equal(pair.seed,seed,`pair ${seed} identity`);completed(pair.status,`pair ${seed}`);
    const armMetrics={};
    for(const arm of ['random','valued']){
      const source=object(pair.arms?.[arm],`${seed} ${arm}`);completed(source.status,`${seed} ${arm}`);equal(source.seed,seed,`${arm} seed`);equal(source.arm,arm,`${seed} arm identity`);equal(source.sources?.development_ids_sha256,TOKEN_IDS,`${seed} ${arm} cohort`);
      armMetrics[arm]=metrics(source.metrics,64,`${seed} ${arm} metrics`);
      equal(reference.correct?.[`${arm} seed${seed}`],armMetrics[arm].correct,`${seed} reference count`);
      const tokens=optionalInteger(source.exposure?.supervised_tokens,`${seed} ${arm} tokens`),updates=optionalInteger(source.exposure?.optimizer_updates,`${seed} ${arm} updates`);
      if(tokens!==null)equal(tokens,32768,`${seed} ${arm} tokens`);if(updates!==null)equal(updates,32,`${seed} ${arm} updates`);
      rows.push(row({id:`${arm==='valued'?'skill':'random'}-${seed}`,label:`${arm==='valued'?'Skill-selected':'Random-selected'} · seed ${seed}`,role:'trained',metric:armMetrics[arm],updates,tokens,seed,sourcePath:FEEDS.valuation,receipt:source.sources?.result_sha256,comparison:descriptiveComparison(base.correct,armMetrics[arm].correct,64),note:'Base difference is descriptive: no paired baseline interval is published. Skill-v-random uncertainty is reported separately.'}));
    }
    const comparison=paired(pair.paired_valued_vs_random,armMetrics.random.correct,armMetrics.valued.correct,64,`skill vs random · seed ${seed}`);
    const skillRow=rows.find(item=>item.id===`skill-${seed}`);
    skillRow.evidence.push({label:'Paired skill − random',value:`${comparison.delta} pp; 95% question-bootstrap [${comparison.interval.join(', ')}] pp; corrected ${comparison.corrected}, regressed ${comparison.regressed}`});
    anySkillWin ||= comparison.delta>0;
  }
  return {id:'token-64',title:'Equal training tokens, two selection seeds',label:'Earlier · token-matched 64-question study',question:'Did skill selection beat random at the same training-token budget?',summary:anySkillWin?'Read each seed’s paired result separately. Two adaptive monitoring runs do not establish a robust selection benefit.':'Skill selection did not beat random in either seed. The two runs reused the same 64 development questions.',limitation:'Adaptive TRAIN-development monitoring, not 128 independent test questions. Equal supervised tokens and updates do not match examples or compute. Baseline deltas are descriptive; only skill-v-random paired intervals are published here. Numeric scoring is not reasoning verification.',updatedAt:date(valuation.generated_at_utc,'valuation timestamp'),sourcePath:FEEDS.valuation,splits:[{id:'development',label:'Adaptive monitoring · same 64 questions',count:64,rows}]};
}

export function buildStudy(id,payloads){
  if(id==='overnight')return overnight(payloads);
  if(id==='matched-200')return matched200(payloads);
  if(id==='token-64')return token64(payloads);
  fail('unsupported study identity');
}
