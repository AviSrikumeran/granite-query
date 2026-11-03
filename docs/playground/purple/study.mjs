import {BOOT,smooth,pointerPose} from './engine/geometry.mjs?v=magenta-20261103-2';
import {makeGPU,makeCPU} from './engine/renderer.mjs?v=magenta-20261103-2';
import {makeAtlas} from './engine/atlas.mjs?v=magenta-20261103-2';
import {DIRECTIONS,POSES,STEP,FORMATIONS,formationAt,blendParts,transition,layoutFor} from './forms.mjs?v=magenta-20261103-2';

const reduced=matchMedia('(prefers-reduced-motion: reduce)'),review=new URLSearchParams(location.search);
const pauseButton=document.querySelector('#pause'),poseControl=document.querySelector('#pose'),linkedControl=document.querySelector('#linked'),peripheralControl=document.querySelector('#peripherals'),status=document.querySelector('#motion-status');
const comparison=document.querySelector('#comparison');
const spacingControl=document.querySelector('#spacing'),materialControl=document.querySelector('#material');
let spacing=review.get('spacing')==='reference'?'reference':'clear',activeMaterial=['hotviolet','violet'].includes(review.get('material'))?'hotviolet':'magenta';
let paused=reduced.matches,time=0,previous=0,lastPaint=0,request=0,dirty=true,mode='auto',offset=0,manual=null,bootSkipped=reduced.matches;
let visible=!document.hidden,linked=true,ghosts=false;
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
const title=s=>s[0].toUpperCase()+s.slice(1);

