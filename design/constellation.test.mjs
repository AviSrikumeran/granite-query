import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {deriveStudy} from '../docs/playground/constellation/data.mjs';
import {deriveStudy as baselineStudy} from '../docs/playground/results-branches/data.mjs';
import {RECORDS,sceneAt,phaseAt,sequenceAt,PERIOD,routeFor,layoutFor,boxHull,springStep,connections,bezier} from '../docs/playground/constellation/forms.mjs';
import {materialColors} from '../docs/playground/constellation/engine/material.mjs';
import {materialColors as baselineColors} from '../docs/playground/results-branches/engine/material.mjs';
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8);
test('the sculpture has stable capacity and finite oriented parts in every scene',()=>{
  for(let i=0;i<=250;i++){const s=sceneAt(i/250,{time:4});assert.equal(s.boxes.length,40);assert.equal(s.panels.length,8);assert.equal(s.boxes.filter(b=>b.role!=='unused').length,32);for(const b of s.boxes){assert.ok([...b.center,...b.half,...b.rotation,b.emission].every(Number.isFinite));near(Math.hypot(...b.rotation),1);}}
});
test('archive, burst and resolve are distinct and the full cycle closes continuously',()=>{
  assert.equal(phaseAt(.04).open,0);assert.equal(phaseAt(.28).open,1);assert.equal(phaseAt(.78).resolve,1);
  assert.notDeepEqual(sceneAt(.04).boxes,sceneAt(.28).boxes);assert.notDeepEqual(sceneAt(.28).boxes,sceneAt(.78).boxes);
  assert.deepEqual(sceneAt(0).boxes,sceneAt(1).boxes);near(sequenceAt(PERIOD),0);
  for(const p of [.105,.15,.61,.66,.87,.90,.91,.98]){const a=sceneAt(p-1e-6).boxes,b=sceneAt(p+1e-6).boxes;a.forEach((part,i)=>part.center.forEach((v,k)=>assert.ok(Math.abs(v-b[i].center[k])<.001)));}
});
test('each tile maps to a real evidence role and focus traces the proper ancestry',()=>{
  assert.equal(new Set(RECORDS.map(r=>r.id)).size,8);
  assert.deepEqual([...routeFor(6)].sort(),[1,6]);assert.deepEqual([...routeFor(0)].sort(),[0,3,4]);assert.equal(routeFor(-1).size,8);
});
test('filaments attach to their moving records, including all five finding links',()=>{
  for(const p of [.04,.28,.52,.78]){const s=sceneAt(p,{time:4,offsets:RECORDS.map(()=>({x:.25,y:-.2}))}),paths=connections(s);assert.equal(paths.length,13);for(const path of paths){assert.ok(path.alpha>=0&&path.alpha<=1);assert.deepEqual(bezier(path.controls,0),path.controls[0]);assert.deepEqual(bezier(path.controls,1),path.controls[3]);assert.ok(path.controls.every(point=>point.every(Number.isFinite)));}}
});
test('spring release settles with bounded energy instead of drifting indefinitely',()=>{
  const offset={x:.65,y:-.65,vx:0,vy:0};let maximum=0;for(let i=0;i<240;i++){springStep(offset,1/60);maximum=Math.max(maximum,Math.abs(offset.x),Math.abs(offset.y));}assert.ok(maximum<=.65);assert.deepEqual(offset,{x:0,y:0,vx:0,vy:0});
});
test('the full sculpture and pulled tiles remain inside wide and narrow canvases',()=>{
  for(const [w,h] of [[280,350],[335,350],[850,500],[1185,550]])for(const p of [.04,.12,.28,.52,.635,.78,.91])for(const turn of [-.168,.168])for(const tilt of [-.104,.104]){
    const layout=layoutFor(w,h);for(const sign of [-1,1]){const s=sceneAt(p,{time:4,spreadX:w<700?.82:1.6,offsets:RECORDS.map(()=>({x:sign*.65,y:sign*.65}))});for(const b of s.boxes.filter(b=>b.role!=='unused'))for(const [x,y] of boxHull(b,layout,turn,tilt)){assert.ok(x>=0&&x<=w&&y>=0&&y<=h-12,`clipped ${b.role} ${w}x${h} p=${p}: ${x},${y}`);}}
  }
});
test('electric magenta material is preserved',()=>assert.deepEqual(materialColors('magenta'),baselineColors('magenta')));
test('every spatial tile is backed by the unchanged public evidence contract',()=>{
  const data=JSON.parse(fs.readFileSync(new URL('./fixtures/results-branches/human-study-results.json',import.meta.url))),options={now:Date.parse(data.generated_at_utc)+60000},model=deriveStudy(data,options);
  assert.deepEqual(model,baselineStudy(data,options));for(const record of RECORDS){assert.ok(model.nodes[record.id].links.length>0);assert.ok(model.nodes[record.id].title.length>0);}assert.equal(model.verdict,'No gain demonstrated');
});
