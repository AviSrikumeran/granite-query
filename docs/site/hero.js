import {BOOT,pointerPose} from '../playground/purple/engine/geometry.mjs?v=magenta-20261103-2';
import {makeGPU,makeCPU} from '../playground/purple/engine/renderer.mjs?v=magenta-20261103-2';
import {makeAtlas} from '../playground/purple/engine/atlas.mjs?v=magenta-20261103-2';
import {PERIOD,formationAt} from '../playground/purple/forms.mjs?v=magenta-20261103-2';

// The accepted Electric magenta specimen, rather than the later extraction
// sculpture. Geometry, material tiers, pose timing and selective flashes come
// directly from its unchanged modules. The wrapper only owns page lifecycle.
export const HERO_CONFIG=Object.freeze({startProgress:0,speed:1,pixelRatio:1.5,maxFPS:30,turnLimit:.105,tiltLimit:.065});
const instances=new WeakMap();let serial=0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
export function heroLayout(width,height){const unit=Math.max(1,Math.min((width-20)/3.8,(height-20)/3.8));return{unit,center:[width*.5,height*.5],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};}
export function heroScene(value){const progress=clamp(value,0,1),scene=formationAt('purple',BOOT+progress*PERIOD,'auto',0,'clear');return{...scene,progress,stage:{id:scene.state.focus}};}
function releaseContext(canvas){if(canvas.tagName!=='CANVAS')return;try{canvas.getContext('webgl')?.getExtension('WEBGL_lose_context')?.loseContext();}catch{/* Context may already have been lost by the browser. */}}

