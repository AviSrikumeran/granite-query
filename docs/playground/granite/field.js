import {FORMS,FORM_LABELS,BOOT,STEP,MORPH_START,MORPH_END,SHAPES,layoutFor,sceneBounds,boxesAt,switchState,mixBoxes,pointerPose,paletteRamp,smooth} from './geometry.mjs?v=lighting-20261103-5';
import {makeGPU,makeCPU} from './renderer.mjs?v=lighting-20261103-5';

// Reconstruct the supplied reference's formations, scale and reflected fragments.
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
let canvas=document.querySelector('#glyph-field');
const hero=document.querySelector('.hero'),pauseButton=document.querySelector('#pause-motion'),formControl=document.querySelector('#form-mode');
const formName=document.querySelector('#form-name'),status=document.querySelector('#motion-status');
const DEFAULT_COLOR='#7fee64';
let color=DEFAULT_COLOR,ramp=paletteRamp(color);
let width=0,height=0,ratio=1,time=0,previous=0,request=0,frames=0;
let paused=reducedMotion.matches,visible=!document.hidden,inView=true,mode='auto',sequenceOffset=0,manual=null,bootSkipped=reducedMotion.matches;
let renderer,layout;
const pointer={x:-2000,y:-2000,strength:0,turn:0,tilt:0};
const rgb=values=>'rgb('+values.map(v=>Math.round(v*255)).join(',')+')';
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
function makeCells(pitch){
  const cells=[],[cx,cy]=layout.center,firstRow=Math.ceil((layout.top-cy)/pitch);
  for(let row=firstRow,y=cy+row*pitch;y<layout.bottom;row++,y=cy+row*pitch){
    const offset=row%2?.75:.25,firstCol=Math.ceil((layout.left-cx)/pitch-offset);
    for(let col=firstCol,x=cx+(col+offset)*pitch;x<layout.right;col++,x=cx+(col+offset)*pitch)cells.push(x,y);
  }
  return new Float32Array(cells);
}

function makeAtlas(color='#fff'){
  const image=document.createElement('canvas');image.width=1024;image.height=64;
  const ctx=image.getContext('2d');ctx.fillStyle=color;ctx.strokeStyle=color;
  for(let kind=0;kind<16;kind++){
    ctx.save();ctx.translate(kind*64+32,32);ctx.lineWidth=7;ctx.lineCap='round';ctx.lineJoin='round';
    if(kind===0||kind===13){ctx.beginPath();ctx.arc(0,0,22,0,Math.PI*2);kind===0?ctx.fill():ctx.stroke();if(kind===13){ctx.beginPath();ctx.arc(0,0,6,0,Math.PI*2);ctx.fill();}}
    if(kind===1){ctx.beginPath();ctx.moveTo(0,22);ctx.bezierCurveTo(-36,-1,-19,-31,0,-12);ctx.bezierCurveTo(19,-31,36,-1,0,22);ctx.fill();}
    if(kind===7||kind===12){ctx.beginPath();const n=kind===2?6:kind===12?4:5;for(let k=0;k<n*2;k++){const a=k*Math.PI/n-Math.PI/2,r=k%2?11:24;ctx[k?'lineTo':'moveTo'](r*Math.cos(a),r*Math.sin(a));}ctx.closePath();kind===12?ctx.stroke():ctx.fill();}
    if(kind===3){ctx.fillRect(-3,-22,6,44);ctx.fillRect(-22,-3,44,6);}
    if(kind===4){ctx.beginPath();ctx.moveTo(-19,-19);ctx.lineTo(0,0);ctx.lineTo(19,-19);ctx.moveTo(0,0);ctx.lineTo(0,22);ctx.stroke();}
    if(kind===5||kind===11){const sign=kind===5?1:-1;ctx.beginPath();ctx.moveTo(0,-22*sign);ctx.lineTo(23,19*sign);ctx.lineTo(-23,19*sign);ctx.closePath();ctx.fill();}
    if(kind===2){ctx.beginPath();for(let k=0;k<3;k++){const a=k*Math.PI/3;ctx.moveTo(-23*Math.cos(a),-23*Math.sin(a));ctx.lineTo(23*Math.cos(a),23*Math.sin(a));}ctx.stroke();}
    if(kind===6){ctx.beginPath();for(let k=0;k<3;k++){const a=k*2*Math.PI/3-Math.PI/2,b=a+Math.PI/3,c=a-Math.PI/3;ctx.moveTo(22*Math.cos(b),22*Math.sin(b));ctx.lineTo(25*Math.cos(a),25*Math.sin(a));ctx.lineTo(22*Math.cos(c),22*Math.sin(c));}ctx.stroke();}
    if(kind===8){ctx.beginPath();for(let k=0;k<6;k++){const a=k*Math.PI/3-Math.PI/2;ctx[k?'lineTo':'moveTo'](24*Math.cos(a),24*Math.sin(a));}ctx.closePath();ctx.fill();ctx.globalCompositeOperation='destination-out';ctx.beginPath();for(let k=0;k<3;k++){const a=k*2*Math.PI/3+Math.PI/2;ctx.moveTo(0,0);ctx.lineTo(26*Math.cos(a),26*Math.sin(a));}ctx.lineWidth=5;ctx.stroke();ctx.globalCompositeOperation='source-over';}
    if(kind===9){ctx.beginPath();for(let k=0;k<6;k++){const a=k*Math.PI/3-Math.PI/2;ctx[k?'lineTo':'moveTo'](24*Math.cos(a),24*Math.sin(a));}ctx.closePath();ctx.fill();}
    if(kind===10){ctx.beginPath();ctx.moveTo(-17,-17);ctx.lineTo(17,17);ctx.moveTo(-17,17);ctx.lineTo(17,-17);ctx.stroke();}
    if(kind===14)for(const y of [-14,0,14])ctx.fillRect(-20,y-2,40,4);
    if(kind===15){ctx.beginPath();ctx.moveTo(-20,8);ctx.lineTo(0,-12);ctx.lineTo(20,8);ctx.stroke();}
    ctx.restore();
  }
  return image;
}

