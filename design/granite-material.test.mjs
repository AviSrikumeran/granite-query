import test from 'node:test';
import assert from 'node:assert/strict';
import {SHAPES,layoutFor} from '../docs/playground/granite/geometry.mjs';
import {ghostOffsets,ghostWeight,introCell,materialColors,softenedNormal,occlusionAt,litSurface,viewDirection} from '../docs/playground/granite/material.mjs';
const close=(a,b,e=1e-6)=>assert.ok(Math.abs(a-b)<e,`${a} != ${b}`);

test('peripheral views use three adjacent projected lattice cells',()=>{
  const offsets=ghostOffsets();close(offsets[0][0],-3.4641016);close(offsets[0][1],0);
  close(offsets[1][0],1.7320508);close(offsets[1][1],-3);
  close(offsets[2][0],1.7320508);close(offsets[2][1],3);
  const moved=ghostOffsets(.105,.065);assert.notDeepEqual(moved,offsets);
  for(const offset of moved)assert.ok(offset.every(Number.isFinite));
  // Rendering transforms do not mutate the accepted geometry or layout.
  const before=JSON.stringify(SHAPES),layout=layoutFor(1640,900);
  ghostOffsets(-.105,-.065);assert.equal(JSON.stringify(SHAPES),before);assert.deepEqual(layoutFor(1640,900),layout);
});
test('peripheral brightness fades continuously toward the outer field',()=>{
  const values=[0,1,2,3,4,5].map(x=>ghostWeight(x,0));
  for(let i=1;i<values.length;i++)assert.ok(values[i]<=values[i-1]);
  close(values[0],.51);close(values.at(-1),0);assert.ok(ghostWeight(2,2)>0);
});
test('intro scales marks in place and briefly exceeds settled brightness',()=>{
  const early=introCell(.8,1,.5),center=introCell(1.08,.1,.5),edge=introCell(1.08,2,.5);
  assert.equal(early.alpha,0);assert.ok(center.alpha>edge.alpha);
  assert.ok(center.flash>1);assert.ok(center.scale<=1);
  assert.deepEqual(introCell(1.55,2.4,.99),{alpha:1,scale:1,flash:1});
});
test('key, fill and softened normals produce face-specific shading',()=>{
  const view=viewDirection(),side=litSurface([1,0,0],[0,0,0],view),top=litSurface([0,1,0],[0,0,0],view);
  assert.ok(side>top+.2);
  const normal=softenedNormal([1,.99,0],{half:[1,1,1]});close(Math.hypot(...normal),1);
  assert.ok(normal[0]>.5&&normal[1]>.5);
  assert.ok(litSurface([1,0,0],[0,0,0],view,.3)<side);
});
test('nearby geometry shades contact regions without extinguishing isolated faces',()=>{
  const alone=[{center:[0,0,0],half:[1,1,1]}],closeNeighbor=[...alone,{center:[2.1,0,0],half:[1,1,1]}];
  const open=occlusionAt([1,0,0],[1,0,0],alone),contact=occlusionAt([1,0,0],[1,0,0],closeNeighbor);
  close(open,1);assert.ok(contact<open-.3);assert.ok(contact>=0);
});
test('material tiers remain finite under hue changes and retain a large brightness range',()=>{
  for(const hex of ['#7fee64','#81d9fa','#ff79bd','#000000','#ffffff']){
    const colors=materialColors(hex);assert.equal(colors.length,48);assert.ok(colors.every(v=>Number.isFinite(v)&&v>=0&&v<=1));
  }
  const colors=materialColors();assert.ok(Math.max(...colors.slice(-3))>.99);assert.ok(Math.max(...colors.slice(0,3))<.2);
});
