import {BOOT,pointerPose} from './engine/geometry.mjs?v=core-20261103-1';
import {makeGPU,makeCPU} from './engine/renderer.mjs?v=core-20261103-1';
import {makeAtlas} from './engine/atlas.mjs?v=core-20261103-1';
import {BASELINE,STAGES,extractionAt,sequenceAt,layoutFor} from './forms.mjs?v=core-20261103-1';

const review=new URLSearchParams(location.search),reduced=matchMedia('(prefers-reduced-motion: reduce)');
const pause=document.querySelector('#pause'),scrub=document.querySelector('#progress'),linkedControl=document.querySelector('#linked'),status=document.querySelector('#motion-status'),caption=document.querySelector('#stage-description');
let time=0,paused=reduced.matches,manual=reduced.matches?1:null,bootSkipped=reduced.matches,visible=!document.hidden,linked=true,previous=0,lastPaint=0,request=0,dirty=true,lastStage='';
const sample=Number(review.get('progress'));
if(review.has('progress')&&Number.isFinite(sample)){manual=Math.max(0,Math.min(1,sample));paused=true;bootSkipped=true;time=4;}
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
function cellsFor(layout,pitch){
  const cells=[],[cx,cy]=layout.center,firstRow=Math.ceil(-cy/pitch);
  for(let row=firstRow,y=cy+row*pitch;y<layout.bottom;row++,y=cy+row*pitch){
    const stagger=row%2?.75:.25,firstCol=Math.ceil(-cx/pitch-stagger);
    for(let col=firstCol,x=cx+(col+stagger)*pitch;x<layout.right;col++,x=cx+(col+stagger)*pitch)cells.push(x,y);
  }
  return new Float32Array(cells);
}
class View {
  constructor(id){
    this.id=id;this.element=document.querySelector(`[data-view="${id}"]`);this.figure=this.element.querySelector('figure');this.canvas=this.element.querySelector('canvas');this.inView=true;this.lost=false;this.layout=null;
    this.pointer={strength:0,turn:0,tilt:0};this.target={...this.pointer};
    this.options={get:()=>({width:this.width,height:this.height,ratio:this.ratio,layout:this.layout,pointer:this.pointer,time,bootSkipped,color:'#ff63ed',material:'magenta',ghosts:false}),makeCells:pitch=>cellsFor(this.layout,pitch),makeAtlas,hash};
    this.createRenderer();
    this.figure.addEventListener('pointermove',event=>{
      if(event.pointerType==='touch'||reduced.matches)return;
      const rect=this.figure.getBoundingClientRect(),pose=pointerPose(event.clientX-rect.left,event.clientY-rect.top,rect.width,rect.height);
      for(const view of views)if(linked||view===this)view.setTarget({...pose,strength:1});
    });
    this.figure.addEventListener('pointerleave',()=>{for(const view of views)if(linked||view===this)view.setTarget({turn:0,tilt:0,strength:0});});
    this.figure.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return;
      event.preventDefault();const target={...this.target,strength:1};
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
    this.canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();this.lost=true;updateStatus();});
    this.canvas.addEventListener('webglcontextrestored',()=>{this.createRenderer();this.lost=false;this.resize();dirty=true;schedule();updateStatus();},{once:true});
  }
  resize(){
    const rect=this.figure.getBoundingClientRect();if(rect.width<1||rect.height<1)return;
    this.width=rect.width;this.height=rect.height;this.ratio=Math.min(1.5,devicePixelRatio||1);this.layout=layoutFor(this.width,this.height);
    this.canvas.width=Math.round(this.width*this.ratio);this.canvas.height=Math.round(this.height*this.ratio);if(!this.lost)this.renderer.resize();dirty=true;
  }
  setTarget(target){Object.assign(this.target,target);if(reduced.matches)Object.assign(this.pointer,target);dirty=true;schedule();}
  advance(delta){
    const response=1-Math.exp(-delta*7.5);let changing=false;
    for(const key of ['turn','tilt','strength']){this.pointer[key]+=(this.target[key]-this.pointer[key])*response;if(Math.abs(this.target[key]-this.pointer[key])>.0001)changing=true;}
    return changing;
  }
  draw(scene){
    if(this.lost||!this.layout||!this.inView)return;
    this.renderer.draw({...scene,turn:this.pointer.turn,tilt:this.pointer.tilt});
    Object.assign(this.canvas.dataset,{time:time.toFixed(3),progress:scene.progress.toFixed(3),stage:scene.stage.id,turn:this.pointer.turn.toFixed(4),tilt:this.pointer.tilt.toFixed(4),paused:String(paused)});
  }
}
const views=['baseline','candidate'].map(id=>new View(id));
function schedule(){if(!request&&visible&&views.some(view=>view.inView))request=requestAnimationFrame(tick);}
function tick(now){
  request=0;if(!visible||!views.some(view=>view.inView)){previous=0;return;}
  const delta=previous?Math.min(.06,Math.max(0,(now-previous)/1000)):0;previous=now;if(!paused)time+=delta;
  let changing=false;for(const view of views)changing=view.advance(delta)||changing;
  const interval=views.some(view=>view.renderer.type!=='WebGL')?85:33;
  if(dirty||now-lastPaint>=interval){
    const progress=manual??sequenceAt(Math.max(0,time-BOOT)),scene=extractionAt(progress);
    views[0].draw({...scene,boxes:BASELINE,state:{...scene.state,flash:0}});views[1].draw(scene);
    scrub.value=String(Math.round(progress*100));scrub.setAttribute('aria-valuetext',`${Math.round(progress*100)} percent, ${scene.stage.label}`);
    if(lastStage!==scene.stage.id){lastStage=scene.stage.id;caption.textContent=scene.stage.description;for(const button of document.querySelectorAll('[data-stage]'))button.setAttribute('aria-pressed',String(button.dataset.stage===lastStage));}
    dirty=false;lastPaint=now;
  }
  if(!paused||changing)schedule();else previous=0;
}
function updateStatus(){
  const simple=views.some(view=>view.renderer.type!=='WebGL'||view.lost);
  pause.textContent=paused?'Play':'Pause';pause.setAttribute('aria-pressed',String(paused));
  status.textContent=(paused?(reduced.matches?'Reduced motion: the extracted pose is held.':'Motion paused. Scrub or choose a stage to inspect.'):'Motion is playing. The reference stays assembled while the candidate opens and extracts.')+(simple?' A simplified renderer is active.':'');
}
function setPaused(value){paused=value;previous=0;dirty=true;updateStatus();schedule();}
function hold(progress){manual=progress;bootSkipped=true;setPaused(true);}
pause.addEventListener('click',()=>{if(paused){if(manual!==null){time=BOOT+manual*8;manual=null;}bootSkipped=true;}setPaused(!paused);});
document.querySelector('#replay').addEventListener('click',()=>{time=0;manual=reduced.matches?0:null;bootSkipped=reduced.matches;lastStage='';for(const view of views){Object.assign(view.target,{turn:0,tilt:0,strength:0});Object.assign(view.pointer,view.target);}setPaused(reduced.matches);});
scrub.addEventListener('input',()=>hold(Number(scrub.value)/100));
for(const button of document.querySelectorAll('[data-stage]'))button.addEventListener('click',()=>hold(STAGES.find(stage=>stage.id===button.dataset.stage).progress));
linkedControl.addEventListener('change',()=>{linked=linkedControl.checked;for(const view of views)view.setTarget({turn:0,tilt:0,strength:0});});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;if(!visible&&request){cancelAnimationFrame(request);request=0;}schedule();});
reduced.addEventListener('change',event=>{if(event.matches){for(const view of views){Object.assign(view.target,{turn:0,tilt:0,strength:0});Object.assign(view.pointer,view.target);}hold(1);}});
for(const view of views)view.resize();updateStatus();schedule();
