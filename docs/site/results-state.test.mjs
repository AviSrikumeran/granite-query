import test from 'node:test';
import assert from 'node:assert/strict';
import {readResultState,normalizeResultState,resultStateURL} from './results-state.mjs';

const rows=(...ids)=>ids.map(id=>({id}));
const studies={
  overnight:{splits:[{id:'development',rows:rows('base','large-error')},{id:'retention',rows:rows('base','large-error')}]},
  'matched-200':{splits:[{id:'development',rows:rows('teacher','base','random','skill')}]},
  'token-64':{splits:[{id:'development',rows:rows('base','skill-42','random-43')}]}
};
test('all exact-view dimensions survive a link reload without losing unrelated query or anchor',()=>{
  const state={study:'overnight',split:'retention',row:'base',view:'records',evidence:'json'};
  const url=resultStateURL('https://example.com/results/?campaign=review#selected-evidence',state);
  assert.deepEqual(normalizeResultState(readResultState(url),studies),state);
  assert.equal(url.searchParams.get('campaign'),'review');
  assert.equal(url.hash,'#selected-evidence');
});
test('invalid query values cannot select nonexistent studies, partitions, rows or representations',()=>{
  const state=normalizeResultState(readResultState('https://example.com/results/?study=unknown&split=test&row=%3Cscript%3E&view=invalid&evidence=anything'),studies);
  assert.deepEqual(state,{study:'overnight',split:'development',row:'large-error',view:'chart',evidence:'details'});
});
test('changing study preserves only a valid row and partition for that study',()=>{
  const state=normalizeResultState({study:'matched-200',split:'retention',row:'large-error',view:'chart',evidence:'json'},studies);
  assert.deepEqual(state,{study:'matched-200',split:'development',row:'skill',view:'chart',evidence:'json'});
});
test('object-prototype names are not accepted as study identities',()=>{
  assert.equal(normalizeResultState({study:'__proto__'},studies).study,'overnight');
  assert.equal(normalizeResultState({study:'constructor'},studies).study,'overnight');
});
test('an unavailable feed falls back to an available study without a dangling row',()=>{
  assert.deepEqual(normalizeResultState(readResultState('https://example.com/results/'),{'token-64':studies['token-64']}),{study:'token-64',split:'development',row:'skill-42',view:'chart',evidence:'details'});
});
test('history entries restore the exact selection and can be normalized repeatedly',()=>{
  const first={study:'matched-200',split:'development',row:'random',view:'records',evidence:'json'};
  const second={study:'token-64',split:'development',row:'random-43',view:'chart',evidence:'details'};
  const entries=[first,second].map(state=>resultStateURL('https://example.com/results/',state));
  for(const [index,url] of entries.entries()){
    const state=normalizeResultState(readResultState(url),studies);
    assert.deepEqual(state,[first,second][index]);
    assert.equal(resultStateURL(url,state).href,url.href);
  }
});
