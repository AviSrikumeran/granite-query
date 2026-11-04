import {FEEDS,buildStudy} from './data.js?v=20261104-1';

const $=selector=>document.querySelector(selector);
const element=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
const number=value=>Number.isFinite(value)?new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(value):'Not reported';
const percent=value=>new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(value)+'%';
const signed=value=>(value<0?'−':value>0?'+':'')+number(Math.abs(value));
const date=value=>new Intl.DateTimeFormat('en-US',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value));
const reportLinks={overnight:'research/?report=overnight','matched-200':'research/?report=human-study','token-64':'research/?report=valuation'};
let studies={},payloads={},studyId='overnight',splitId='development',selectedId='large-error',view='chart',evidenceView='details',loadNumber=0;

const menu=$('.menu-toggle'),navigation=$('#main-nav');
function closeMenu(focus=false){menu?.setAttribute('aria-expanded','false');navigation?.classList.remove('is-open');if(focus)menu?.focus();}
menu?.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));navigation.classList.toggle('is-open',open);});
navigation?.addEventListener('click',event=>{if(event.target.closest('a'))closeMenu();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu?.getAttribute('aria-expanded')==='true')closeMenu(true);});
matchMedia('(min-width:651px)').addEventListener('change',event=>{if(event.matches)closeMenu();});

// Artwork failure must never prevent access to the research.
import('./hero.js?v=20261104-1').then(({initHero})=>initHero($('#hero-material'))).catch(()=>{$('#hero-material').setAttribute('aria-label','Static magenta material illustration. Interactive artwork unavailable.');});

function selected(){const study=studies[studyId],split=study?.splits.find(item=>item.id===splitId);return{study,split,row:split?.rows.find(item=>item.id===selectedId)};}
function chooseRow(id,{focus=false}={}){selectedId=id;renderResults({focusRow:focus?id:null});}
function bindRows(container){container.addEventListener('click',event=>{const button=event.target.closest('[data-row]');if(button)chooseRow(button.dataset.row,{focus:true});});container.addEventListener('keydown',event=>{const button=event.target.closest('[data-row]');if(!button)return;const{split}=selected();if(!split)return;let index=split.rows.findIndex(row=>row.id===button.dataset.row);if(event.key==='ArrowDown'||event.key==='ArrowRight')index=Math.min(split.rows.length-1,index+1);else if(event.key==='ArrowUp'||event.key==='ArrowLeft')index=Math.max(0,index-1);else if(event.key==='Home')index=0;else if(event.key==='End')index=split.rows.length-1;else return;event.preventDefault();chooseRow(split.rows[index].id,{focus:true});});}
bindRows($('#result-chart'));bindRows($('#result-records'));

function rowSubtitle(row){if(row.role==='baseline')return'Untouched baseline';if(row.role==='teacher')return'Separate teacher diagnostic';return[row.updates===null?null:number(row.updates)+' updates',row.seed===null?null:'seed '+row.seed].filter(Boolean).join(' · ')||'Trained adapter';}
function chartButton(row,split){const button=element('button',undefined,'result-row '+row.role+(row.id===selectedId?' selected':''));button.type='button';button.dataset.row=row.id;button.setAttribute('aria-pressed',String(row.id===selectedId));button.setAttribute('aria-label',row.label+', '+row.correct+' of '+row.total+' '+split.id+' questions, '+percent(row.accuracy));const name=element('span',undefined,'row-name');name.append(document.createTextNode(row.label),element('small',rowSubtitle(row)));const track=element('span',undefined,'row-track'),bar=element('span');track.setAttribute('aria-hidden','true');bar.style.width=row.accuracy+'%';track.append(bar);const value=element('span',undefined,'row-value');value.setAttribute('aria-hidden','true');value.append(document.createTextNode(row.correct),element('small','/'+row.total),element('b',percent(row.accuracy)));button.append(name,track,value);return button;}
function tableRow(row){const tr=element('tr'),th=element('th'),button=element('button',row.label,'table-row-button');th.scope='row';button.type='button';button.dataset.row=row.id;button.setAttribute('aria-pressed',String(row.id===selectedId));th.append(button);tr.append(th,element('td',row.correct+' / '+row.total),element('td',percent(row.accuracy)),element('td',row.truncated===null?'Not reported':String(row.truncated)));return tr;}
function addField(list,label,value){const wrapper=element('div');wrapper.append(element('dt',label),element('dd',value));list.append(wrapper);}

