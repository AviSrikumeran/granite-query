import {BOOT,pointerPose} from './engine/geometry.mjs?v=reveal-20261103-1';
import {makeGPU,makeCPU} from './engine/renderer.mjs?v=reveal-20261103-1';
import {makeAtlas} from './engine/atlas.mjs?v=reveal-20261103-1';
import {STAGES,PERIOD,revealAt,sequenceAt,layoutFor} from './forms.mjs?v=reveal-20261103-1';

const review=new URLSearchParams(location.search),reduced=matchMedia('(prefers-reduced-motion: reduce)');
const figure=document.querySelector('figure'),pause=document.querySelector('#pause'),scrub=document.querySelector('#progress');
const status=document.querySelector('#motion-status'),caption=document.querySelector('#stage-description'),label=document.querySelector('#stage-label');
let canvas=figure.querySelector('canvas'),renderer,layout,width=0,height=0,ratio=1,lost=false,inView=true;
let time=0,paused=reduced.matches,manual=reduced.matches ? .61 : null,bootSkipped=reduced.matches,visible=!document.hidden;
let previous=0,lastPaint=0,request=0,dirty=true,lastStage='';
const pointer={strength:0,turn:0,tilt:0},target={...pointer};
const sample=Number(review.get('progress'));
if(review.has('progress')&&Number.isFinite(sample)){manual=Math.max(0,Math.min(1,sample));paused=true;bootSkipped=true;time=4;}
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
function cellsFor(pitch){
  const cells=[],[cx,cy]=layout.center,firstRow=Math.ceil(-cy/pitch);
  for(let row=firstRow,y=cy+row*pitch;y<height;row++,y=cy+row*pitch){
    const stagger=row%2?.75:.25,firstCol=Math.ceil(-cx/pitch-stagger);
    for(let col=firstCol,x=cx+(col+stagger)*pitch;x<width;col++,x=cx+(col+stagger)*pitch)cells.push(x,y);
  }
  return new Float32Array(cells);
}
const options={get:()=>({width,height,ratio,layout,pointer,time,bootSkipped,color:'#ff63ed',material:'magenta',ghosts:false}),makeCells:cellsFor,makeAtlas,hash};
function createRenderer(){
  renderer=null;
  try{if(review.get('renderer')!=='canvas')renderer=makeGPU(canvas,options);}catch(error){console.warn('Using the simplified renderer:',error.message);}
  if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeCPU(canvas,options);}
  canvas.dataset.renderer=renderer.type;
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;updateStatus();});
  canvas.addEventListener('webglcontextrestored',()=>{createRenderer();lost=false;resize();dirty=true;schedule();updateStatus();},{once:true});
}
function resize(){
  const rect=figure.getBoundingClientRect();if(rect.width<1||rect.height<1)return;
  width=rect.width;height=rect.height;ratio=Math.min(1.5,devicePixelRatio||1);layout=layoutFor(width,height);
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);if(!lost)renderer.resize();dirty=true;schedule();
}
function setTarget(value){Object.assign(target,value);if(reduced.matches)Object.assign(pointer,target);dirty=true;schedule();}
figure.addEventListener('pointermove',event=>{
  if(event.pointerType==='touch'||reduced.matches)return;
  const rect=figure.getBoundingClientRect();setTarget({...pointerPose(event.clientX-rect.left,event.clientY-rect.top,rect.width,rect.height),strength:1});
});
figure.addEventListener('pointerleave',()=>setTarget({turn:0,tilt:0,strength:0}));
figure.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return;
  event.preventDefault();const value={...target,strength:1};
  if(event.key==='Home')Object.assign(value,{turn:0,tilt:0,strength:0});
  if(event.key==='ArrowLeft')value.turn-=.025;if(event.key==='ArrowRight')value.turn+=.025;
  if(event.key==='ArrowUp')value.tilt-=.018;if(event.key==='ArrowDown')value.tilt+=.018;
  value.turn=Math.max(-.105,Math.min(.105,value.turn));value.tilt=Math.max(-.065,Math.min(.065,value.tilt));setTarget(value);
});
function schedule(){if(!request&&visible&&inView)request=requestAnimationFrame(tick);}
function tick(now){
  request=0;if(!visible||!inView){previous=0;return;}
  const delta=previous?Math.min(.06,Math.max(0,(now-previous)/1000)):0;previous=now;if(!paused)time+=delta;
  const response=1-Math.exp(-delta*7.5);let changing=false;
  for(const key of ['turn','tilt','strength']){pointer[key]+=(target[key]-pointer[key])*response;if(Math.abs(target[key]-pointer[key])>.0001)changing=true;}
  if(dirty||now-lastPaint>=(renderer.type==='WebGL'?33:85)){
    const scene=revealAt(manual??sequenceAt(Math.max(0,time-BOOT)));
    if(layout&&!lost){renderer.draw({...scene,turn:pointer.turn,tilt:pointer.tilt});Object.assign(canvas.dataset,{time:time.toFixed(3),progress:scene.progress.toFixed(3),stage:scene.stage.id,turn:pointer.turn.toFixed(4),tilt:pointer.tilt.toFixed(4),paused:String(paused)});}
    scrub.value=String(Math.round(scene.progress*1000));scrub.setAttribute('aria-valuetext',`${Math.round(scene.progress*100)} percent, ${scene.stage.label}`);
    for(const button of document.querySelectorAll('button[data-stage]'))button.setAttribute('aria-pressed',String(paused&&manual!==null&&Math.abs(manual-STAGES.find(s=>s.id===button.dataset.stage).progress)<.0001));
    if(lastStage!==scene.stage.id){lastStage=scene.stage.id;caption.textContent=scene.stage.description;label.textContent=scene.stage.label;}
    dirty=false;lastPaint=now;
  }
  if(!paused||changing)schedule();else previous=0;
}
function updateStatus(){
  pause.textContent=paused?'Play':'Pause';pause.setAttribute('aria-pressed',String(paused));
  status.textContent=(paused?(reduced.matches?'Reduced motion: automatic playback is off. Choose Play to opt in.':'Paused. Choose a pose or scrub to inspect.'):'Playing · Select, unlock, reveal, return.')+(lost?' Graphics paused; waiting for the renderer to recover.':renderer.type!=='WebGL'?' Simplified canvas rendering is active.':'');
}
function setPaused(value){paused=value;previous=0;dirty=true;updateStatus();schedule();}
function hold(progress){manual=progress;bootSkipped=true;setPaused(true);}
pause.addEventListener('click',()=>{if(paused){if(manual!==null){time=BOOT+manual*PERIOD;manual=null;}bootSkipped=true;}setPaused(!paused);});
document.querySelector('#replay').addEventListener('click',()=>{time=0;manual=reduced.matches?0:null;bootSkipped=reduced.matches;lastStage='';Object.assign(target,{turn:0,tilt:0,strength:0});Object.assign(pointer,target);setPaused(reduced.matches);});
scrub.addEventListener('input',()=>hold(Number(scrub.value)/1000));
for(const button of document.querySelectorAll('button[data-stage]'))button.addEventListener('click',()=>hold(STAGES.find(stage=>stage.id===button.dataset.stage).progress));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;if(!visible&&request){cancelAnimationFrame(request);request=0;}schedule();});
reduced.addEventListener('change',event=>{if(event.matches){Object.assign(target,{turn:0,tilt:0,strength:0});Object.assign(pointer,target);hold(.61);}});
createRenderer();new ResizeObserver(resize).observe(figure);
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;if(inView)dirty=true;schedule();}).observe(figure);
resize();updateStatus();schedule();
