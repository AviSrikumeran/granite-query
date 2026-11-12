import {makeGPU} from './gq-renderer.mjs?v=20261111-1';
import {makeAtlas} from '../playground/purple/engine/atlas.mjs?v=magenta-20261103-2';

// The approved Slow turn treatment is a single rigid artwork. Glyphs never split.
const instances=new WeakMap();
const css=document.createElement('style');
css.textContent=`
header .gq-logo-link{position:relative;display:inline-block!important;width:98px;height:60px;flex:0 0 98px;vertical-align:middle;line-height:1;text-decoration:none!important}
.gq-logo-link canvas{display:block;width:100%;height:100%;transform-origin:50% 50%;will-change:transform;opacity:0;filter:brightness(1.65) saturate(1.16)}
.gq-logo-link[data-gq-ready="true"] canvas{opacity:1}
.gq-logo-fallback{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font:600 30px/1 Arial,Helvetica,sans-serif;letter-spacing:-2px;color:#f66af2;text-shadow:0 0 13px #df46d352}
.gq-logo-link[data-gq-ready="true"] .gq-logo-fallback{visibility:hidden}
.library-page header .gq-logo-link,header.site-header .gq-logo-link,.gq-site-header .gq-logo-link{background:#100b15;border-radius:4px}
.gq-logo-help{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media(max-width:650px){header .gq-logo-link{width:86px;height:54px;flex-basis:86px}}
`;
document.head.append(css);

export function mountNavigationLogo(link){
 if(!link||instances.has(link))return instances.get(link);
 const saved={html:link.innerHTML,label:link.getAttribute('aria-label'),description:link.getAttribute('aria-describedby')};
 const abort=new AbortController(),signal=abort.signal,reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const canvas=document.createElement('canvas');canvas.setAttribute('aria-hidden','true');
 const fallback=document.createElement('span');fallback.className='gq-logo-fallback';fallback.textContent='GQ';fallback.setAttribute('aria-hidden','true');
 const help=document.createElement('span');help.className='gq-logo-help';help.id='gq-logo-help';help.textContent='Animated GraniteQuery logo. Space pauses or resumes the light and turn; Escape pauses. Enter goes to the homepage.';
 link.classList.add('gq-logo-link');link.setAttribute('aria-label','GraniteQuery home');link.setAttribute('aria-describedby',help.id);link.replaceChildren(fallback,canvas,help);
 let gpu=null,clock=1.5,request=0,previous=0,lastPaint=-Infinity,inView=true,paused=reduced.matches,lost=false,destroyed=false,width=0,height=0,ratio=1,layout=null;
 const pointer={turn:0,tilt:0,strength:0},design={width:300,height:190};
 const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n)};
 const makeCells=pitch=>{const result=[],[cx,cy]=layout.center;for(let row=Math.ceil(-cy/pitch),y=cy+row*pitch;y<design.height;row++,y=cy+row*pitch){const stagger=row%2?.75:.25;for(let col=Math.ceil(-cx/pitch-stagger),x=cx+(col+stagger)*pitch;x<design.width;col++,x=cx+(col+stagger)*pitch)result.push(x,y)}return new Float32Array(result)};
 function stop(){if(request)cancelAnimationFrame(request);request=0;previous=0}
 function schedule(){if(!request&&!destroyed&&!lost&&!paused&&inView&&!document.hidden)request=requestAnimationFrame(tick)}
 function draw(){
  if(!gpu||!layout||lost||destroyed)return;
  gpu.draw({boxes:[],turn:-16*Math.PI/180,tilt:-.10,shineTime:clock,shineStrength:1.1,shineStyle:2,energy:0,state:{flash:.24}});
  const turn=reduced.matches?0:Math.sin(clock*.65)*7,tilt=reduced.matches?0:Math.sin(clock*.65+.6)*2.3;
  canvas.style.transform=`perspective(950px) rotateY(${turn}deg) rotateX(${tilt}deg)`;
  Object.assign(link.dataset,{gqReady:'true',gqPlaying:String(!paused&&!document.hidden&&inView),gqTime:clock.toFixed(3),gqMotion:'slow-turn'});
 }
 function create(){gpu=makeGPU(canvas,{get:()=>({width:design.width,height:design.height,ratio,layout,time:6,bootSkipped:true,pointer,material:'magenta',ghosts:false}),makeCells,makeAtlas,hash});if(!gpu)throw Error('WebGL unavailable')}
 function resize(){
  if(destroyed||lost)return;
  width=link.clientWidth;height=link.clientHeight;if(!width||!height)return;
  const dpr=Math.min(2,devicePixelRatio||1),nextWidth=Math.round(width*dpr),nextHeight=Math.round(height*dpr);
  if(canvas.width!==nextWidth)canvas.width=nextWidth;if(canvas.height!==nextHeight)canvas.height=nextHeight;
  ratio=canvas.width/design.width;
  const unit=design.width/5.5,pitch=unit*7.6/95;
  layout={unit,center:[design.width*.5,design.height*.46],pitch,glyphSize:pitch*7.4/6.4,footprint:pitch*11/6.4,left:0,right:design.width,top:0,bottom:design.height};
  try{if(!gpu)create();gpu.resize();draw();schedule()}catch{gpu=null;link.dataset.gqReady='false';stop()}
 }
 function tick(now){request=0;if(destroyed||lost||paused||!inView||document.hidden){previous=0;return}const dt=previous?Math.min(.1,(now-previous)/1000):0;previous=now;clock+=dt;if(now-lastPaint>=1000/18){draw();lastPaint=now}schedule()}
 function setPaused(value){paused=value;stop();draw();schedule()}
 link.addEventListener('keydown',event=>{if(event.key===' '){event.preventDefault();setPaused(!paused)}else if(event.key==='Escape')setPaused(true)},{signal});
 document.addEventListener('visibilitychange',()=>{stop();if(document.hidden)link.dataset.gqPlaying='false';else{draw();schedule()}},{signal});
 reduced.addEventListener('change',event=>{if(event.matches){clock=1.5;setPaused(true)}},{signal});
 canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;link.dataset.gqReady='false';link.dataset.gqPlaying='false';stop()},{signal});
 canvas.addEventListener('webglcontextrestored',()=>{lost=false;gpu=null;resize()},{signal});
 const sizeObserver=new ResizeObserver(resize);sizeObserver.observe(link);
 const visibilityObserver=new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;stop();if(inView){draw();schedule()}else link.dataset.gqPlaying='false'},{threshold:.01});visibilityObserver.observe(link);
 const controller={pause:()=>setPaused(true),play:()=>setPaused(false),destroy(){if(destroyed)return;destroyed=true;stop();abort.abort();sizeObserver.disconnect();visibilityObserver.disconnect();canvas.getContext('webgl')?.getExtension('WEBGL_lose_context')?.loseContext();link.innerHTML=saved.html;link.classList.remove('gq-logo-link');for(const [key,value]of [['aria-label',saved.label],['aria-describedby',saved.description]])value===null?link.removeAttribute(key):link.setAttribute(key,value);for(const key of ['gqReady','gqPlaying','gqTime','gqMotion'])delete link.dataset[key];instances.delete(link)}};
 instances.set(link,controller);resize();return controller;
}

document.querySelectorAll('header.site-nav .wordmark,header.site-header .wordmark,.gq-site-header .gq-wordmark').forEach(mountNavigationLogo);
