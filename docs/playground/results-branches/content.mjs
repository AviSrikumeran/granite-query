import {FEEDS,deriveStudy,deriveNative,unavailableStudy,percent,number,signed,statusLabel} from './data.mjs?v=results-20261103-1';
const text=(id,value)=>{document.getElementById(id).textContent=value??'—';};
const element=(tag,value)=>{const el=document.createElement(tag);if(value!=null)el.textContent=value;return el;};
const dateLabel=timestamp=>new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'UTC'}).format(new Date(timestamp))+' UTC';
export function fillLinks(container,links=[]){
  container.replaceChildren(...links.map(link=>{const a=element('a',link.label+' ↗');a.href=link.href;a.target='_blank';a.rel='noopener';return a;}));
}
function renderStudy(model){
  document.body.dataset.feedStatus=model.status;
  const ready=model.status==='ready',pending=model.status==='pending';
  text('data-state',ready?(model.age.stale?'Published snapshot · stale':'Published snapshot · completed study'):pending?'Published snapshot · comparison pending':'Published evidence unavailable');
  text('data-updated',model.age?'Generated '+dateLabel(model.age.timestamp)+(model.age.stale?' · More than 24 hours old; refresh before treating it as current.':' · Refresh reads the latest published feed.'):'No current result is inferred. Use Refresh results to retry.');
  text('query-summary',ready?model.verdict+' in this comparison.':model.verdict);
  text('query-scope',model.scope??model.explanation);
  text('budget-note',model.budget??'Measured exposure is unavailable.');
  text('evaluation-label',model.scope??'Evaluation evidence is unavailable.');
  const tbody=document.getElementById('result-rows');tbody.replaceChildren();
  for(const [role,label] of [['baseline','Untouched'],['random','Random'],['skill','Skill']]){
    const job=model.jobs[role],complete=job?.status==='completed',row=element('tr'),name=element('th',label);name.scope='row';
    name.append(element('small',statusLabel(job?.status??'unavailable')));row.append(name,element('td',complete?job.correct+'/'+job.count:'—'),element('td',complete?percent(job.accuracy):'—'),element('td',complete?number(job.truncated):'—'));tbody.append(row);
  }
  const c=model.comparison;
  text('paired-result',c?signed(c.delta)+' pp · skill minus random':'Paired comparison '+(pending?'pending':'unavailable'));
  text('paired-uncertainty',c?'Paired 95% question-bootstrap interval: '+signed(c.interval[0])+' to '+signed(c.interval[1])+' pp. '+(c.includesZero?'Spans no difference. ':'')+'Single seed; exploratory, uncorrected comparisons.':'A missing or unverified interval is not shown as zero.');
  ['matched','scope','comparison','uncertainty','settings'].forEach((id,i)=>text('e'+(i+1)+'-summary',model.nodes[id].title.replace(/^E\d · /,'')));
  text('finding-title',model.verdict);text('finding-summary',model.explanation);
  fillLinks(document.getElementById('finding-links'),Object.values(model.links));
  const provenance=document.getElementById('provenance');provenance.replaceChildren();
  if(!model.protocol){provenance.append(element('p','No verified fingerprints are available.'));return;}
  const list=element('dl');
  const fields=[['Study',model.studyId],['Model',model.protocol.model],['Model revision',model.protocol.revision],['Study manifest SHA-256',model.manifest],['Development source SHA-256',model.cohortHash],['Fetched feed SHA-256',model.digest??'Unavailable']];
  for(const [role,job] of Object.entries(model.jobs))if(job.status==='completed')fields.push([role+' result SHA-256',job.resultHash],[role+' protocol SHA-256',job.protocolHash]);
  for(const [key,value] of fields)list.append(element('dt',key),element('dd',value));
  provenance.append(list,element('p','Fingerprints identify retained receipts. Private questions, responses and raw worker artifacts are not exposed here.'));
}
function renderNative(model){
  text('native-status',model.detail);
  text('native-updated','Generated '+dateLabel(model.age.timestamp)+(model.age.stale?' · Stale snapshot':' · Published snapshot'));
  const list=document.getElementById('native-jobs');list.replaceChildren();
  for(const job of model.jobs){const item=element('li');item.append(element('strong',job.label),element('span',statusLabel(job.status)+' · '+job.score));list.append(item);}
}
async function readFeed(url,withDigest=false){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
  try{
    const response=await fetch(url,{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error('The published feed returned HTTP '+response.status+'.');
    const raw=await response.text(),data=JSON.parse(raw);
    let digest=null;
    if(withDigest&&globalThis.crypto?.subtle){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw));digest=[...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('');}
    return {data,digest};
  }finally{clearTimeout(timer);}
}
export function startEvidence(onChange){
  const refresh=document.getElementById('refresh');let running=false,lastGood=null;
  async function load(){
    if(running)return;running=true;refresh.disabled=true;refresh.textContent='Refreshing…';
    const outcomes=await Promise.allSettled([readFeed(FEEDS.study,true),readFeed(FEEDS.native)]);
    try{
      if(outcomes[0].status==='rejected')throw Error('The public result feed could not be loaded.');
      const {data,digest}=outcomes[0].value,model=deriveStudy(data,{digest});lastGood=model;renderStudy(model);onChange(model);
    }catch(error){
      if(lastGood){renderStudy(lastGood);text('data-state','Refresh failed · showing previous snapshot');text('data-updated','Generated '+dateLabel(lastGood.age.timestamp)+' · '+error.message);document.body.dataset.feedStatus='cached';}
      else{const model=unavailableStudy(error.message,outcomes[0].status==='fulfilled'?'needs-review':'unavailable');renderStudy(model);onChange(model);}
    }
    try{if(outcomes[1].status==='rejected')throw Error('The independent native-study feed is unavailable.');renderNative(deriveNative(outcomes[1].value.data));}
    catch(error){text('native-status',error.message);text('native-updated','No current status or score is inferred.');document.getElementById('native-jobs').replaceChildren();}
    running=false;refresh.disabled=false;refresh.textContent='Refresh results';
  }
  refresh.addEventListener('click',load);load();
}