function cellsFor(layout,pitch){
  const cells=[],[cx,cy]=layout.center,firstRow=Math.ceil((layout.top-cy)/pitch);
  for(let row=firstRow,y=cy+row*pitch;y<layout.bottom;row++,y=cy+row*pitch){
    const stagger=row%2?.75:.25,firstCol=Math.ceil((layout.left-cx)/pitch-stagger);
    for(let col=firstCol,x=cx+(col+stagger)*pitch;x<layout.right;col++,x=cx+(col+stagger)*pitch)cells.push(x,y);
  }
  return new Float32Array(cells);
}
function clockScenes(){
  if(manual){
    const state=transition(manual.from,manual.target,time-manual.started);
    if(state.transitioning)return Object.fromEntries(DIRECTIONS.map(id=>[id,{state,boxes:blendParts(manual.parts[id],FORMATIONS[spacing][manual.target],state.blend)}]));
    if(mode==='auto')offset=POSES.indexOf(manual.target)*STEP-Math.max(0,time-BOOT);
    manual=null;
  }
  return Object.fromEntries(DIRECTIONS.map(id=>[id,formationAt(id,time,mode,offset,spacing)]));
}
class View {
  constructor(id){
    this.id=id;this.element=document.querySelector(`[data-direction="${id}"]`);this.figure=this.element.querySelector('figure');this.canvas=this.element.querySelector('canvas');this.caption=this.element.querySelector('.pose-name');
    this.width=0;this.height=0;this.ratio=1;this.layout=null;this.inView=true;this.lost=false;
    this.pointer={x:-2000,y:-2000,strength:0,turn:0,tilt:0};this.target={strength:0,turn:0,tilt:0};
    this.options={get:()=>({width:this.width,height:this.height,ratio:this.ratio,layout:this.layout,pointer:this.pointer,time,bootSkipped,color:'#7fee64',material:this.id==='green'?'green':activeMaterial,ghosts}),makeCells:pitch=>cellsFor(this.layout,pitch),makeAtlas,hash};
    this.createRenderer();
    this.figure.addEventListener('pointermove',event=>{
      if(event.pointerType==='touch')return;
      const rect=this.figure.getBoundingClientRect(),pose=pointerPose(event.clientX-rect.left,event.clientY-rect.top,rect.width,rect.height);
      for(const view of views)if(linked||view===this)view.setTarget({...pose,strength:1});
    });
    this.figure.addEventListener('pointerleave',()=>{for(const view of views)if(linked||view===this)view.setTarget({turn:0,tilt:0,strength:0});});
    this.figure.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return;event.preventDefault();
      const target={...this.target,strength:1};
      if(event.key==='Home')Object.assign(target,{turn:0,tilt:0,strength:0});
      if(event.key==='ArrowLeft')target.turn-=.025;if(event.key==='ArrowRight')target.turn+=.025;
      if(event.key==='ArrowUp')target.tilt-=.018;if(event.key==='ArrowDown')target.tilt+=.018;
      target.turn=Math.max(-.105,Math.min(.105,target.turn));target.tilt=Math.max(-.065,Math.min(.065,target.tilt));
      for(const view of views)if(linked||view===this)view.setTarget(target);
    });
    new ResizeObserver(()=>{this.resize();schedule();}).observe(this.figure);
    new IntersectionObserver(entries=>{this.inView=entries[0].isIntersecting;if(this.inView)dirty=true;schedule();}).observe(this.figure);
  }
  createRenderer(){
    let renderer=null;
    try{if(review.get('renderer')!=='canvas')renderer=makeGPU(this.canvas,this.options);}catch(error){console.warn('Using the simplified renderer:',error.message);}
    if(!renderer){const replacement=this.canvas.cloneNode();this.canvas.replaceWith(replacement);this.canvas=replacement;renderer=makeCPU(this.canvas,this.options);}
    this.renderer=renderer;this.canvas.dataset.renderer=renderer.type;
    this.canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();this.lost=true;this.canvas.dataset.renderer='Context lost';updateStatus();});
    this.canvas.addEventListener('webglcontextrestored',()=>{this.lost=false;this.renderer=makeGPU(this.canvas,this.options);this.canvas.dataset.renderer=this.renderer.type;this.resize();dirty=true;schedule();updateStatus();});
  }
  resize(){
    const rect=this.figure.getBoundingClientRect();if(rect.width<1||rect.height<1)return;
    this.width=rect.width;this.height=rect.height;this.ratio=Math.min(1.5,devicePixelRatio||1);this.layout=layoutFor(this.width,this.height);
    this.canvas.width=Math.round(this.width*this.ratio);this.canvas.height=Math.round(this.height*this.ratio);if(!this.lost)this.renderer.resize();dirty=true;
  }
  setTarget(target){
    Object.assign(this.target,target);if(reduced.matches)Object.assign(this.pointer,this.target);dirty=true;schedule();
  }
  advance(delta){
    const response=reduced.matches?1:1-Math.exp(-delta*7.5);let changing=false;
    for(const key of ['turn','tilt','strength']){this.pointer[key]+=(this.target[key]-this.pointer[key])*response;if(Math.abs(this.target[key]-this.pointer[key])>.0001)changing=true;}
    return changing;
  }
  draw(scene){
    if(this.lost||!this.layout||!this.inView)return;
    this.renderer.draw({...scene,turn:this.pointer.turn,tilt:this.pointer.tilt});this.caption.textContent=title(scene.state.focus);
    Object.assign(this.canvas.dataset,{direction:this.id,time:time.toFixed(3),pose:scene.state.focus,blend:scene.state.blend.toFixed(3),flash:scene.state.flash.toFixed(3),turn:this.pointer.turn.toFixed(4),tilt:this.pointer.tilt.toFixed(4),paused:String(paused),ghosts:String(ghosts),spacing,material:this.id==='green'?'green':activeMaterial});
  }
}
const views=DIRECTIONS.map(id=>new View(id));
function schedule(){if(!request&&visible&&views.some(view=>view.inView))request=requestAnimationFrame(tick);}
function tick(now){
  request=0;if(!visible||!views.some(view=>view.inView)){previous=0;return;}
  const delta=previous?Math.min(.06,Math.max(0,(now-previous)/1000)):0;previous=now;
  if(!paused)time+=delta;
  let changing=false;for(const view of views)changing=view.advance(delta)||changing;
  const interval=views.some(view=>view.renderer.type!=='WebGL')?80:25;
  if(dirty||now-lastPaint>=interval){const scenes=clockScenes();for(const view of views)view.draw(scenes[view.id]);dirty=false;lastPaint=now;}
  if(!paused||changing)schedule();else previous=0;
}
function updateStatus(){
  const simple=views.some(view=>view.renderer.type!=='WebGL'||view.lost);
  status.textContent=(paused?(reduced.matches?'Reduced motion: poses are held.':'Motion paused. Mouse and keyboard inspection are available.'):'Motion is playing. Both materials share one clock.')+(simple?' A simplified view is active on this device.':'');
  pauseButton.textContent=paused?'Play':'Pause';pauseButton.setAttribute('aria-pressed',String(paused));
}
function setPaused(value){paused=value;previous=0;dirty=true;updateStatus();schedule();}
pauseButton.addEventListener('click',()=>{if(paused)bootSkipped=true;setPaused(!paused);});
document.querySelector('#replay').addEventListener('click',()=>{
  time=0;offset=0;manual=null;mode='auto';poseControl.value='auto';bootSkipped=reduced.matches;
  for(const view of views){Object.assign(view.target,{strength:0,turn:0,tilt:0});Object.assign(view.pointer,view.target);}
  setPaused(reduced.matches);
});
poseControl.addEventListener('change',()=>{
  const source=clockScenes(),target=poseControl.value==='auto'?source.green.state.focus:poseControl.value;
  mode=poseControl.value;bootSkipped=true;
  if(paused||reduced.matches){manual=null;if(mode==='auto')offset=POSES.indexOf(target)*STEP-Math.max(0,time-BOOT);}
  else manual={from:source.green.state.focus,target,started:time,parts:Object.fromEntries(DIRECTIONS.map(id=>[id,source[id].boxes]))};
  dirty=true;schedule();
});
linkedControl.addEventListener('change',()=>{linked=linkedControl.checked;for(const view of views)view.setTarget({strength:0,turn:0,tilt:0});});
peripheralControl.addEventListener('change',()=>{ghosts=peripheralControl.checked;dirty=true;schedule();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;schedule();});
reduced.addEventListener('change',event=>{if(event.matches){bootSkipped=true;for(const view of views){Object.assign(view.target,{strength:0,turn:0,tilt:0});Object.assign(view.pointer,view.target);}setPaused(true);}});
const reviewTime=Number(review.get('at'));
if(review.has('at')&&Number.isFinite(reviewTime)){time=Math.max(0,reviewTime);paused=true;bootSkipped=!review.has('intro');}
if(POSES.includes(review.get('pose'))){mode=review.get('pose');poseControl.value=mode;}
if(review.get('ghosts')==='1'){ghosts=true;peripheralControl.checked=true;}
function updateMaterialLabel(){document.querySelector('#purple-title').textContent=activeMaterial==='hotviolet'?'Hot violet':'Electric magenta';}
spacingControl.value=spacing;materialControl.value=activeMaterial;updateMaterialLabel();
spacingControl.addEventListener('change',()=>{spacing=spacingControl.value;manual=null;dirty=true;schedule();});
materialControl.addEventListener('change',()=>{activeMaterial=materialControl.value;updateMaterialLabel();dirty=true;schedule();});
for(const view of views)view.resize();updateStatus();schedule();
