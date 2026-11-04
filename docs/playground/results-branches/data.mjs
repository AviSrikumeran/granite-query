export const FEEDS={study:'../../human-study-results.json',native:'../../native-reasoning-study.json'};
export const REVIEWED={commit:'daf8d1cbe5bd6c93524ebc7a22a930f6c6ef7804',sha256:'ce670a229f555d8dfce6d7614cb736a44f430a99066bfc35c2078f4a0ddc70d5'};
const repo='https://github.com/AviSrikumeran/granite-query/blob/';
const hex=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const integer=value=>Number.isInteger(value)&&value>=0;
const finite=Number.isFinite;
const requireValue=(condition,message)=>{if(!condition)throw Error(message);};
export const percent=value=>Number.isFinite(value)?new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(value)+'%':'—';
export const number=value=>Number.isFinite(value)?new Intl.NumberFormat('en-US').format(value):'—';
export const signed=value=>Number.isFinite(value)?(value>0?'+':value<0?'−':'')+new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(Math.abs(value)):'—';
export const statusLabel=value=>({completed:'Completed',prepared:'Prepared',queued:'Queued',running:'Running',in_progress:'In progress',failed:'Failed',pending:'Pending',unverified:'Unverified',unavailable:'Unavailable'}[value]??'Pending review');
export function freshness(timestamp,now=Date.now()){
  const date=Date.parse(timestamp);
  requireValue(Number.isFinite(date),'The feed timestamp is missing or invalid.');
  return {timestamp,stale:now-date>86400000,future:date-now>300000};
}
function jobFrom(raw,count){
  if(!raw||raw.status!=='completed')return {status:raw?.status??'unavailable',correct:null,count:null,truncated:null,tokens:null,updates:null};
  if(raw.unique_call_observed!==true||!hex(raw.result_sha256)||!hex(raw.protocol_hash))return {status:'unverified',correct:null,count:null,truncated:null,tokens:null,updates:null};
  const m=raw.metrics;
  requireValue(m&&m.count===count&&integer(m.numeric_correct)&&integer(m.truncated)&&m.numeric_correct+m.truncated<=count,'A completed job has inconsistent evaluation counts.');
  requireValue(integer(raw.actual_supervised_tokens)&&integer(raw.actual_optimizer_updates),'A completed job lacks measured training exposure.');
  const accuracy=m.numeric_correct/count*100;
  requireValue(raw.accuracy_percent==null||(finite(raw.accuracy_percent)&&Math.abs(raw.accuracy_percent-accuracy)<.00001),'The published score disagrees with its counts.');
  return {status:'completed',correct:m.numeric_correct,count,truncated:m.truncated,accuracy,tokens:raw.actual_supervised_tokens,updates:raw.actual_optimizer_updates,resultHash:raw.result_sha256,protocolHash:raw.protocol_hash,scoring:m.scoring_policy};
}
export function deriveStudy(data,{digest=null,now=Date.now()}={}){
  requireValue(data?.schema_version===1&&data.study_id==='human-reference64k-dev200-v2','This feed schema or study is not supported by this comparison.');
  const cohort=data.cohort,protocol=data.protocol;
  requireValue(cohort&&integer(cohort.development_count)&&cohort.development_count>0&&cohort.split==='train'&&cohort.role==='development'&&cohort.legacy64_included===false&&cohort.legacy64_results_merged===false&&data.official_test_used===false,'The study scope differs from the reviewed training-split development cohort.');
  requireValue(hex(cohort.development_source_sha256)&&hex(data.study_manifest_sha256),'The cohort or study fingerprint is unavailable.');
  requireValue(protocol&&typeof protocol.model==='string'&&/^[a-f0-9]{40}$/.test(protocol.revision)&&integer(protocol.seed)&&integer(protocol.max_new_tokens)&&typeof protocol.enable_thinking==='boolean','The model or evaluation protocol is incomplete.');
  requireValue(protocol.model==='ibm-granite/granite-4.2-3b'&&protocol.enable_thinking===false&&protocol.max_new_tokens===512,'The reviewed Granite non-thinking/512 evaluation recipe has changed.');
  const age=freshness(data.generated_at_utc,now);
  requireValue(!age.future,'The feed timestamp is unexpectedly in the future.');
  const count=cohort.development_count,jobs=Object.fromEntries(['baseline','random','skill'].map(role=>[role,jobFrom(data.jobs?.[role],count)]));
  const complete=Object.values(jobs).every(j=>j.status==='completed');
  const matched=jobs.random.status==='completed'&&jobs.skill.status==='completed'&&jobs.random.tokens>0&&jobs.random.tokens===jobs.skill.tokens&&jobs.random.updates>0&&jobs.random.updates===jobs.skill.updates;
  const pair=data.comparisons?.skill_vs_random;
  let comparison=null;
  if(complete&&matched&&data.status==='completed'&&pair?.status==='completed'){
    const s=pair.statistics,expected=(jobs.skill.correct-jobs.random.correct)/count*100;
    requireValue(s&&s.count===count&&integer(s.corrected)&&integer(s.regressed)&&s.corrected<=Math.min(jobs.skill.correct,count-jobs.random.correct)&&s.regressed<=Math.min(jobs.random.correct,count-jobs.skill.correct),'The paired comparison has inconsistent outcome counts.');
    requireValue(finite(s.difference_percentage_points)&&Math.abs(s.difference_percentage_points-expected)<.00001&&Math.abs((s.corrected-s.regressed)/count*100-expected)<.00001,'The paired difference disagrees with the completed jobs.');
    const interval=s.paired_bootstrap_95_interval_pp;
    requireValue(Array.isArray(interval)&&interval.length===2&&interval.every(finite)&&interval[0]<=expected&&interval[1]>=expected&&interval[0]>=-100&&interval[1]<=100,'The paired uncertainty interval is missing or invalid.');
    comparison={delta:expected,interval,corrected:s.corrected,regressed:s.regressed,includesZero:interval[0]<=0&&interval[1]>=0};
  }
  const status=comparison?'ready':'pending';
  const verdict=!comparison?'Comparison pending':comparison.interval[0]>0?'Higher in this comparison':comparison.interval[1]<0?'Lower in this comparison':comparison.delta<=0?'No gain demonstrated':'No clear advantage';
  const explanation=!comparison?'Completed, verified matched jobs and a valid paired comparison are required before stating an advantage.':
    'Skill selection scored '+jobs.skill.correct+'/'+count+' versus random selection’s '+jobs.random.correct+'/'+count+'. The difference is '+signed(comparison.delta)+' percentage points; the paired 95% question-bootstrap interval is '+signed(comparison.interval[0])+' to '+signed(comparison.interval[1])+' pp. '+(comparison.includesZero?'It spans no difference.':'This is an exploratory single-seed development comparison.');
  const reportRef=digest===REVIEWED.sha256?REVIEWED.commit:'main';
  const links={
    feed:{label:'Published JSON',href:FEEDS.study},
    report:{label:digest===REVIEWED.sha256?'Reviewed report':'Latest report',href:repo+reportRef+'/progress/HUMAN_STUDY_RESULTS.md'},
    protocol:{label:digest===REVIEWED.sha256?'Reviewed design':'Study design',href:repo+reportRef+'/progress/HUMAN_STUDY_DESIGN.json'}
  };
  const scope=count+' GSM training-split development questions · seed '+protocol.seed+'. Official test not used.';
  const budget=matched?number(jobs.skill.tokens)+' supervised loss tokens and '+number(jobs.skill.updates)+' updates per adapter. Examples, forwarded input tokens and runtime are not matched.':'Matched measured training budgets are not yet verified.';
  const evidence=comparison?signed(comparison.delta)+' pp · skill versus random':'Paired result pending';
  const uncertainty=comparison?'Paired 95% question-bootstrap interval: '+signed(comparison.interval[0])+' to '+signed(comparison.interval[1])+' pp. '+comparison.corrected+' corrected; '+comparison.regressed+' regressed. Questions are resampled, not training seeds.':'Paired uncertainty is unavailable until the matched comparison is published.';
  const receipts=Object.values(jobs).filter(j=>j.status==='completed').length;
  const nodes={
    query:{title:'Did skill selection improve Granite?',text:'Trace the human-reference study through its protocol, measured results and verified receipts. '+scope,kind:'Research question',links:[links.report,links.feed]},
    retrieve:{title:'One study, three evidence routes',text:'Keep the protocol, paired results and receipt fingerprints attached to the same study. Earlier 64-question studies and the native OPEN/1024 study remain separate.',kind:'Study records',links:[links.report]},
    evaluation:{label:'Study protocol',title:'A matched development comparison',text:scope+' '+budget,kind:'Protocol',links:[links.protocol,links.feed],pointer:'/cohort · /protocol'},
    results:{title:'Observed results',text:complete?'Untouched Granite '+jobs.baseline.correct+'/'+count+'; random '+jobs.random.correct+'/'+count+'; skill '+jobs.skill.correct+'/'+count+'. '+evidence+'.':'Some job outcomes remain pending or unverified. No missing result is displayed as zero.',kind:'Results',links:[links.report,links.feed],pointer:'/jobs · /comparisons/skill_vs_random'},
    run:{label:'Verified receipts',title:receipts+' of 3 jobs have verified completed receipts',text:'The public feed exposes aggregate counts, unique-call observations, protocol hashes and result hashes. Private questions and responses are not exposed.',kind:'Run receipts',links:[links.feed],pointer:'/jobs/*/result_sha256'},
    matched:{label:'Same development cohort',title:'E1 · '+count+' development questions',text:scope+' Earlier 64-question results are not merged into this cohort.',kind:'Scope',source:'Study protocol',links:[links.protocol,links.feed],pointer:'/cohort/development_source_sha256'},
    scope:{label:'Measured training budgets',title:'E2 · '+(matched?number(jobs.skill.tokens)+' loss tokens':'Budget verification pending'),text:budget,kind:'Matched exposure',source:'Study protocol',links:[links.feed],pointer:'/jobs/skill/actual_supervised_tokens'},
    comparison:{label:'Skill versus random',title:'E3 · '+evidence,text:explanation,kind:'Paired result',source:'Observed results',links:[links.report,links.feed],pointer:'/comparisons/skill_vs_random/statistics'},
    uncertainty:{label:'Question uncertainty',title:'E4 · '+(comparison?(comparison.includesZero?'Interval spans no difference':'Exploratory interval'):'Uncertainty pending'),text:uncertainty+' No multiplicity correction is applied.',kind:'Uncertainty',source:'Observed results',links:[links.report,links.feed],pointer:'/comparisons/skill_vs_random/statistics/paired_bootstrap_95_interval_pp'},
    settings:{label:'Result fingerprints',title:'E5 · '+receipts+' verified completed receipts',text:'Model '+protocol.model+' at revision '+protocol.revision.slice(0,12)+'. Evaluation: thinking '+(protocol.enable_thinking?'on':'off')+', '+protocol.max_new_tokens+' output tokens. Full protocol and result hashes are listed below the walkthrough.',kind:'Provenance',source:'Verified receipts',links:[links.feed],pointer:'/protocol/revision · /jobs/*/protocol_hash'},
    answer:{label:verdict,title:verdict,text:explanation+' One adaptive development seed does not establish generalization, a causal ranking benefit or verified reasoning steps.',kind:status==='ready'?'Bounded finding':'Pending finding',links:[links.report,links.feed]}
  };
  return {status,age,digest,studyId:data.study_id,manifest:data.study_manifest_sha256,cohortHash:cohort.development_source_sha256,protocol,jobs,comparison,verdict,explanation,scope,budget,nodes,links,limitations:Array.isArray(data.limitations)?data.limitations:[],receipts};
}
export function unavailableStudy(message='Published evidence could not be loaded.',status='unavailable'){
  const nodes=Object.fromEntries(['query','retrieve','evaluation','results','run','matched','scope','comparison','uncertainty','settings','answer'].map(id=>[id,{title:id==='query'?'Did skill selection improve Granite?':'Evidence '+(status==='needs-review'?'needs review':'unavailable'),text:message+' No result is inferred. Retry the published feed or open it directly.',kind:'Evidence unavailable',label:'Evidence unavailable',links:[{label:'Published JSON',href:FEEDS.study}]}]));
  return {status,nodes,jobs:{},comparison:null,verdict:'Evidence unavailable',explanation:message,receipts:0,links:{feed:{label:'Published JSON',href:FEEDS.study}}};
}
export function deriveNative(data,{now=Date.now()}={}){
  requireValue(data?.schema_version===1&&data.version==='native-reasoning-public-receipts-v1'&&Array.isArray(data.jobs),'The native-study feed schema is unsupported.');
  requireValue(data.protocol?.native_generation_prefix==='OPEN'&&data.protocol?.enable_thinking===true&&data.protocol?.max_new_tokens===1024,'The native OPEN/1024 evaluation recipe has changed.');
  const age=freshness(data.updated_at_utc,now);requireValue(!age.future,'The native-study timestamp is unexpectedly in the future.');
  const jobs=data.jobs.map(job=>{
    const count=job.metrics?.count,correct=job.metrics?.numeric_correct;
    const verified=job.status==='completed'&&job.provider_terminal_receipt_verified===true&&integer(count)&&count>0&&count===job.planned_evaluation_count&&integer(correct)&&correct<=count;
    return {role:job.role,label:job.label,status:job.status,score:verified?correct+'/'+count:'Not available'};
  });
  return {age,stage:data.stage,detail:data.current_work?.detail??'No current work detail is published.',jobs,teacher:{retained:data.teacher?.retained_original_outcomes,planned:data.teacher?.planned_original_calls},note:'Separate native OPEN/1024 study. These outcomes are not combined with the non-thinking/512 human-reference comparison.',href:FEEDS.native};
}