function renderEvidence(study,split,row){
  $('#evidence-title').textContent=row.label;$('#evidence-subtitle').textContent=split.label+' · '+rowSubtitle(row);$('#evidence-score').textContent=row.correct+' / '+row.total;
  const paired=$('#paired-comparison');paired.replaceChildren();
  if(row.comparison){const comparison=row.comparison;paired.append(element('p',comparison.label));const delta=element('strong');delta.append(document.createTextNode(signed(comparison.delta)+' '),element('span','percentage points'));paired.append(delta);paired.append(element('span',comparison.interval?'95% paired question-bootstrap interval: '+number(comparison.interval[0])+' to '+number(comparison.interval[1])+' pp.':'Descriptive difference only. No paired baseline interval is published for this contrast.'));if(comparison.corrected!==null)paired.append(element('span',comparison.corrected+' corrected · '+comparison.regressed+' regressed.'));}
  else{paired.append(element('p','Reference condition'),element('span','This is the untouched baseline. Trained arms are compared with a clearly named reference; no interval is invented for the baseline itself.'));}
  const fields=$('#evidence-fields');fields.replaceChildren();addField(fields,'Optimizer updates',row.role==='teacher'?'Not applicable':row.updates===null?'Not published':number(row.updates));addField(fields,'Supervised target tokens',row.role==='teacher'?'Not applicable':row.trainingTokens===null?'Not published':number(row.trainingTokens));addField(fields,'Output-capped answers',row.truncated===null?'Not published':row.truncated+' / '+row.total);addField(fields,'Training seed',row.role==='teacher'?'Not applicable':row.seed===null?'Not published':String(row.seed));
  const provenance=row.evidence.filter(item=>/scoring|sha|paired|strict|output|revision/i.test(item.label));
  if(provenance.length){const details=element('details',undefined,'provenance-details'),summary=element('summary','Scoring and provenance'),list=element('dl');for(const item of provenance)addField(list,item.label,item.value);details.append(summary,list);fields.append(details);}
  $('#evidence-note').textContent=(row.note?row.note+' ':'')+'Question-bootstrap intervals do not measure training-seed uncertainty. Numeric matches do not verify every reasoning step.';
  $('#source-data-link').href=row.sourcePath;$('#source-data-link').textContent='Open original evidence ↗';
  $('#evidence-json').textContent=JSON.stringify({representation:'Derived display record; original source linked below',study:study.id,partition:split.id,published_at_utc:study.updatedAt,...row},null,2);
  $('#evidence-details').hidden=evidenceView!=='details';$('#evidence-json').hidden=evidenceView!=='json';for(const button of document.querySelectorAll('button[data-evidence-view]'))button.setAttribute('aria-pressed',String(button.dataset.evidenceView===evidenceView));
}

function renderResults({focusRow=null}={}){
  const study=studies[studyId];if(!study)return;
  let split=study.splits.find(item=>item.id===splitId);if(!split){split=study.splits[0];splitId=split.id;}
  if(!split.rows.some(row=>row.id===selectedId))selectedId=studyId==='overnight'?'large-error':studyId==='matched-200'?'skill':'skill-42';
  if(!split.rows.some(row=>row.id===selectedId))selectedId=split.rows[0].id;
  const row=split.rows.find(item=>item.id===selectedId);
  $('#study-date').textContent=date(study.updatedAt);$('#study-label').textContent=study.label;$('#study-title').textContent=study.title;$('#study-summary').textContent=study.summary;$('#study-limitation').textContent=study.limitation;$('#chart-measure').textContent='Numeric answer accuracy · '+split.label;$('#records-caption').textContent=split.label+'. Counts and output caps from the original evidence.';$('#study-report-link').href=reportLinks[studyId];
  for(const button of document.querySelectorAll('button[data-study]'))button.setAttribute('aria-pressed',String(button.dataset.study===studyId));
  const splitControls=$('#split-controls');splitControls.replaceChildren();for(const item of study.splits){const button=element('button',item.id==='retention'?'Same-task retention':'Development');button.type='button';button.dataset.split=item.id;button.setAttribute('aria-pressed',String(item.id===splitId));splitControls.append(button);}splitControls.hidden=study.splits.length===1;
  $('#result-chart').replaceChildren(...split.rows.map(item=>chartButton(item,split)));$('#result-records').replaceChildren(...split.rows.map(tableRow));
  $('#chart-view').hidden=view!=='chart';$('#records-view').hidden=view!=='records';for(const button of document.querySelectorAll('button[data-view]'))button.setAttribute('aria-pressed',String(button.dataset.view===view));
  renderEvidence(study,split,row);$('#chart-selection-link').textContent='Inspect '+row.label+' ↓';Object.assign($('.result-workspace').dataset,{study:studyId,split:splitId,selected:selectedId,view});
  if(focusRow){const container=view==='chart'?$('#result-chart'):$('#result-records');container.querySelector('[data-row="'+CSS.escape(focusRow)+'"]')?.focus({preventScroll:true});}
}

document.querySelectorAll('button[data-study]').forEach(button=>button.addEventListener('click',()=>{studyId=button.dataset.study;splitId='development';selectedId='';renderResults();}));
$('#split-controls').addEventListener('click',event=>{const button=event.target.closest('button[data-split]');if(button){splitId=button.dataset.split;renderResults();}});
document.querySelectorAll('button[data-view]').forEach(button=>button.addEventListener('click',()=>{view=button.dataset.view;renderResults();}));
document.querySelectorAll('button[data-evidence-view]').forEach(button=>button.addEventListener('click',()=>{evidenceView=button.dataset.evidenceView;const{study,split,row}=selected();if(row)renderEvidence(study,split,row);}));

