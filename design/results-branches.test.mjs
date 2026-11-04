import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {deriveStudy,deriveNative,unavailableStudy,REVIEWED} from '../docs/playground/results-branches/data.mjs';
import {NODES,graphAt,bindContent} from '../docs/playground/results-branches/graph.mjs';
import {graphAt as illustrativeGraphAt} from '../docs/playground/proof-branches/graph.mjs';
const raw=fs.readFileSync(new URL('./fixtures/results-branches/human-study-results.json',import.meta.url));
const source=JSON.parse(raw),native=JSON.parse(fs.readFileSync(new URL('./fixtures/results-branches/native-reasoning-study.json',import.meta.url)));
const clone=()=>structuredClone(source),now=Date.parse(source.generated_at_utc)+60000;

test('the reviewed public snapshot produces the published negative point estimate and inconclusive interval',()=>{
  const model=deriveStudy(source,{now});
  assert.equal(model.status,'ready');assert.equal(model.verdict,'No gain demonstrated');
  assert.deepEqual(Object.values(model.jobs).map(j=>j.correct),[179,174,171]);
  assert.equal(model.comparison.delta,-1.5);assert.deepEqual(model.comparison.interval,[-4.5,1.5]);
  assert.equal(model.comparison.corrected,3);assert.equal(model.comparison.regressed,6);
  assert.equal(model.receipts,3);assert.match(model.scope,/200.*development/);assert.match(model.budget,/65,536/);
});
test('missing, failed and unverified jobs never become zero scores or an advantage',()=>{
  for(const status of ['prepared','running','failed']){
    const d=clone();d.jobs.skill.status=status;d.jobs.skill.metrics=null;
    const m=deriveStudy(d,{now});assert.equal(m.jobs.skill.correct,null);assert.equal(m.comparison,null);assert.equal(m.verdict,'Comparison pending');
  }
  const d=clone();d.jobs.skill.unique_call_observed=false;
  const m=deriveStudy(d,{now});assert.equal(m.jobs.skill.status,'unverified');assert.equal(m.jobs.skill.correct,null);assert.equal(m.comparison,null);
});
test('completed counts, study scope and supplied paired statistics must agree',()=>{
  const mutations=[
    d=>d.schema_version=2,
    d=>d.study_id='different-study',
    d=>d.cohort.legacy64_results_merged=true,
    d=>d.cohort.split='test',
    d=>d.protocol.enable_thinking=true,
    d=>d.jobs.skill.metrics.count=64,
    d=>d.jobs.skill.metrics.numeric_correct=201,
    d=>d.jobs.skill.accuracy_percent=99,
    d=>d.comparisons.skill_vs_random.statistics.count=64,
    d=>d.comparisons.skill_vs_random.statistics.difference_percentage_points=3,
    d=>d.comparisons.skill_vs_random.statistics.paired_bootstrap_95_interval_pp=[2,5]
  ];
  for(const mutate of mutations){const d=clone();mutate(d);assert.throws(()=>deriveStudy(d,{now}));}
});
test('unmatched budgets or missing paired uncertainty withhold the finding',()=>{
  const a=clone();a.jobs.skill.actual_supervised_tokens=32768;assert.equal(deriveStudy(a,{now}).comparison,null);
  const b=clone();b.comparisons=null;assert.equal(deriveStudy(b,{now}).status,'pending');
});
test('freshness is explicit and impossible future timestamps are rejected',()=>{
  assert.equal(deriveStudy(source,{now:now+86400000}).age.stale,true);
  assert.equal(deriveStudy(source,{now}).age.stale,false);
  assert.throws(()=>deriveStudy(source,{now:now-600000}));
});
test('only identical feed bytes receive the reviewed report permalink',()=>{
  const digest=crypto.createHash('sha256').update(raw).digest('hex');assert.equal(digest,REVIEWED.sha256);
  const reviewed=deriveStudy(source,{now,digest});
  assert.match(reviewed.links.report.href,new RegExp(REVIEWED.commit));
  assert.equal(reviewed.links.report.label,'Reviewed report');
  const updated=deriveStudy(source,{now,digest:'a'.repeat(64)});
  assert.match(updated.links.report.href,/\/main\//);assert.equal(updated.links.report.label,'Latest report');
});
test('all actual evidence nodes retain public source links and leaf field paths',()=>{
  const model=deriveStudy(source,{now});
  for(const node of Object.values(model.nodes))assert.ok(node.links.length>0);
  for(const id of ['matched','scope','comparison','uncertainty','settings']){assert.ok(model.nodes[id].pointer.startsWith('/'));assert.ok(model.nodes[id].source);}
});
test('the separate native recipe reports prepared scores as unavailable even if an unverified score appears',()=>{
  const d=structuredClone(native);d.jobs[0].accuracy_percent=100;d.jobs[0].metrics={count:200,numeric_correct:200};
  const model=deriveNative(d,{now:Date.parse(d.updated_at_utc)+60000});
  assert.ok(model.jobs.every(j=>j.score==='Not available'));assert.match(model.note,/not combined/);
});
test('unavailable evidence carries no invented score or example result',()=>{
  const model=unavailableStudy('Network unavailable');
  assert.deepEqual(model.jobs,{});assert.equal(model.comparison,null);assert.equal(model.verdict,'Evidence unavailable');
  assert.ok(Object.values(model.nodes).every(n=>n.text.includes('No result is inferred')));
});
test('binding real evidence preserves the complete accepted branch geometry and reveal timing',()=>{
  const model=deriveStudy(source,{now});bindContent(model.nodes);
  assert.ok(NODES.every(node=>typeof node.label==='string'&&node.label.length>0));
  for(const p of [0,.12,.22,.36,.51,.72,.90,1])assert.deepEqual(graphAt(p),illustrativeGraphAt(p));
});