/** Mount one original magenta artwork. Returns {destroy,pause,play,resetView,getState}. */
export function initHero(container,{autoplay=true,intro=false,pixelRatio=HERO_CONFIG.pixelRatio,renderer:requestedRenderer='auto'}={}){
  if(!container||container.nodeType!==1)throw new TypeError('initHero requires a container element.');
  instances.get(container)?.destroy();
  const owner=container.ownerDocument,win=owner.defaultView,abort=new AbortController(),signal=abort.signal,reduced=win.matchMedia('(prefers-reduced-motion: reduce)'),id='gq-material-'+(++serial);
  const initialStyle={position:container.style.position,minHeight:container.style.minHeight},changedPosition=win.getComputedStyle(container).position==='static',changedHeight=container.getBoundingClientRect().height<120&&win.getComputedStyle(container).display!=='none';
  if(changedPosition)container.style.position='relative';if(changedHeight)container.style.minHeight='clamp(330px, 45vw, 560px)';
  const root=owner.createElement('div');root.dataset.gqHero=id;root.className='gq-material-art';
  const style=owner.createElement('style');style.textContent=`[data-gq-hero="${id}"]{position:absolute;inset:0;overflow:hidden;background:transparent}[data-gq-hero="${id}"] canvas{position:absolute;inset:0;width:100%;height:100%;display:block;mix-blend-mode:lighten;mask-image:radial-gradient(ellipse at 50% 50%,#000 52%,#000d 76%,transparent 100%);-webkit-mask-image:radial-gradient(ellipse at 50% 50%,#000 52%,#000d 76%,transparent 100%);touch-action:pan-y}[data-gq-hero="${id}"] canvas:focus-visible{outline:1px solid #ffc1f4a0;outline-offset:-9px}[data-gq-hero="${id}"] .gq-material-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;border:0}[data-gq-hero="${id}"] .gq-material-fallback{position:absolute;inset:30%;color:#a479a7;font:12px/1.8 Arial,Helvetica,sans-serif;text-align:center}`;
  let canvas=owner.createElement('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Electric magenta interlocking block');canvas.tabIndex=0;canvas.setAttribute('aria-describedby',id+'-help');
  const help=owner.createElement('p');help.id=id+'-help';help.className='gq-material-sr';help.textContent='Decorative electric magenta artwork. Move the pointer to turn it. Arrow keys change the view. Escape pauses movement; Space or Enter resumes or pauses.';
  const status=owner.createElement('p');status.className='gq-material-sr';status.setAttribute('role','status');root.append(style,canvas,help,status);container.append(root);
  let renderer=null,needsRendererResize=true,canvasEvents=null,width=0,height=0,ratio=1,layout=null,time=BOOT,phase=HERO_CONFIG.startProgress*PERIOD,manual=reduced.matches?HERO_CONFIG.startProgress:null,paused=reduced.matches||!autoplay,bootSkipped=!intro||reduced.matches||!autoplay,visible=!owner.hidden,inView=true,lost=false,destroyed=false,request=0,previous=0,lastPaint=-Infinity,dirty=true;
  if(intro&&!bootSkipped)time=0;
  const pointer={turn:0,tilt:0,strength:0},target={...pointer};
  const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
  function cellsFor(pitch){const cells=[],[cx,cy]=layout.center;for(let row=Math.ceil(-cy/pitch),y=cy+row*pitch;y<height;row++,y=cy+row*pitch){const stagger=row%2?.75:.25;for(let col=Math.ceil(-cx/pitch-stagger),x=cx+(col+stagger)*pitch;x<width;col++,x=cx+(col+stagger)*pitch)cells.push(x,y);}return new Float32Array(cells);}
  const options={get:()=>({width,height,ratio,layout,pointer,time,bootSkipped,color:'#ff63ed',material:'magenta',ghosts:true}),makeCells:cellsFor,makeAtlas,hash};
  function updateStatus(message){if(message)status.textContent=message;}
  function cancelFrame(){if(request)win.cancelAnimationFrame(request);request=0;previous=0;}
  function refreshVisibility(){if(destroyed)return false;const wasActive=visible&&inView,rect=root.getBoundingClientRect(),viewportWidth=win.innerWidth||owner.documentElement.clientWidth,viewportHeight=win.innerHeight||owner.documentElement.clientHeight;visible=!owner.hidden;inView=rect.width>0&&rect.height>0&&rect.bottom>0&&rect.right>0&&rect.top<viewportHeight&&rect.left<viewportWidth;if(visible&&inView&&!wasActive)dirty=true;return visible&&inView;}
  function schedule(){if(destroyed)return;if(!refreshVisibility()){cancelFrame();return;}if(!request&&!lost&&width>0&&height>0)request=win.requestAnimationFrame(tick);}
  function createRenderer(){
    canvasEvents?.abort();renderer=null;needsRendererResize=true;let attempted=false;
    try{if(requestedRenderer!=='canvas'){attempted=true;renderer=makeGPU(canvas,options);}}catch{/* The existing Canvas 2D path is the graceful fallback. */}
    if(!renderer){if(attempted)releaseContext(canvas);const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeCPU(canvas,options);}
    canvas.dataset.renderer=renderer.type;canvasEvents=new AbortController();const canvasSignal=canvasEvents.signal;
    canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;canvas.dataset.renderer='Context lost';cancelFrame();updateStatus('The artwork is paused while graphics recover.');},{signal:canvasSignal});
    canvas.addEventListener('webglcontextrestored',()=>{if(destroyed)return;lost=false;createRenderer();resize();dirty=true;schedule();updateStatus('The material artwork is available again.');},{signal:canvasSignal});
    canvas.addEventListener('pointermove',event=>{if(reduced.matches||event.pointerType==='touch')return;const rect=canvas.getBoundingClientRect(),pose=pointerPose(event.clientX-rect.left,event.clientY-rect.top,rect.width,rect.height);setTarget({...pose,strength:1});},{signal:canvasSignal});
    canvas.addEventListener('pointerleave',()=>setTarget({turn:0,tilt:0,strength:0}),{signal:canvasSignal});
    if(renderer.type==='unavailable'){canvas.hidden=true;const fallback=owner.createElement('p');fallback.className='gq-material-fallback';fallback.textContent='Material artwork unavailable in this browser.';root.append(fallback);paused=true;}
  }
  function resize(){if(destroyed)return;const rect=root.getBoundingClientRect();if(rect.width<1||rect.height<1){cancelFrame();return;}const nextRatio=Math.min(2,Math.max(1,Math.min(Number(pixelRatio)||HERO_CONFIG.pixelRatio,win.devicePixelRatio||1))),sizeChanged=width!==rect.width||height!==rect.height||ratio!==nextRatio;width=rect.width;height=rect.height;ratio=nextRatio;layout=heroLayout(width,height);if(!renderer)createRenderer();const pixelWidth=Math.max(1,Math.round(width*ratio)),pixelHeight=Math.max(1,Math.round(height*ratio));if(canvas.width!==pixelWidth)canvas.width=pixelWidth;if(canvas.height!==pixelHeight)canvas.height=pixelHeight;if(!lost&&(sizeChanged||needsRendererResize)){renderer.resize();needsRendererResize=false;}dirty=true;if(refreshVisibility()&&!lost)paint(win.performance.now());schedule();}
  function progress(){return manual??(((phase+Math.max(0,time-BOOT)*HERO_CONFIG.speed)%PERIOD)+PERIOD)%PERIOD/PERIOD;}
  function setTarget(value){Object.assign(target,value);target.turn=clamp(target.turn,-HERO_CONFIG.turnLimit,HERO_CONFIG.turnLimit);target.tilt=clamp(target.tilt,-HERO_CONFIG.tiltLimit,HERO_CONFIG.tiltLimit);if(reduced.matches)Object.assign(pointer,target);dirty=true;schedule();}
  function setPaused(value){if(destroyed)return;paused=value;bootSkipped=true;if(!paused&&manual!==null){phase=manual*PERIOD-Math.max(0,time-BOOT)*HERO_CONFIG.speed;manual=null;}previous=0;dirty=true;updateStatus(paused?'Artwork movement paused.':'Artwork movement playing.');if(refreshVisibility()&&renderer&&layout&&!lost)paint(win.performance.now());schedule();}
  function resetView(){setTarget({turn:0,tilt:0,strength:0});updateStatus('Artwork view reset.');}
  function turn(amount){setTarget({...target,turn:target.turn+amount,strength:1});}
  root.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','Escape'].includes(event.key)){event.preventDefault();if(event.key==='Escape'){setPaused(true);return;}if(event.key==='Home'){resetView();return;}if(event.key==='ArrowLeft')turn(-.025);if(event.key==='ArrowRight')turn(.025);if(event.key==='ArrowUp')setTarget({...target,tilt:target.tilt-.018,strength:1});if(event.key==='ArrowDown')setTarget({...target,tilt:target.tilt+.018,strength:1});}else if(event.target===canvas&&['Enter',' '].includes(event.key)){event.preventDefault();setPaused(!paused);}},{signal});
  function tick(now){request=0;if(destroyed||!refreshVisibility()||lost){previous=0;return;}const delta=previous?Math.min(.05,Math.max(0,(now-previous)/1000)):0;previous=now;if(!paused)time+=delta;const response=reduced.matches?1:1-Math.exp(-delta*7.5);let changing=false;for(const key of ['turn','tilt','strength']){pointer[key]+=(target[key]-pointer[key])*response;if(Math.abs(target[key]-pointer[key])>.0001)changing=true;else pointer[key]=target[key];}
    const interval=renderer.type==='WebGL'?1000/HERO_CONFIG.maxFPS:110;if(dirty||now-lastPaint>=interval)paint(now);if(!paused||changing)schedule();else previous=0;
  }
  function paint(now){if(destroyed||lost||!renderer||!layout)return;const scene=heroScene(progress());renderer.draw({...scene,turn:pointer.turn,tilt:pointer.tilt});Object.assign(canvas.dataset,{progress:scene.progress.toFixed(4),stage:scene.stage.id,pose:scene.state.focus,blend:scene.state.blend.toFixed(3),flash:scene.state.flash.toFixed(3),source:'electric-magenta',spacing:'clear',ghosts:'true',paused:String(paused),turn:pointer.turn.toFixed(4),tilt:pointer.tilt.toFixed(4),material:'magenta',time:time.toFixed(3)});dirty=false;lastPaint=now;}
  owner.addEventListener('visibilitychange',()=>{visible=!owner.hidden;cancelFrame();if(visible){dirty=true;schedule();}},{signal});
  reduced.addEventListener('change',event=>{if(event.matches){manual=HERO_CONFIG.startProgress;Object.assign(pointer,{turn:0,tilt:0,strength:0});Object.assign(target,pointer);setPaused(true);}},{signal});
  const resizeObserver=new ResizeObserver(resize);resizeObserver.observe(root);const intersectionObserver=new IntersectionObserver(()=>{cancelFrame();if(refreshVisibility()){dirty=true;schedule();}},{threshold:.01});intersectionObserver.observe(root);win.addEventListener('resize',resize,{signal});win.addEventListener('scroll',()=>{if(refreshVisibility()){dirty=true;schedule();}else cancelFrame();},{signal,passive:true,capture:true});
  const controller={pause:()=>setPaused(true),play:()=>setPaused(false),resetView,getState:()=>({paused,reducedMotion:reduced.matches,progress:progress(),visible,inView,renderer:renderer?.type??'pending',destroyed}),destroy(){if(destroyed)return;destroyed=true;cancelFrame();abort.abort();canvasEvents?.abort();resizeObserver.disconnect();intersectionObserver.disconnect();if(renderer?.type==='WebGL')releaseContext(canvas);renderer=null;canvas.width=1;canvas.height=1;root.remove();if(changedPosition&&container.style.position==='relative')container.style.position=initialStyle.position;if(changedHeight&&container.style.minHeight==='clamp(330px, 45vw, 560px)')container.style.minHeight=initialStyle.minHeight;if(instances.get(container)===controller)instances.delete(container);}};
  instances.set(container,controller);resize();updateStatus(reduced.matches?'Reduced motion: a still electric magenta block.':'Interactive electric magenta artwork.');schedule();return controller;
}
