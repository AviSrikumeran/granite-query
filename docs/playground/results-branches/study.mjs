import {pointerPose} from './engine/geometry.mjs?v=results-20261103-1';
import {makeGPU,makeCPU} from './engine/renderer.mjs?v=results-20261103-1';
import {makeAtlas} from './engine/atlas.mjs?v=results-20261103-1';
import {NODES,STAGES,bindContent,graphAt,nodeVisibility,layoutFor,project,progressFromScroll,stageAt} from './graph.mjs?v=results-20261103-1';
import {startEvidence,fillLinks} from './content.mjs?v=results-20261103-1';

const review=new URLSearchParams(location.search),reduced=matchMedia('(prefers-reduced-motion: reduce)'),mobile=matchMedia('(max-width:700px)');
const figure=document.querySelector('figure'),visual=document.querySelector('.visual'),controls=document.querySelector('#node-controls');
const sections=[...document.querySelectorAll('[data-section]')],full=document.querySelector('#show-all');
let canvas=figure.querySelector('canvas'),renderer,layout,width=0,height=0,ratio=1,lost=false,inView=true,visible=!document.hidden;
let anchors=[0,1,2,3],manual=null,progress=0,targetProgress=0,selected='query',lastStage=-1,dirty=true,request=0,previous=0,lastPaint=0;
const pointer={strength:0,turn:0,tilt:0},targetPointer={...pointer};
const sample=Number(review.get('progress'));
if(review.has('progress')&&Number.isFinite(sample))manual=Math.max(0,Math.min(1,sample));
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
const buttons=NODES.map((node,index)=>{
  const button=document.createElement('button');button.type='button';button.className='node';button.disabled=true;
  button.dataset.kind=index===10?'answer':index>4?'leaf':'source';
  button.setAttribute('aria-label',`${node.tag} · ${node.label}`);button.setAttribute('aria-pressed','false');
  const tag=document.createElement('span');tag.className='node-tag';tag.textContent=node.tag;button.append(tag);
  button.addEventListener('click',()=>selectNode(node.id));controls.append(button);return button;
});
function cellsFor(pitch){
  const cells=[],[cx,cy]=layout.center;
  for(let row=Math.ceil(-cy/pitch),y=cy+row*pitch;y<height;row++,y=cy+row*pitch){
    const stagger=row%2?.75:.25;
    for(let col=Math.ceil(-cx/pitch-stagger),x=cx+(col+stagger)*pitch;x<width;col++,x=cx+(col+stagger)*pitch)cells.push(x,y);
  }
  return new Float32Array(cells);
}
const options={get:()=>({width,height,ratio,layout,pointer,time:4,bootSkipped:true,color:'#ff63ed',material:'magenta',ghosts:false}),makeCells:cellsFor,makeAtlas,hash};
function createRenderer(){
  renderer=null;
  try{if(review.get('renderer')!=='canvas')renderer=makeGPU(canvas,options);}catch(error){console.warn('Using the simplified renderer:',error.message);}
  if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeCPU(canvas,options);}
  canvas.dataset.renderer=renderer.type;
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;updateMode();});
  canvas.addEventListener('webglcontextrestored',()=>{createRenderer();lost=false;resize();updateMode();},{once:true});
}
function measureAnchors(){
  const offset=mobile.matches?visual.getBoundingClientRect().height+32:innerHeight*.28;
  anchors=sections.map(section=>section.getBoundingClientRect().top+scrollY-offset);
}
function setProgress(){
  targetProgress=manual??(reduced.matches?1:progressFromScroll(scrollY,anchors));
  if(reduced.matches)progress=targetProgress;
  dirty=true;schedule();
}
function resize(){
  const rect=figure.getBoundingClientRect();if(rect.width<1||rect.height<1)return;
  width=rect.width;height=rect.height;ratio=Math.min(1.5,devicePixelRatio||1);layout=layoutFor(width,height);
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);if(!lost)renderer.resize();measureAnchors();setProgress();
}
function selectNode(id){
  const node=NODES.find(n=>n.id===id);if(!node)return;
  selected=id;document.querySelector('#detail-kind').textContent=node.kind;
  document.querySelector('#detail-source').textContent=node.source?`From ${node.source}`:'';
  document.querySelector('#detail-title').textContent=node.title;document.querySelector('#detail-text').textContent=node.text;
  fillLinks(document.querySelector('#detail-links'),node.links);
  document.querySelector('#detail-pointer').textContent=node.pointer??'';
  for(const button of document.querySelectorAll('[data-inspect]'))button.setAttribute('aria-pressed',String(button.dataset.inspect===id));
  dirty=true;schedule();
}
function goToStage(index){
  manual=null;updateMode();measureAnchors();window.scrollTo({top:Math.max(0,anchors[index]),behavior:reduced.matches?'auto':'smooth'});setProgress();
}
for(const link of document.querySelectorAll('[data-step]'))link.addEventListener('click',event=>{event.preventDefault();goToStage(Number(link.dataset.step));});
for(const button of document.querySelectorAll('[data-inspect]'))button.addEventListener('click',()=>{
  const node=NODES.find(n=>n.id===button.dataset.inspect);selectNode(node.id);
  if(nodeVisibility(node,targetProgress)<1)goToStage(node.stage);
});
full.addEventListener('click',()=>{manual=manual===null?1:null;updateMode();setProgress();});
function updateMode(){
  full.disabled=reduced.matches;full.textContent=reduced.matches?'Full map · reduced motion':manual!==null?'Follow scroll':'Show full map';
  full.setAttribute('aria-pressed',String(manual!==null||reduced.matches));
  const suffix=lost?' · Graphics waiting to recover':renderer?.type!=='WebGL'?' · Simplified rendering':'';
  document.querySelector('#scroll-cue').textContent=(reduced.matches?'Full map · motion reduced':manual===1?'Full map · select any node':manual!==null?'Held review pose · select a node':'Scroll to grow the map ↓')+suffix;
}
function setPointer(value){Object.assign(targetPointer,value);if(reduced.matches)Object.assign(pointer,value);dirty=true;schedule();}
figure.addEventListener('pointermove',event=>{
  if(event.pointerType==='touch'||reduced.matches)return;
  const rect=figure.getBoundingClientRect();setPointer({...pointerPose(event.clientX-rect.left,event.clientY-rect.top,rect.width,rect.height),strength:1});
});
figure.addEventListener('pointerleave',()=>setPointer({turn:0,tilt:0,strength:0}));
figure.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return;
  event.preventDefault();const value={...targetPointer,strength:1};
  if(event.key==='Home')Object.assign(value,{turn:0,tilt:0,strength:0});
  if(event.key==='ArrowLeft')value.turn-=.025;if(event.key==='ArrowRight')value.turn+=.025;
  if(event.key==='ArrowUp')value.tilt-=.018;if(event.key==='ArrowDown')value.tilt+=.018;
  value.turn=Math.max(-.105,Math.min(.105,value.turn));value.tilt=Math.max(-.065,Math.min(.065,value.tilt));setPointer(value);
});
function schedule(){if(!request&&visible&&inView)request=requestAnimationFrame(tick);}
function tick(now){
  request=0;if(!visible||!inView){previous=0;return;}
  const delta=previous?Math.min(.06,Math.max(0,(now-previous)/1000)):0;previous=now;
  const response=reduced.matches?1:1-Math.exp(-delta*10),pointerResponse=1-Math.exp(-delta*7.5);
  progress+=(targetProgress-progress)*response;if(Math.abs(progress-targetProgress)<.00005)progress=targetProgress;
  let changing=Math.abs(progress-targetProgress)>.00005;
  for(const key of ['turn','tilt','strength']){pointer[key]+=(targetPointer[key]-pointer[key])*pointerResponse;if(Math.abs(targetPointer[key]-pointer[key])>.0001)changing=true;}
  if(dirty||now-lastPaint>=(renderer.type==='WebGL'?33:85)){
    const stage=stageAt(progress);
    if(stage!==lastStage){
      lastStage=stage;document.querySelector('#map-phase').textContent=STAGES[stage].label;
      if(NODES.find(n=>n.id===selected).stage!==stage)selectNode(['query','evaluation','matched','answer'][stage]);
      for(const link of document.querySelectorAll('[data-step]')){if(Number(link.dataset.step)===stage)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');}
    }
    if(layout&&!lost){
      renderer.draw({...graphAt(progress,selected),turn:pointer.turn,tilt:pointer.tilt});
      let count=0;
      NODES.forEach((node,i)=>{
        const visibility=nodeVisibility(node,progress),button=buttons[i],pos=project(node.point,layout,pointer.turn,pointer.tilt),ready=visibility>.98;
        if(ready)count++;if(!ready&&document.activeElement===button)figure.focus({preventScroll:true});
        button.disabled=!ready;button.style.opacity=String(visibility);button.style.left=`${pos[0]}px`;button.style.top=`${pos[1]}px`;button.setAttribute('aria-pressed',String(node.id===selected));
      });
      Object.assign(canvas.dataset,{progress:progress.toFixed(4),target:targetProgress.toFixed(4),stage:STAGES[stage].id,nodeCount:String(count),turn:pointer.turn.toFixed(4),tilt:pointer.tilt.toFixed(4),mode:manual!==null?'held':reduced.matches?'reduced':'scroll'});
      document.querySelector('#map-progress').style.transform=`scaleX(${progress})`;
    }
    dirty=false;lastPaint=now;
  }
  if(changing)schedule();else previous=0;
}
window.addEventListener('scroll',setProgress,{passive:true});
window.addEventListener('resize',()=>{measureAnchors();setProgress();},{passive:true});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;if(!visible&&request){cancelAnimationFrame(request);request=0;}if(visible){dirty=true;schedule();}});
reduced.addEventListener('change',()=>{Object.assign(pointer,{turn:0,tilt:0,strength:0});Object.assign(targetPointer,pointer);updateMode();setProgress();});
createRenderer();new ResizeObserver(resize).observe(figure);
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;if(inView){dirty=true;schedule();}}).observe(figure);
resize();progress=targetProgress;selectNode(['query','evaluation','matched','answer'][stageAt(progress)]);updateMode();schedule();
new ResizeObserver(()=>{measureAnchors();setProgress();}).observe(visual);
new ResizeObserver(()=>{measureAnchors();setProgress();}).observe(document.querySelector('.walkthrough'));
startEvidence(model=>{
  bindContent(model.nodes);
  NODES.forEach((node,i)=>buttons[i].setAttribute('aria-label',node.tag+' · '+node.label));
  canvas.dataset.dataStatus=model.status;
  selectNode(selected);measureAnchors();setProgress();
});