async function loadEvidence(){
  const generation=++loadNumber,button=$('#reload-evidence');button.disabled=true;$('#data-status').textContent='Loading published evidence files…';
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
  const entries=Object.entries(FEEDS),responses=await Promise.allSettled(entries.map(async([key,path])=>{const response=await fetch(path,{cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error(path+' unavailable');return[key,await response.json()];}));clearTimeout(timeout);if(generation!==loadNumber)return;
  payloads=Object.fromEntries(responses.filter(result=>result.status==='fulfilled').map(result=>result.value));const previousStudies=studies,next={},errors=[];
  for(const id of ['overnight','matched-200','token-64'])try{next[id]=buildStudy(id,payloads);}catch{errors.push(id);}
  studies=Object.keys(next).length?next:previousStudies;for(const tab of document.querySelectorAll('button[data-study]')){tab.disabled=!studies[tab.dataset.study];tab.setAttribute('aria-label',tab.textContent.trim().replace(/\s+/g,' ')+(tab.disabled?' · evidence unavailable':''));}
  if(Object.keys(studies).length){for(const control of document.querySelectorAll('button[data-view],button[data-evidence-view],button[data-split]'))control.disabled=false;if(!studies[studyId])studyId=Object.keys(studies)[0];renderResults();const newest=Object.values(studies).map(study=>study.updatedAt).sort((a,b)=>Date.parse(b)-Date.parse(a))[0];$('#data-status').textContent=Object.keys(next).length?'Published snapshots · newest '+date(newest)+' UTC. '+(errors.length?'Some study evidence is unavailable.':'No live jobs or account telemetry are queried.'):'Reload failed. Showing the previously loaded published evidence from '+date(newest)+' UTC; the original source remains linked.';}
  else{$('#data-status').textContent='Evidence files could not be loaded or validated. Showing only the dated 4 Nov 2026 report excerpt. Open the original report to verify it.';for(const control of document.querySelectorAll('button[data-view],button[data-evidence-view],button[data-split]'))control.disabled=true;}
  const feedback=payloads.feedback;if(next.overnight&&feedback?.schema_version===1&&feedback.teacher_estimate_not_invoice===true&&Number.isFinite(feedback.teacher_peak_token_estimate_usd)&&feedback.teacher_peak_token_estimate_usd>=0&&Number.isInteger(feedback.teacher_requests)&&feedback.teacher_requests>=0&&Number.isInteger(feedback.teacher_qualified)&&feedback.teacher_qualified>=0&&feedback.teacher_qualified<=feedback.teacher_requests){$('#teacher-estimate').textContent='≈ '+new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(feedback.teacher_peak_token_estimate_usd);$('#teacher-call-count').textContent=feedback.teacher_requests;$('#teacher-qualified-count').textContent=feedback.teacher_qualified;}
  button.disabled=false;
}
$('#reload-evidence').addEventListener('click',loadEvidence);loadEvidence();

const method={
  source:{kicker:'01 / Source checks',title:'A qualified answer is the starting point.',text:'DeepSeek reviewed 32 actual Granite attempts in the overnight study. Twenty-seven corrections passed numeric and arithmetic checks; five were rejected. Qualification is not independent verification of every reasoning step.',path:'overnight-feedback-results.json'},
  select:{kicker:'02 / Selection and controls',title:'Keep the comparison attributable.',text:'The correction arm used eight distinct taught mistakes plus eight replay examples. The random control used a separate selection with the same example and update counts. Complete-target token exposure was unequal; the outcome cannot be attributed to a perfectly compute-matched contrast.',path:'research/?report=overnight'},
  train:{kicker:'03 / Real adapter training',title:'Saved, reloaded, then evaluated.',text:'Independent LoRA adapters were trained on the pinned Granite 4.2 3B checkpoint. The local RTX 3060 runs saved and reloaded their adapter tensors before evaluation. The larger dose fitted the eight taught mistakes, which demonstrates fitting rather than transfer.',path:'overnight-results.md'},
  evaluate:{kicker:'04 / Separate questions',title:'The held-apart questions decide.',text:'The latest correction study measured 32 development and 32 same-task retention questions, under the same nonthinking greedy 512-token inference protocol. No adapter improved separate development accuracy. The official test split remained unopened.',path:'overnight-capacity-results.json'}
};
const methodButtons=[...document.querySelectorAll('[data-method]')];
function selectMethod(id){const record=method[id];for(const button of methodButtons)button.setAttribute('aria-pressed',String(button.dataset.method===id));$('#method-kicker').textContent=record.kicker;$('#method-detail-title').textContent=record.title;$('#method-detail-text').textContent=record.text;$('#method-detail-link').href=record.path;}
methodButtons.forEach((button,index)=>{button.addEventListener('click',()=>selectMethod(button.dataset.method));button.addEventListener('keydown',event=>{let next=index;if(event.key==='ArrowRight'||event.key==='ArrowDown')next=Math.min(methodButtons.length-1,index+1);else if(event.key==='ArrowLeft'||event.key==='ArrowUp')next=Math.max(0,index-1);else if(event.key==='Home')next=0;else if(event.key==='End')next=methodButtons.length-1;else return;event.preventDefault();selectMethod(methodButtons[next].dataset.method);methodButtons[next].focus();});});
