import test from 'node:test';
import assert from 'node:assert/strict';
import {NODES,EDGES,STAGES,toWorld,graphAt,nodeVisibility,edgeTiming,layoutFor,project,progressFromScroll} from '../docs/playground/proof-branches/graph.mjs';
import {rotate} from '../docs/playground/proof-branches/engine/geometry.mjs';
import {materialColors} from '../docs/playground/proof-branches/engine/material.mjs';
import {materialColors as baselineColors} from '../docs/playground/purple/engine/material.mjs';
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} != ${b}`);

test('every evidence requirement retains one source and contributes to the qualified answer',()=>{
  const paths=EDGES.map(([a,b])=>[NODES[a].id,NODES[b].id]);
  for(const node of NODES.filter(n=>n.kind==='Evidence requirement')){
    const index=NODES.indexOf(node),parents=EDGES.filter(([,b])=>b===index);
    assert.equal(parents.length,1);assert.equal(NODES[parents[0][0]].title,node.source);
    assert.ok(paths.some(([a,b])=>a===node.id&&b==='answer'));
  }
  const reached=new Set([0]);for(const [a,b] of EDGES){assert.ok(reached.has(a));reached.add(b);}assert.equal(reached.size,NODES.length);
});
test('parents appear before their paths grow and every incoming answer path is complete before its node',()=>{
  for(const [from,to] of EDGES){const [start,end]=edgeTiming(from,to);assert.ok(start>=NODES[from].at+.025);assert.equal(end,NODES[to].at);assert.ok(end>start);}
  for(let i=0;i<=500;i++){
    const p=i/500;
    for(const [from,to] of EDGES){const [start,end]=edgeTiming(from,to);if(p>start)assert.equal(nodeVisibility(NODES[from],p),1);if(nodeVisibility(NODES[to],p)>0)assert.ok(p>=end);}
  }
});
test('all oriented path legs remain finite and attach to both endpoint nodes when complete',()=>{
  for(let i=0;i<=250;i++){
    const scene=graphAt(i/250);assert.equal(scene.boxes.length,40);
    for(const box of scene.boxes){assert.ok([...box.center,...box.half,...box.rotation,box.emission].every(Number.isFinite));near(Math.hypot(...box.rotation),1);}
  }
  const scene=graphAt(1);
  EDGES.forEach(([from,to],index)=>{
    const legs=[0,1].map(leg=>scene.boxes.find(b=>b.role===`edge:${index}:${leg}`));
    const endpoints=legs.map(b=>{const offset=rotate(b.rotation,[0,b.half[1],0]);return [b.center.map((v,k)=>v-offset[k]),b.center.map((v,k)=>v+offset[k])];});
    endpoints[0][0].forEach((v,k)=>near(v,toWorld(NODES[from].point)[k]));
    endpoints[0][1].forEach((v,k)=>near(v,endpoints[1][0][k]));
    endpoints[1][1].forEach((v,k)=>near(v,toWorld(NODES[to].point)[k]));
  });
});
test('scroll interpolation hits each section, clamps bounds and reverses without extra state',()=>{
  const anchors=[180,750,1340,1980];
  anchors.forEach((v,i)=>near(progressFromScroll(v,anchors),STAGES[i].progress));
  near(progressFromScroll(-100,anchors),0);near(progressFromScroll(9000,anchors),1);
  let previous=-1;
  for(let s=0;s<=2200;s+=10){const p=progressFromScroll(s,anchors);assert.ok(p>=previous);previous=p;assert.deepEqual(graphAt(p),graphAt(progressFromScroll(s,anchors)));}
  assert.throws(()=>progressFromScroll(100,[0,5,4,9]));
  assert.equal(NODES.filter(n=>nodeVisibility(n,0)===1).length,1);assert.equal(NODES.filter(n=>nodeVisibility(n,1)===1).length,11);
});
test('projected node controls track world geometry and remain framed at mouse extremes',()=>{
  for(const [w,h] of [[280,220],[350,280],[480,350],[667,414],[760,510]])for(const turn of [-.105,0,.105])for(const tilt of [-.065,.065]){
    const layout=layoutFor(w,h),c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
    for(const node of NODES){
      const v=toWorld(node.point),y=v[1]*ct+v[2]*st,z=-v[1]*st+v[2]*ct,q=[v[0]*c+z*s,y,-v[0]*s+z*c],pos=project(node.point,layout,turn,tilt);
      near(pos[0],layout.center[0]+.8660254*(q[0]-q[2])*layout.unit);near(pos[1],layout.center[1]+(.5*q[0]-q[1]+.5*q[2])*layout.unit);
      assert.ok(pos[0]>=22&&pos[0]<=w-22&&pos[1]>=22&&pos[1]<=h-35,`${node.id} clipped at ${w}x${h}`);
    }
  }
});
test('the established electric magenta color ramp is preserved',()=>assert.deepEqual(materialColors('magenta'),baselineColors('magenta')));