const renderOptions={get:()=>({layout,width,height,ratio,time,pointer,bootSkipped,color}),makeCells,makeAtlas,hash};
const makeWebGL=()=>makeGPU(canvas,renderOptions),makeFallback=()=>makeCPU(canvas,renderOptions);

function sceneAtClock(){
  if(manual){
    const state=switchState(manual.from,manual.target,time-manual.started);
    const blend=smooth(manual.geometryStarted,manual.geometryStarted+MORPH_END-MORPH_START,time);
    if(state.transitioning||blend<1){state.blend=blend;state.focus=blend<.5?manual.from:manual.target;state.transitioning=true;if(time>=manual.geometryStarted&&blend<1)state.phase='reshape';return {state,boxes:mixBoxes(manual.boxes,SHAPES[manual.target],blend)};}
    if(mode==='auto')sequenceOffset=FORMS.indexOf(manual.target)*STEP-Math.max(0,time-BOOT);
    manual=null;
  }
  return boxesAt(Math.max(0,time-BOOT)+sequenceOffset,mode);
}
function draw(){
  const scene=sceneAtClock();scene.turn=pointer.turn;scene.tilt=pointer.tilt;scene.bounds=sceneBounds(scene.boxes);renderer.draw(scene);frames++;
  formName.textContent=FORM_LABELS[scene.state.focus];
  Object.assign(canvas.dataset,{form:scene.state.focus,time:time.toFixed(3),frame:String(frames),transitioning:String(scene.state.transitioning),phase:scene.state.phase,blend:scene.state.blend.toFixed(3),flash:scene.state.flash.toFixed(3),reveal:(bootSkipped?BOOT:Math.min(BOOT,time)).toFixed(3),turn:scene.turn.toFixed(4),tilt:scene.tilt.toFixed(4),echoCount:'3',unit:layout.unit.toFixed(2)});
}
function tick(now){
  request=0;if(paused||!visible||!inView){previous=0;return;}
  const delta=previous?Math.min(.06,Math.max(0,(now-previous)/1000)):0;time+=delta;previous=now;
  const response=1-Math.exp(-delta*7.5),active=pointer.x>-1000;
  const {turn,tilt}=pointerPose(pointer.x,pointer.y,width,height,active);
  pointer.strength+=((active?1:0)-pointer.strength)*response;pointer.turn+=(turn-pointer.turn)*response;pointer.tilt+=(tilt-pointer.tilt)*response;
  draw();request=requestAnimationFrame(tick);
}
function schedule(){if(!request&&!paused&&visible&&inView)request=requestAnimationFrame(tick);}
function setPaused(value){paused=value;previous=0;if(request)cancelAnimationFrame(request);request=0;canvas.dataset.paused=String(paused);pauseButton.setAttribute('aria-pressed',String(paused));pauseButton.textContent=paused?'Resume':'Pause';status.textContent=paused?'Animation paused. Choose a form to inspect it.':'Animation playing.';schedule();}
function resize(){
  const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;ratio=Math.min(2,Math.max(1.5,devicePixelRatio||1));
  layout=layoutFor(width,height);
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);renderer.resize();draw();schedule();
}
function changeForm(requested,targetForm){
  const source=sceneAtClock(),target=targetForm||(requested==='auto'?source.state.focus:requested);
  mode=requested;formControl.value=mode;bootSkipped=true;
  if(paused||(!source.state.transitioning&&source.state.focus===target)){manual=null;if(mode==='auto')sequenceOffset=FORMS.indexOf(target)*STEP-Math.max(0,time-BOOT);}
  else if(manual){manual.boxes=source.boxes;manual.from=source.state.focus;manual.target=target;manual.geometryStarted=time;} // Keep the existing flare clock.
  else manual={boxes:source.boxes,from:source.state.focus,target,started:time,geometryStarted:time+MORPH_START};
  draw();schedule();
}
function setColor(value){
  if(!/^#[0-9a-f]{6}$/i.test(value))return false;
  color=value.toLowerCase();ramp=paletteRamp(color);
  document.documentElement.style.setProperty('--accent',color);document.documentElement.style.setProperty('--highlight',rgb(ramp.highlight));
  document.querySelector('#base-color').value=color;document.querySelector('#base-hex').value=color.toUpperCase();document.querySelector('#base-hex').removeAttribute('aria-invalid');
  canvas.dataset.color=color;draw();return true;
}
try{if(new URLSearchParams(location.search).get('renderer')!=='canvas')renderer=makeWebGL();}catch(error){console.warn('WebGL unavailable; using Canvas 2D:',error.message);}
if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeFallback();}
canvas.dataset.renderer=renderer.type;canvas.dataset.color=color;
hero.addEventListener('pointermove',event=>{if(event.pointerType==='touch')return;const rect=hero.getBoundingClientRect();pointer.x=event.clientX-rect.left;pointer.y=event.clientY-rect.top;canvas.dataset.interaction='pointer';});
hero.addEventListener('pointerleave',()=>{pointer.x=-2000;pointer.y=-2000;});
canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();if(request)cancelAnimationFrame(request);request=0;canvas.dataset.renderer='context lost';});
canvas.addEventListener('webglcontextrestored',()=>{renderer=makeWebGL();canvas.dataset.renderer=renderer.type;resize();});
pauseButton.addEventListener('click',()=>setPaused(!paused));
formControl.addEventListener('change',()=>changeForm(formControl.value));
document.querySelector('#reset-motion').addEventListener('click',()=>{time=0;previous=0;sequenceOffset=0;manual=null;mode='auto';bootSkipped=reducedMotion.matches;formControl.value='auto';Object.assign(pointer,{x:-2000,y:-2000,strength:0,turn:0,tilt:0});setPaused(reducedMotion.matches);draw();});
const colorControl=document.querySelector('#base-color'),hexControl=document.querySelector('#base-hex');
colorControl.addEventListener('input',()=>setColor(colorControl.value));
hexControl.addEventListener('input',()=>{if(!setColor(hexControl.value))hexControl.setAttribute('aria-invalid','true');});
hexControl.addEventListener('blur',()=>{if(hexControl.getAttribute('aria-invalid')==='true'){hexControl.value=color.toUpperCase();hexControl.removeAttribute('aria-invalid');}});
document.querySelector('#reset-colors').addEventListener('click',()=>setColor(DEFAULT_COLOR));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;schedule();});
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;schedule();}).observe(canvas);
new ResizeObserver(resize).observe(canvas);
reducedMotion.addEventListener('change',event=>{if(event.matches){bootSkipped=true;setPaused(true);draw();}});
const review=new URLSearchParams(location.search),reviewTime=Number(review.get('at'));
if(review.has('at')&&Number.isFinite(reviewTime)){time=Math.max(0,reviewTime);bootSkipped=!review.has('intro');paused=true;if(FORMS.includes(review.get('form'))){mode=review.get('form');formControl.value=mode;}}
resize();setPaused(paused);
