import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {FEEDS,buildStudy} from './data.js';

const fixtures=Object.fromEntries(Object.entries(FEEDS).map(([key,path])=>[key,JSON.parse(fs.readFileSync(new URL('../'+path,import.meta.url),'utf8'))]));
const copy=()=>structuredClone(fixtures);
const allRows=study=>study.splits.flatMap(split=>split.rows);

test('latest completed local doses remain separate from the older matched cohort',()=>{
  const study=buildStudy('overnight',fixtures);
  assert.equal(study.updatedAt,fixtures.capacity.updated_at_utc);
  assert.deepEqual(study.splits.map(split=>split.count),[32,32]);
  assert.deepEqual(study.splits[0].rows.map(row=>row.id),['base','small-error','small-random','large-error','large-random']);
  assert.deepEqual(study.splits[0].rows.map(row=>row.correct),[30,30,30,28,29]);
  assert.deepEqual(study.splits[1].rows.map(row=>row.correct),[29,26,28,27,25]);
  assert.equal(study.splits[1].rows[3].comparison.delta,-6.25);
  assert.deepEqual(study.splits[1].rows[4].comparison.interval,[-25,-3.125]);
  for(const row of allRows(study))assert.equal(row.accuracy,row.correct/row.total*100);
});
test('matched200 joins only identical teacher/student cohorts and keeps the skill/random comparator explicit',()=>{
  const study=buildStudy('matched-200',fixtures),rows=study.splits[0].rows;
  assert.deepEqual(rows.map(row=>row.id),['teacher','base','random','skill']);
  assert.deepEqual(rows.map(row=>row.correct),[194,179,174,171]);
  assert.deepEqual(rows.map(row=>row.accuracy),[97,89.5,87,85.5]);
  assert.equal(rows[0].role,'teacher');assert.equal(rows[0].updates,null);assert.equal(rows[0].seed,null);
  assert.deepEqual(rows[0].comparison.interval,[4,11.5]);
  assert.equal(rows[3].comparison.label,'vs random-trained Granite');assert.equal(rows[3].comparison.delta,-1.5);
  assert.deepEqual(rows[3].comparison.interval,[-4.5,1.5]);
});
test('token64 uses the matched batch8 baseline and preserves both seeds without pooling',()=>{
  const study=buildStudy('token-64',fixtures),rows=study.splits[0].rows;
  assert.equal(study.splits[0].count,64);
  assert.deepEqual(rows.map(row=>row.id),['base','random-42','skill-42','random-43','skill-43']);
  assert.deepEqual(rows.map(row=>row.correct),[58,55,53,57,56]);
  assert.equal(rows[0].sourcePath,FEEDS.research);
  assert.equal(rows[1].comparison.interval,null);assert.equal(rows[1].comparison.corrected,null);
  assert.ok(rows[2].evidence.some(item=>item.label==='Paired skill − random'&&item.value.includes('-3.125')));
  assert.match(study.limitation,/not 128 independent/);
});
test('missing optional metrics stay unknown while observed zeros stay zero',()=>{
  const data=copy();delete data.capacity.metrics.error.updates;delete data.capacity.metrics.error.full_target_loss_tokens_from_validated_updates;
  delete data.capacity.metrics.error.development.truncated;
  const row=buildStudy('overnight',data).splits[0].rows[3];
  assert.equal(row.updates,null);assert.equal(row.trainingTokens,null);assert.equal(row.truncated,null);assert.equal(row.seed,null);
  const baseline=buildStudy('overnight',data).splits[0].rows[0];assert.equal(baseline.updates,0);assert.equal(baseline.trainingTokens,0);assert.equal(baseline.truncated,0);
});
test('wrong cohorts, source aliases and denominators are rejected rather than merged',()=>{
  for(const mutate of [d=>d.teacher.source_sha256='0'.repeat(64),d=>d.human.cohort.split='test',d=>d.teacher.teacher.metrics.count=64,d=>d.human.protocol.max_new_tokens=1024]){
    const data=copy();mutate(data);assert.throws(()=>buildStudy('matched-200',data),/Study unavailable/);
  }
  const token=copy();token.research.token_matched32768.batched_baseline.development_source_sha256='0'.repeat(64);assert.throws(()=>buildStudy('token-64',token),/Study unavailable/);
  const local=copy();local.feedback.metrics.baseline.development.numeric_correct=29;local.feedback.metrics.baseline.development.strict_format_correct=29;assert.throws(()=>buildStudy('overnight',local),/reused baseline/);
  const plan=copy();plan.capacity.plan_sha256='0'.repeat(64);assert.throws(()=>buildStudy('overnight',plan),/plan identity/);
});
test('schema, nonfinite values, completion and missing core counts fail closed',()=>{
  for(const mutate of [d=>d.capacity.schema_version=2,d=>d.capacity.metrics.error.development.numeric_correct=NaN,d=>d.capacity.metrics.error.updates=Infinity,d=>d.capacity.stage='running',d=>d.capacity.metrics.error.development.numeric_correct=null]){
    const data=copy();mutate(data);assert.throws(()=>buildStudy('overnight',data),/Study unavailable/);
  }
  assert.throws(()=>buildStudy('unrecognized',fixtures),/unsupported study/);
});
test('paired deltas and changes must agree with exact model counts',()=>{
  const data=copy();data.human.comparisons.skill_vs_random.statistics.difference_percentage_points=1.5;assert.throws(()=>buildStudy('matched-200',data),/delta disagrees/);
  const flipped=copy();flipped.capacity.comparisons.error_vs_base.development.paired_question_bootstrap95_pp=[1,-1];assert.throws(()=>buildStudy('overnight',flipped),/interval/);
  const mismatch=copy();mismatch.valuation.pairs['42'].paired_valued_vs_random.corrected=5;assert.throws(()=>buildStudy('token-64',mismatch),/paired changes/);
});
test('filename-keyed payloads are supported and normalization does not mutate fixtures',()=>{
  const before=JSON.stringify(fixtures);
  const byFilename=Object.fromEntries(Object.entries(FEEDS).map(([key,path])=>[path,fixtures[key]]));
  for(const id of ['overnight','matched-200','token-64'])assert.equal(buildStudy(id,byFilename).id,id);
  assert.equal(JSON.stringify(fixtures),before);
});
