import test from 'node:test';
import assert from 'node:assert/strict';
import {FORMS,SHAPES,BOX_COUNT,BOOT,HOLD,TRANSITION,MORPH_START,MORPH_END,STEP,PERIOD,boxesAt,switchState,mixBoxes,revealAt,startupFlare,highlightFlare,paletteRamp,pointerPose,surfaceLight,cameraRotate,traceBoxes} from '../docs/playground/granite/geometry.mjs';
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
test('geometry holds through the flare and reshapes only within the brief recorded-style window',()=>{
  for(let i=0;i<FORMS.length;i++){
    const from=FORMS[i],to=FORMS[(i+1)%FORMS.length];
    assert.deepEqual(boxesAt(i*STEP+HOLD+MORPH_START).boxes,SHAPES[from]);
    assert.deepEqual(boxesAt(i*STEP+HOLD+MORPH_END+1e-8).boxes,SHAPES[to]);
    const middle=boxesAt(i*STEP+HOLD+(MORPH_START+MORPH_END)/2).boxes;
    assert.notDeepEqual(middle,SHAPES[from]);assert.notDeepEqual(middle,SHAPES[to]);
    for(let n=0;n<=100;n++){
      const elapsed=n/100*TRANSITION,scene=boxesAt(i*STEP+HOLD+elapsed);
      for(const b of scene.boxes){assert.ok([...b.center,...b.half,...b.rotation].every(Number.isFinite));assert.ok(b.half.every(v=>v>=0&&v<=1.1));assert.ok(b.center.every(v=>Math.abs(v)<=1.1));}
    }
    assert.equal(switchState(from,to,MORPH_START-1e-6).phase,'flare');
    assert.equal(switchState(from,to,(MORPH_START+MORPH_END)/2).phase,'reshape');
    assert.ok(switchState(from,to,MORPH_START).flash>.8);
    close(switchState(from,to,TRANSITION).flash,0);
  }
  close(MORPH_END-MORPH_START,.2);
  close(STEP,5);
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
  close(revealAt(.9,.5,1,.3),0);
  assert.ok(revealAt(1.08,.5,1,.3)>revealAt(1.08,.5,1,1.8));
  close(startupFlare(.9),0);assert.ok(startupFlare(1.12)>.9);close(startupFlare(BOOT),0);
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
  assert.deepEqual(pointerPose(640,400,1280,800),{turn:0,tilt:0});
  const left=pointerPose(0,0,1280,800),right=pointerPose(1280,800,1280,800);
  close(left.turn,-right.turn);close(left.tilt,-right.tilt);assert.ok(Math.abs(left.turn)<.11);assert.ok(Math.abs(left.tilt)<.07);
});
test('rounded tiers use analytic cylinders with continuous side normals, not box segments',()=>{
  const tiers=SHAPES.tiers.filter(b=>b.half[0]>0);assert.equal(tiers.length,3);assert.ok(tiers.every(b=>b.kind===1));
  const cylinder={center:[0,0,0],half:[.9,.2,.9],kind:1,rotation:[0,0,0,1]};
  const samples=[-.3,-.15,0,.15,.3].map(x=>traceBoxes(x,.65,[cylinder]));
  assert.ok(samples.every(Boolean));
  for(const h of samples){close(Math.hypot(...h.normal),1);assert.ok(Math.abs(h.normal[0])>.1&&Math.abs(h.normal[2])>.1);}
  for(let i=1;i<samples.length;i++){const change=Math.hypot(...samples[i].normal.map((v,k)=>v-samples[i-1].normal[k]));assert.ok(change>0&&change<.25);}
});
test('a new manual target can start at the displayed geometry without a position reset',()=>{
  const displayed=boxesAt(HOLD+(MORPH_START+MORPH_END)/2).boxes;
  assert.deepEqual(mixBoxes(displayed,SHAPES.tiers,0),displayed);
  assert.deepEqual(mixBoxes(displayed,SHAPES.tiers,1),SHAPES.tiers);
});
test('surface highlights travel with time even when the geometry and mouse remain fixed',()=>{
  const values=Array.from({length:40},(_,i)=>surfaceLight([0,0,1],[.3,.2,.6],.2,i*.15));
  assert.ok(Math.max(...values)-Math.min(...values)>.2);
  assert.ok(values.every(v=>v>=0&&v<1.2));
});
