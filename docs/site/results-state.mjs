/* Exact-view links are presentation state, never a source of research data. */
export const DEFAULT_RESULT_STATE=Object.freeze({study:'overnight',split:'development',row:'large-error',view:'chart',evidence:'details'});
const DEFAULT_ROWS=Object.freeze({overnight:'large-error','matched-200':'skill','token-64':'skill-42'});
const STATE_KEYS=Object.freeze(['study','split','row','view','evidence']);

export function readResultState(input){
  const url=new URL(input,'https://example.invalid/results/');
  return Object.fromEntries(STATE_KEYS.map(key=>[key,url.searchParams.get(key)??DEFAULT_RESULT_STATE[key]]));
}

export function normalizeResultState(candidate,studies){
  const ids=Object.keys(studies);
  if(!ids.length)return {...DEFAULT_RESULT_STATE};
  const study=Object.hasOwn(studies,candidate.study)?candidate.study:Object.hasOwn(studies,'overnight')?'overnight':ids[0];
  const record=studies[study];
  const partition=record.splits.find(item=>item.id===candidate.split)??record.splits[0];
  const row=partition.rows.some(item=>item.id===candidate.row)?candidate.row:partition.rows.find(item=>item.id===DEFAULT_ROWS[study])?.id??partition.rows[0].id;
  return {study,split:partition.id,row,view:candidate.view==='records'?'records':'chart',evidence:candidate.evidence==='json'?'json':'details'};
}

export function resultStateURL(input,state){
  const url=new URL(input,'https://example.invalid/results/');
  for(const key of STATE_KEYS)url.searchParams.set(key,state[key]);
  return url;
}
