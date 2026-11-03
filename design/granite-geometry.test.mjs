import test from 'node:test';
import assert from 'node:assert/strict';
import {FORMS,SHAPES,BOX_COUNT,BOOT,HOLD,TRANSITION,SWITCH_AT,STEP,PERIOD,boxesAt,switchState,revealAt,highlightFlare,paletteRamp,cameraRotate,traceBoxes} from '../docs/playground/granite/geometry.mjs';
const close=(a,b,e=1e-8)=>assert.ok(Math.abs(a-b)<e,a+' != '+b);

test('retained forms are distinct, finite, and bounded; removed forms cannot enter the sequence',()=>{
  assert.deepEqual(FORMS,['frames','steps','slabs','tiers']);
  assert.equal(new Set(FORMS.map(f=>JSON.stringify(SHAPES[f]))).size,4);
  for(const form of FORMS){
    assert.equal(SHAPES[form].length,BOX_COUNT);
    const active=SHAPES[form].filter(b=>b.half.every(v=>v>0));assert.ok(active.length>=3);
    for(const b of active){assert.ok([...b.center,...b.half,...b.rotation].every(Number.isFinite));assert.ok(b.half.every(v=>v<=1.1));assert.ok(b.center.every(v=>Math.abs(v)<=1.1));}
  }
});
test('a highlight flare never lifts dark areas and increases the already-bright areas',()=>{
  for(const light of [0,.1,.3,.48])close(highlightFlare(light,1),light);
  assert.ok(highlightFlare(.9,1)>.9);close(highlightFlare(.9,0),.9);
});
test('the shape commits directly under the flare, without any disassembled geometry',()=>{
  for(let i=0;i<FORMS.length;i++){
    const from=FORMS[i],to=FORMS[(i+1)%FORMS.length];
    for(let n=0;n<=100;n++){
      const elapsed=n/100*TRANSITION,scene=boxesAt(i*STEP+HOLD+elapsed);
      const expected=elapsed<SWITCH_AT?from:to;
      assert.deepEqual(scene.boxes,SHAPES[expected]);
    }
    assert.equal(switchState(from,to,SWITCH_AT-1e-6).focus,from);
    assert.equal(switchState(from,to,SWITCH_AT).focus,to);
    close(switchState(from,to,SWITCH_AT).flash,1);
    close(switchState(from,to,TRANSITION).flash,0);
  }
});
test('the automatic cycle closes, and a fixed form does not change while time advances',()=>{
  assert.deepEqual(boxesAt(0),boxesAt(PERIOD));
  assert.deepEqual(boxesAt(-1e-6).boxes,boxesAt(0).boxes);
  for(const f of FORMS)assert.deepEqual(boxesAt(0,f),boxesAt(999,f));
});
test('startup fills existing glyph locations monotonically and finishes fully revealed',()=>{
  let early=0;
  for(let i=0;i<1000;i++){
    const seed=i/1000;let previous=0;
    if(revealAt(0,seed,1)>0)early++;
    for(let n=0;n<=20;n++){const value=revealAt(n/20*BOOT,seed,.65);assert.ok(value>=previous);previous=value;}
    close(previous,1);
  }
  assert.ok(early>0&&early<25);
});
test('one base hue generates a bounded darker shadow and a lighter highlight',()=>{
  for(const hex of ['#63e688','#81d9fa','#ff79bd','#000000','#ffffff']){
    const p=paletteRamp(hex);
    for(let i=0;i<3;i++){assert.ok(p.shadow[i]<=p.base[i]);assert.ok(p.highlight[i]>=p.base[i]);assert.ok(p.highlight[i]<=1);}
  }
});
test('yaw and pitch preserve dimensions and change the perspective in both axes',()=>{
  const v=[1,2,3],a=cameraRotate(v,.3,.16);close(Math.hypot(...a),Math.hypot(...v));
  assert.notDeepEqual(a,cameraRotate(v,-.3,.16));assert.notDeepEqual(a,cameraRotate(v,.3,-.16));
  const box={center:[0,0,0],half:[.6,.6,.6],kind:0,rotation:[0,0,0,1]};
  assert.ok(traceBoxes(0,0,[box],.2,.1));assert.equal(traceBoxes(9,9,SHAPES.frames),null);
});
test('rounded tiers use analytic cylinders with continuous side normals, not box segments',()=>{
  const tiers=SHAPES.tiers.filter(b=>b.half[0]>0);assert.equal(tiers.length,3);assert.ok(tiers.every(b=>b.kind===1));
  const cylinder={center:[0,0,0],half:[.9,.2,.9],kind:1,rotation:[0,0,0,1]};
  const samples=[-.3,-.15,0,.15,.3].map(x=>traceBoxes(x,.65,[cylinder]));
  assert.ok(samples.every(Boolean));
  for(const h of samples){close(Math.hypot(...h.normal),1);assert.ok(Math.abs(h.normal[0])>.1&&Math.abs(h.normal[2])>.1);}
  for(let i=1;i<samples.length;i++){const change=Math.hypot(...samples[i].normal.map((v,k)=>v-samples[i-1].normal[k]));assert.ok(change>0&&change<.25);}
});
