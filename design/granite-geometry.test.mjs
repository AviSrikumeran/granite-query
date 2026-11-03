import test from 'node:test';
import assert from 'node:assert/strict';
import {FORMS,SHAPES,BOX_COUNT,BOOT,HOLD,TRANSITION,MORPH_START,MORPH_END,STEP,PERIOD,REFLECTIONS,layoutFor,sceneBounds,reflectionVisible,boxesAt,switchState,mixBoxes,revealAt,startupFlare,highlightFlare,paletteRamp,pointerPose,surfaceLight,cameraRotate,traceBoxes} from '../docs/playground/granite/geometry.mjs';
const close=(a,b,e=1e-8)=>assert.ok(Math.abs(a-b)<e,a+' != '+b);

test('the recorded sequence has twelve box edges, three plates, eight cubes and five stairs',()=>{
  assert.deepEqual(FORMS,['box','layers','cubes','stairs']);
  const counts={box:12,layers:3,cubes:8,stairs:5};
  for(const form of FORMS){
    assert.equal(SHAPES[form].length,BOX_COUNT);
    const active=SHAPES[form].filter(b=>b.half.every(v=>v>0));assert.equal(active.length,counts[form]);
    for(const b of active){assert.ok([...b.center,...b.half,...b.rotation].every(Number.isFinite));assert.ok(b.half.every(v=>v<=1.1));assert.ok(b.center.every(v=>Math.abs(v)<=1.1));}
  }
  const positions=SHAPES.cubes.filter(b=>b.half[0]>0).map(b=>JSON.stringify(b.center));assert.equal(new Set(positions).size,8);
});
test('compact desktop scale preserves a quarter-width main object and broad unused space',()=>{
  for(const w of [1280,1640]){
    const l=layoutFor(w,820),ratio=3.3*l.unit/w;
    assert.ok(ratio>.23&&ratio<.27);
    assert.ok(l.right-l.left<w*.6);assert.ok(l.top>=300);close(l.center[0],w/2);
  }
  for(const w of [390,600,682,900]){const l=layoutFor(w,750);assert.ok(l.left>=0&&l.right<=w);assert.ok(l.unit>=60&&l.unit<=100);}
  close(layoutFor(390,750).unit/layoutFor(390,750).pitch,layoutFor(1640,900).unit/layoutFor(1640,900).pitch);
});
test('the cage leaves substantial empty holes inside its envelope',()=>{
  const hull={...sceneBounds(SHAPES.box),rotation:[0,0,0,1],kind:0};
  let holes=0;
  for(let x=-1.5;x<=1.5;x+=.1)for(let y=-1.5;y<=1.5;y+=.1)if(traceBoxes(x,y,[hull])&&!traceBoxes(x,y,SHAPES.box))holes++;
  assert.ok(holes>150);
});
test('reflections expose different stair faces and are hidden inside the foreground envelope',()=>{
  const mirror=REFLECTIONS[0].mirror;let difference=0;
  for(let x=-1.8;x<1.8;x+=.12)for(let y=-1.8;y<1.8;y+=.12){
    if(Boolean(traceBoxes(x,y,SHAPES.stairs))!==Boolean(traceBoxes(x,y,SHAPES.stairs,0,0,0,mirror)))difference++;
  }
  assert.ok(difference>50);
  assert.equal(reflectionVisible(0,0,SHAPES.box),0);assert.equal(reflectionVisible(4,0,SHAPES.box),1);
  assert.ok(REFLECTIONS[2].strength<REFLECTIONS[0].strength/2);
  assert.equal(new Set(REFLECTIONS.map(r=>JSON.stringify(r.mirror))).size,3);
});
test('a highlight flare preserves dark areas and lifts already-bright areas',()=>{
  for(const light of [0,.1,.3,.48])close(highlightFlare(light,1),light);
  assert.ok(highlightFlare(.9,1)>.9);close(highlightFlare(.9,0),.9);
});
test('the five-second cycle has a brief bounded reshape rather than a long disassembly',()=>{
  for(let i=0;i<FORMS.length;i++){
    const from=FORMS[i],to=FORMS[(i+1)%FORMS.length];
    assert.deepEqual(boxesAt(i*STEP+HOLD+MORPH_START).boxes,SHAPES[from]);
    assert.deepEqual(boxesAt(i*STEP+HOLD+MORPH_END+1e-8).boxes,SHAPES[to]);
    const middle=boxesAt(i*STEP+HOLD+(MORPH_START+MORPH_END)/2).boxes;
    assert.notDeepEqual(middle,SHAPES[from]);assert.notDeepEqual(middle,SHAPES[to]);
    for(let n=0;n<=100;n++)for(const b of boxesAt(i*STEP+HOLD+n/100*TRANSITION).boxes){assert.ok([...b.center,...b.half].every(Number.isFinite));assert.ok(b.half.every(v=>v>=0&&v<=1.1));assert.ok(b.center.every(v=>Math.abs(v)<=1.1));}
    assert.ok(switchState(from,to,MORPH_START).flash>.8);close(switchState(from,to,TRANSITION).flash,0);
  }
  close(MORPH_END-MORPH_START,.2);close(STEP,5);
  assert.deepEqual(boxesAt(0),boxesAt(PERIOD));assert.deepEqual(boxesAt(-1e-6).boxes,boxesAt(0).boxes);
  for(const f of FORMS)assert.deepEqual(boxesAt(0,f),boxesAt(999,f));
});
test('startup holds sparse marks and then reveals the existing field from the center outward',()=>{
  let early=0;
  for(let i=0;i<1000;i++){
    const seed=i/1000;let previous=0;if(revealAt(0,seed,1)>0)early++;
    for(let n=0;n<=20;n++){const value=revealAt(n/20*BOOT,seed,.65);assert.ok(value>=previous);previous=value;}close(previous,1);
  }
  assert.ok(early>0&&early<25);close(revealAt(.9,.5,1,.3),0);
  assert.ok(revealAt(1.08,.5,1,.3)>revealAt(1.08,.5,1,1.8));
  close(startupFlare(.9),0);assert.ok(startupFlare(1.12)>.9);close(startupFlare(BOOT),0);
});
test('one hue produces bounded shadow and highlight values',()=>{
  for(const hex of ['#7fee64','#81d9fa','#ff79bd','#000000','#ffffff']){
    const p=paletteRamp(hex);for(let i=0;i<3;i++){assert.ok(p.shadow[i]<=p.base[i]);assert.ok(p.highlight[i]>=p.base[i]);assert.ok(p.highlight[i]<=1);}
  }
});
test('pointer pose is gentle, bounded and dimension preserving',()=>{
  const v=[1,2,3];close(Math.hypot(...cameraRotate(v,.1,.065)),Math.hypot(...v));
  assert.deepEqual(pointerPose(640,400,1280,800),{turn:0,tilt:0});
  const left=pointerPose(0,0,1280,800),right=pointerPose(1280,800,1280,800);
  close(left.turn,-right.turn);close(left.tilt,-right.tilt);assert.ok(Math.abs(left.turn)<.11);assert.ok(Math.abs(left.tilt)<.07);
});
test('retargeting can begin at the displayed geometry without a position reset',()=>{
  const displayed=boxesAt(HOLD+(MORPH_START+MORPH_END)/2).boxes;
  assert.deepEqual(mixBoxes(displayed,SHAPES.cubes,0),displayed);assert.deepEqual(mixBoxes(displayed,SHAPES.cubes,1),SHAPES.cubes);
});
test('surface illumination moves while geometry and mouse remain fixed',()=>{
  const values=Array.from({length:40},(_,i)=>surfaceLight([0,0,1],[.3,.2,.6],.2,i*.15));
  assert.ok(Math.max(...values)-Math.min(...values)>.2);assert.ok(values.every(v=>v>=0&&v<1.2));
});
