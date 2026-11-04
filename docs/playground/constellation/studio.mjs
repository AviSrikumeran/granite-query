import {BOOT,pointerPose} from './engine/geometry.mjs?v=constellation-20261103-1';
import {makeGPU,makeCPU} from './engine/renderer.mjs?v=constellation-20261103-1';
import {makeAtlas} from './engine/atlas.mjs?v=constellation-20261103-1';
import {RECORDS,POSES,PERIOD,sceneAt,phaseAt,sequenceAt,layoutFor,projectWorld,boxHull,connections,bezier,springStep} from './forms.mjs?v=constellation-20261103-1';
import {FEEDS,deriveStudy,unavailableStudy} from './data.mjs?v=constellation-20261103-1';
const review=new URLSearchParams(location.search),reduced=matchMedia('(prefers-reduced-motion: reduce)');
const figure=document.querySelector('figure'),svg=document.querySelector('#wires'),tiles=document.querySelector('#tiles'),pause=document.querySelector('#pause'),scrub=document.querySelector('#scrub'),picker=document.querySelector('#record');
let canvas=figure.querySelector('canvas'),renderer,layout,width=0,height=0,ratio=1,lost=false,inView=true,visible=!document.hidden;
let time=0,paused=reduced.matches,manual=reduced.matches ? .52 : null,bootSkipped=reduced.matches,previous=0,lastPaint=0,request=0,dirty=true,chosen='auto',lastDetail='',drag=null,model=null;
const pointer={turn:0,tilt:0,strength:0,x:0,y:0},target={...pointer},offsets=RECORDS.map(()=>({x:0,y:0,vx:0,vy:0}));
const pose=POSES.find(p=>p.id===review.get('pose'));
if(pose){manual=pose.progress;paused=true;bootSkipped=true;time=4;}
const sample=Number(review.get('progress'));
if(review.has('progress')&&Number.isFinite(sample)){manual=Math.max(0,Math.min(1,sample));paused=true;bootSkipped=true;time=4;}
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
const ns='http://www.w3.org/2000/svg',makeSVG=(tag,attrs={})=>{const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));return el;};
const masks=Array.from({length:40},()=>{const p=makeSVG('polygon');document.querySelector('#occluders').append(p);return p;});
const wires=Array.from({length:13},()=>{
  const g=makeSVG('g'),glow=makeSVG('path',{fill:'none',stroke:'#ef53e8','stroke-width':4,filter:'url(#wire-glow)'}),line=makeSVG('path',{fill:'none',stroke:'#a849bb','stroke-width':1}),hot=makeSVG('path',{fill:'none',stroke:'#ffd1fa','stroke-width':1.5,pathLength:1,'stroke-dasharray':'.10 .90'}),dots=[0,1].map(()=>makeSVG('circle',{r:1.8,fill:'#ffeaff'}));
  g.append(glow,line,hot,...dots);document.querySelector('#paths').append(g);return {g,glow,line,hot,dots};
});
const buttons=[-1,...RECORDS.map((_,i)=>i)].map(index=>{
  const button=document.createElement('button');button.className='tile'+(index<0?' core':'');button.type='button';button.dataset.index=String(index);button.setAttribute('aria-pressed',String(index<0));const span=document.createElement('span');span.textContent=index<0?'Q':RECORDS[index].tag;button.append(span);
  button.setAttribute('aria-label',index<0?'Inspect the question or finding':'Inspect '+RECORDS[index].tag);
  button.addEventListener('click',()=>choose(index<0?'auto':RECORDS[index].id));
  button.addEventListener('focus',()=>choose(index<0?'auto':RECORDS[index].id));
  if(index>=0)button.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;choose(RECORDS[index].id);const o=offsets[index];drag={index,id:event.pointerId,x:event.clientX,y:event.clientY,ox:o.x,oy:o.y};button.setPointerCapture(event.pointerId);event.preventDefault();schedule();
  });
  tiles.append(button);return button;
});
function cellsFor(pitch){const cells=[],[cx,cy]=layout.center;for(let row=Math.ceil(-cy/pitch),y=cy+row*pitch;y<height;row++,y=cy+row*pitch){const stagger=row%2?.75:.25;for(let col=Math.ceil(-cx/pitch-stagger),x=cx+(col+stagger)*pitch;x<width;col++,x=cx+(col+stagger)*pitch)cells.push(x,y);}return new Float32Array(cells);}
const options={get:()=>({width,height,ratio,layout,pointer,time,bootSkipped,color:'#ff63ed',material:'magenta',ghosts:false}),makeCells:cellsFor,makeAtlas,hash};
function createRenderer(){
  renderer=null;try{if(review.get('renderer')!=='canvas')renderer=makeGPU(canvas,options);}catch(error){console.warn('Using simplified rendering:',error.message);}
  if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeCPU(canvas,options);}canvas.dataset.renderer=renderer.type;
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;updatePlayback();});
  canvas.addEventListener('webglcontextrestored',()=>{createRenderer();lost=false;resize();updatePlayback();},{once:true});
}
function resize(){const rect=figure.getBoundingClientRect();if(rect.width<1||rect.height<1)return;width=rect.width;height=rect.height;ratio=Math.min(1.5,devicePixelRatio||1);layout=layoutFor(width,height);canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);svg.setAttribute('viewBox','0 0 '+width+' '+height);document.querySelector('#mask-area').setAttribute('width',width);document.querySelector('#mask-area').setAttribute('height',height);if(!lost)renderer.resize();dirty=true;schedule();}
const progress=()=>manual??sequenceAt(Math.max(0,time-BOOT));
const indexFor=id=>RECORDS.findIndex(r=>r.id===id);
function activeId(){return chosen==='auto'?(phaseAt(progress()).resolve>.5?'answer':'query'):chosen;}
function choose(id){chosen=id;lastDetail='';dirty=true;showDetail();schedule();}
function showDetail(){
  const id=activeId();if(lastDetail===id)return;lastDetail=id;
  const node=model?.nodes[id];picker.value=id;
  document.querySelector('#record-kind').textContent=node?.kind??'Published evidence';
  document.querySelector('#record-title').textContent=node?.title??'Loading the public study…';
  document.querySelector('#record-text').textContent=node?.text??'The choreography is a visual experiment. Linked values come from the published development study.';
  const links=document.querySelector('#record-links');links.replaceChildren();
  for(const link of node?.links??[]){const a=document.createElement('a');a.textContent=link.label+' ↗';a.href=link.href;a.target='_blank';a.rel='noopener';links.append(a);}
}
picker.addEventListener('change',()=>choose(picker.value));
figure.addEventListener('pointermove',event=>{
  if(drag&&event.pointerId===drag.id){const o=offsets[drag.index];o.x=Math.max(-.65,Math.min(.65,drag.ox+(event.clientX-drag.x)/layout.unit));o.y=Math.max(-.65,Math.min(.65,drag.oy+(event.clientY-drag.y)/layout.unit));o.vx=0;o.vy=0;dirty=true;schedule();return;}
  if(event.pointerType==='touch'||reduced.matches)return;
  const rect=figure.getBoundingClientRect(),pose=pointerPose(event.clientX-rect.left,event.clientY-rect.top,width,height);
  Object.assign(target,{turn:pose.turn*1.6,tilt:pose.tilt*1.6,strength:1,x:(event.clientX-rect.left-layout.center[0])/layout.unit,y:(event.clientY-rect.top-layout.center[1])/layout.unit});dirty=true;schedule();
});
function release(event){if(!drag||event.pointerId!==drag.id)return;if(reduced.matches)Object.assign(offsets[drag.index],{x:0,y:0,vx:0,vy:0});drag=null;dirty=true;schedule();}
figure.addEventListener('pointerup',release);figure.addEventListener('pointercancel',release);figure.addEventListener('lostpointercapture',release);
figure.addEventListener('pointerleave',()=>{if(!drag){Object.assign(target,{turn:0,tilt:0,strength:0});dirty=true;schedule();}});
figure.addEventListener('keydown',event=>{
  const keys=['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'];if(!keys.includes(event.key))return;event.preventDefault();
  const index=Number(event.target.closest('.tile')?.dataset.index??-1);
  if(event.key==='Home'){resetPulls();return;}
  if(index>=0){const o=offsets[index];o.x=Math.max(-.65,Math.min(.65,o.x+(event.key==='ArrowLeft'?-.18:event.key==='ArrowRight'?.18:0)));o.y=Math.max(-.65,Math.min(.65,o.y+(event.key==='ArrowUp'?-.18:event.key==='ArrowDown'?.18:0)));o.vx=o.vy=0;}
  else{target.turn=Math.max(-.168,Math.min(.168,target.turn+(event.key==='ArrowLeft'?-.035:event.key==='ArrowRight'?.035:0)));target.tilt=Math.max(-.104,Math.min(.104,target.tilt+(event.key==='ArrowUp'?-.025:event.key==='ArrowDown'?.025:0)));target.strength=1;if(reduced.matches)Object.assign(pointer,target);}
  dirty=true;schedule();
});
function resetPulls(){drag=null;offsets.forEach(o=>Object.assign(o,{x:0,y:0,vx:0,vy:0}));Object.assign(target,{turn:0,tilt:0,strength:0,x:0,y:0});if(reduced.matches)Object.assign(pointer,target);dirty=true;schedule();}
document.querySelector('#reset').addEventListener('click',resetPulls);
function setPaused(value){paused=value;previous=0;dirty=true;updatePlayback();schedule();}
function updatePlayback(){pause.textContent=paused?'Play':'Pause';pause.setAttribute('aria-pressed',String(paused));}
function hold(value){manual=value;time=4;bootSkipped=true;resetPulls();choose('auto');setPaused(true);}
for(const button of document.querySelectorAll('[data-pose]'))button.addEventListener('click',()=>hold(POSES.find(p=>p.id===button.dataset.pose).progress));
pause.addEventListener('click',()=>{if(paused){if(manual!==null){time=BOOT+manual*PERIOD;manual=null;}bootSkipped=true;}setPaused(!paused);});
document.querySelector('#replay').addEventListener('click',()=>{time=0;manual=reduced.matches?0:null;bootSkipped=reduced.matches;resetPulls();choose('auto');setPaused(reduced.matches);});
scrub.addEventListener('input',()=>{manual=Number(scrub.value)/1000;bootSkipped=true;setPaused(true);});
const expand=document.querySelector('#expand');
function setExpanded(value){document.body.classList.toggle('immersive',value);expand.textContent=value?'Exit full canvas ↙':'Full canvas ↗';expand.setAttribute('aria-pressed',String(value));resize();}
expand.addEventListener('click',()=>setExpanded(!document.body.classList.contains('immersive')));
document.addEventListener('keydown',event=>{if(event.key==='Escape'){if(document.body.classList.contains('immersive'))setExpanded(false);setPaused(true);}});
function schedule(){if(!request&&visible&&inView)request=requestAnimationFrame(tick);}
function drawPaths(scene){
  scene.boxes.forEach((box,i)=>masks[i].setAttribute('points',box.half.every(v=>v>.001)?boxHull(box,layout,pointer.turn,pointer.tilt).map(p=>p.join(',')).join(' '):''));
  const paths=connections(scene,time);
  paths.forEach((path,i)=>{
    const wire=wires[i],points=path.controls.map(v=>projectWorld(v,layout,pointer.turn,pointer.tilt)),d='M '+points[0].join(' ')+' C '+points.slice(1).map(p=>p.join(' ')).join(' ');
    for(const el of [wire.line,wire.glow,wire.hot])el.setAttribute('d',d);
    wire.g.setAttribute('opacity',String(path.alpha*(path.highlight?.90:.20)));wire.glow.setAttribute('opacity',path.highlight?'.45':'.1');wire.hot.setAttribute('stroke-dashoffset',String(-((time*.20+i*.137)%1)));wire.line.setAttribute('stroke-width',path.highlight?'1.3':'.7');
    wire.dots.forEach((dot,j)=>{const t=((time*.22+i*.17+j*.5)%1),p=projectWorld(bezier(path.controls,t),layout,pointer.turn,pointer.tilt);dot.setAttribute('cx',p[0]);dot.setAttribute('cy',p[1]);dot.setAttribute('opacity',path.highlight?'1':'.25');});
  });
}
function tick(now){
  request=0;if(!visible||!inView){previous=0;return;}
  const dt=previous?Math.min(.05,Math.max(0,(now-previous)/1000)):0;previous=now;if(!paused)time+=dt;
  let changing=false;const ease=reduced.matches?1:1-Math.exp(-dt*7.5);
  for(const key of ['turn','tilt','strength','x','y']){pointer[key]+=(target[key]-pointer[key])*ease;if(Math.abs(target[key]-pointer[key])>.0001)changing=true;}
  offsets.forEach((o,i)=>{if(!reduced.matches&&drag?.index!==i)springStep(o,dt);if(!reduced.matches&&Math.hypot(o.x,o.y,o.vx,o.vy)>.0001)changing=true;});
  if(dirty||now-lastPaint>=(renderer.type==='WebGL'?33:90)){
    const p=progress(),selected=indexFor(activeId()),scene=sceneAt(p,{time,selected,pointer,offsets,spreadX:width<700?.82:1.6});
    if(layout&&!lost){renderer.draw({...scene,turn:pointer.turn,tilt:pointer.tilt});drawPaths(scene);
      buttons.forEach((button,i)=>{const pos=projectWorld(i===0?scene.core:scene.panels[i-1].center,layout,pointer.turn,pointer.tilt);button.style.left=pos[0]+'px';button.style.top=pos[1]+'px';button.setAttribute('aria-pressed',String(i===0?selected<0:selected===i-1));button.firstChild.style.opacity=String(i===0?1:scene.phase.open);if(i===0)button.firstChild.textContent=scene.phase.resolve>.5?'Finding':'Q';});
      Object.assign(canvas.dataset,{progress:p.toFixed(4),stage:scene.phase.stage,paused:String(paused),selected:activeId(),pulls:String(offsets.filter(o=>Math.hypot(o.x,o.y)>.01).length),dragging:drag?String(drag.index):'none',turn:pointer.turn.toFixed(4),tilt:pointer.tilt.toFixed(4)});
    }
    const titles={archive:'Archive / Packed records',scatter:'Scatter / Suspended evidence',trace:'Trace / Luminous connections',resolve:'Resolve / A structured finding',return:'Return / Magnetic reset'};
    document.querySelector('#phase-label').textContent=titles[scene.phase.stage];
    document.querySelector('#floating-note').textContent=selected>=0?(model?.nodes[activeId()]?.title??RECORDS[selected].tag):scene.phase.resolve>.5?(model?.verdict??'A finding with its limits attached.'):'One study. Eight evidence tiles.';
    scrub.value=String(Math.round(p*1000));scrub.setAttribute('aria-valuetext',scene.phase.stage);
    for(const b of document.querySelectorAll('[data-pose]'))b.setAttribute('aria-pressed',String(paused&&manual===POSES.find(p=>p.id===b.dataset.pose).progress));
    showDetail();dirty=false;lastPaint=now;
  }
  if(!paused||changing||drag)schedule();else previous=0;
}
let loading=false;
async function loadEvidence(){
  if(loading)return;loading=true;const refresh=document.querySelector('#refresh');refresh.disabled=true;refresh.textContent='Refreshing…';const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),12000);
  try{
    const response=await fetch(FEEDS.study,{cache:'no-store',signal:abort.signal});if(!response.ok)throw Error('The public study snapshot is unavailable.');
    const raw=await response.text();let digest=null;if(globalThis.crypto?.subtle)digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))].map(v=>v.toString(16).padStart(2,'0')).join('');
    model=deriveStudy(JSON.parse(raw),{digest});document.querySelector('#feed-status').textContent=(model.age.stale?'Stale published snapshot':'Published development snapshot')+' · '+new Date(model.age.timestamp).toISOString().replace('T',' ').slice(0,16)+' UTC · Motion is choreographed, not a live training display.';
  }catch(error){model=unavailableStudy(error.message);document.querySelector('#feed-status').textContent='Evidence unavailable. The visual remains a motion study; no result is inferred.';}
  finally{clearTimeout(timeout);loading=false;refresh.disabled=false;refresh.textContent='Refresh evidence';lastDetail='';showDetail();canvas.dataset.dataStatus=model.status;dirty=true;schedule();}
}
document.querySelector('#refresh').addEventListener('click',loadEvidence);
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;if(!visible&&request){cancelAnimationFrame(request);request=0;}if(visible){dirty=true;schedule();}});
reduced.addEventListener('change',event=>{if(event.matches){manual=.52;bootSkipped=true;resetPulls();setPaused(true);}});
createRenderer();new ResizeObserver(resize).observe(figure);new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;if(inView){dirty=true;schedule();}}).observe(figure);resize();updatePlayback();loadEvidence();schedule();
