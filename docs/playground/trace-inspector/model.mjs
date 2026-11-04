// Authored interface fixtures. No measured Granite results or model reasoning.
export const SOURCES = Object.freeze({
  cohort: {document:'Protocol note',section:'1. Evaluation scope',text:'Both variants use one fixed evaluation cohort. Its identity is recorded before either comparison is inspected.'},
  budget: {document:'Protocol note',section:'2. Training exposure',text:'The comparison states the supervised token budget and update count. Example counts and elapsed time are reported separately.'},
  changes: {document:'Interpretation note',section:'1. Question-level changes',text:'Corrections, regressions and unchanged outcomes accompany the aggregate comparison. Both directions remain visible.'},
  interval: {document:'Interpretation note',section:'2. Qualification',text:'Any reported difference keeps its uncertainty interval and evaluation scope. An exploratory comparison is not presented as a general result.'},
  identity: {document:'Artifact index',section:'1. Model reference',text:'A reproducible record identifies its model and revision. This demonstration uses an illustrative placeholder, not a model release.'},
  receipt: {document:'Artifact index',section:'2. Receipt reference',text:'A saved artifact is linked through its stable record identity. This demonstration contains no actual run receipt or verified hash.'}
});

export const RECORDS = Object.freeze([
  {id:'packet',parent:null,label:'Research packet',kind:'Packet',code:'P–017',summary:'Keep the finding attached to its records.',input:'An authored protocol, interpretation note and artifact index.',output:'One inspectable packet. Every child retains a visible parent and source reference.',sources:['cohort','changes','receipt']},
  {id:'protocol',parent:'packet',label:'Protocol note',kind:'Source',code:'S–01',summary:'Define what was compared.',input:'Evaluation scope and training exposure statements.',output:'Two explicit checks: the cohort stays fixed and the training budget is stated.',sources:['cohort','budget']},
  {id:'cohort',parent:'protocol',label:'Fixed cohort',kind:'Check',code:'C–01',summary:'The question set has one identity.',input:'Protocol note / Evaluation scope.',output:'Both variants belong to the same fixed cohort. The scope remains attached to the comparison.',sources:['cohort']},
  {id:'budget',parent:'protocol',label:'Exposure budget',kind:'Check',code:'C–02',summary:'Matched exposure needs an explicit definition.',input:'Protocol note / Training exposure.',output:'Read supervised token count and update count separately from examples and runtime.',sources:['budget']},
  {id:'interpretation',parent:'packet',label:'Interpretation note',kind:'Source',code:'S–02',summary:'Explain a difference without losing its limits.',input:'Question-level outcomes and a qualification statement.',output:'Keep changes and uncertainty visible together. No numeric result is invented for this demo.',sources:['changes','interval']},
  {id:'changes',parent:'interpretation',label:'Changes retained',kind:'Check',code:'C–03',summary:'Corrections and regressions both remain visible.',input:'Interpretation note / Question-level changes.',output:'Inspect both directions of change alongside the aggregate, rather than hiding regressions.',sources:['changes']},
  {id:'interval',parent:'interpretation',label:'Uncertainty note',kind:'Qualification',code:'Q–01',summary:'Keep the interval with the claim.',input:'A difference statement from the interpretation note.',output:'Retain the uncertainty interval, cohort scope and exploratory qualification beside the finding.',sources:['interval']},
  {id:'provenance',parent:'packet',label:'Artifact index',kind:'Source',code:'S–03',summary:'Give the supporting artifacts stable identities.',input:'Model and receipt references.',output:'Record what an artifact identifies. Do not substitute an animated status for evidence.',sources:['identity','receipt']},
  {id:'identity',parent:'provenance',label:'Model reference',kind:'Reference',code:'R–01',summary:'A model name is not a complete identity.',input:'Artifact index / Model reference.',output:'A real integration would display a model plus pinned revision. No real revision is claimed here.',sources:['identity']},
  {id:'receipt',parent:'provenance',label:'Receipt reference',kind:'Reference',code:'R–02',summary:'The record points to an artifact, not a visual effect.',input:'Artifact index / Receipt reference.',output:'A real integration would link the saved receipt. This illustrative packet contains no verified receipt.',sources:['receipt']},
  {id:'finding',parent:'packet',label:'Bounded finding',kind:'Finding',code:'F–01',summary:'An inspectable claim keeps its context.',input:'Protocol, interpretation and provenance records in this packet.',output:'The interface explains which records support a statement. It makes no measured model-performance claim.',sources:['cohort','interval','receipt']}
].map(Object.freeze));

export const byId = id => RECORDS.find(record=>record.id===id) ?? null;
export const childrenOf = id => RECORDS.filter(record=>record.parent===id);
export function ancestorsOf(id) {
  const path=[];
  let record=byId(id);
  const seen=new Set();
  while(record?.parent&&!seen.has(record.parent)){
    seen.add(record.parent);record=byId(record.parent);if(record)path.unshift(record);
  }
  return path;
}
export function filteredRecords(query='',kind='all') {
  const q=query.trim().toLowerCase();
  const matches=RECORDS.filter(record=>(kind==='all'||record.kind===kind)&&(!q||[record.label,record.kind,record.code,record.summary,record.input,record.output].join(' ').toLowerCase().includes(q)));
  const ids=new Set(matches.flatMap(record=>[record.id,...ancestorsOf(record.id).map(parent=>parent.id)]));
  return {matches,ids,active:Boolean(q||kind!=='all')};
}
export function visibleRecords({query='',kind='all',expanded=new Set()}={}) {
  const filter=filteredRecords(query,kind);
  return {filter,records:RECORDS.filter(record=>filter.ids.has(record.id)&&ancestorsOf(record.id).every(parent=>filter.active||expanded.has(parent.id)))};
}
