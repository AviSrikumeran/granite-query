import {createNavigationMaterial,GLYPH_COUNT} from './gq-block-material.mjs?v=20261111-5';

// The approved Slow turn treatment is a single rigid artwork. Glyphs never split.
const instances=new WeakMap();
const css=document.createElement('style');
css.textContent=`
header .gq-logo-link{position:relative;top:6px;display:inline-block!important;width:600px;max-width:100%;min-width:0;height:88px;flex:0 1 600px;vertical-align:middle;line-height:1;text-decoration:none!important;background:transparent!important;border-radius:0}
header.site-nav:has(.gq-logo-link){height:112px;gap:24px}
.gq-header-inner:has(.gq-logo-link){min-height:112px;display:flex;gap:24px;align-items:center}
header.site-header:has(.gq-logo-link){flex-wrap:wrap;gap:8px 24px;padding-block:8px}
.gq-logo-link canvas{display:block;width:100%;height:100%;transform-origin:50% 50%;will-change:transform;opacity:0}
.gq-logo-link[data-gq-ready="true"] canvas{opacity:1}
.gq-logo-fallback{position:absolute;inset:0;display:flex;align-items:center;justify-content:flex-start;font:600 clamp(24px,5vw,48px)/1.1 Arial,Helvetica,sans-serif;letter-spacing:-1px;white-space:normal;overflow-wrap:anywhere;color:#d52ac7;text-shadow:0 0 8px #df46d329}
.gq-logo-link[data-gq-ready="true"] .gq-logo-fallback{visibility:hidden}
.gq-logo-help{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media(max-width:1280px){
 header.site-nav:has(.gq-logo-link){padding-inline:24px;gap:20px}
 header.site-nav:has(.gq-logo-link) .menu-toggle{display:flex;align-items:center;gap:16px;min-height:44px;flex:none;border:0;background:transparent;color:inherit;font-size:13px;padding:10px 0}
 header.site-nav:has(.gq-logo-link) nav{display:none;position:absolute;left:0;right:0;top:112px;padding:15px 24px 20px;background:var(--night);border-bottom:1px solid #ffffff29;flex-direction:column;align-items:stretch;gap:0;font-size:14px}
 header.site-nav:has(.gq-logo-link) nav.is-open{display:flex}
 header.site-nav:has(.gq-logo-link) nav>a{min-height:48px;padding:14px 0;border-bottom:1px solid #ffffff17}
 .library-page header.site-nav:has(.gq-logo-link) nav{background:var(--paper);border-color:var(--line)}
 .library-page header.site-nav:has(.gq-logo-link) nav>a{border-color:var(--line)}
 .gq-header-inner:has(.gq-logo-link){position:relative;padding-inline:24px}
 .gq-header-inner:has(.gq-logo-link) .gq-menu-toggle{display:block;margin-left:auto;min-height:44px;min-width:70px;flex:none}
 .gq-header-inner:has(.gq-logo-link) .gq-site-nav{display:none;position:absolute;inset:112px 0 auto;z-index:40;flex-direction:column;align-items:stretch;gap:0;background:#f6f3ef;border-bottom:1px solid var(--line);padding:8px 24px 15px;margin:0;font-size:14px}
 .gq-header-inner:has(.gq-logo-link) .gq-site-nav.is-open{display:flex}
 .gq-header-inner:has(.gq-logo-link) .gq-site-nav a{min-height:48px;padding:10px 0;border-bottom:1px solid var(--line)}
 .gq-header-inner:has(.gq-logo-link) .gq-site-nav a:last-child{border-left:0;border-bottom:0;padding-left:0}
 .home-page .opening-inner{padding-top:136px}
}
@media(max-width:1000px){header.site-header:has(.gq-logo-link) nav{flex:0 0 100%;flex-wrap:wrap}}
@media(max-width:560px){
 header .gq-logo-link{width:min(360px,100%);height:152px;flex-basis:auto}
 header.site-nav:has(.gq-logo-link),.gq-header-inner:has(.gq-logo-link){display:grid;grid-template-columns:minmax(0,1fr);align-items:center;height:212px;min-height:212px;gap:0;padding:8px 18px}
 header.site-nav:has(.gq-logo-link) .menu-toggle,.gq-header-inner:has(.gq-logo-link) .gq-menu-toggle{justify-self:end;margin:0}
 header.site-nav:has(.gq-logo-link) #main-nav{top:212px}
 .gq-header-inner:has(.gq-logo-link) .gq-site-nav{top:212px}
 header.site-header:has(.gq-logo-link){display:flex;flex-direction:column;align-items:flex-start}
 header.site-header:has(.gq-logo-link) nav{flex-basis:auto}
 .home-page .opening-inner{padding-top:236px}
 html:has(.site-nav .gq-logo-link){scroll-padding-top:224px}
}
`;
document.head.append(css);

export function mountNavigationLogo(link){
 if(!link||instances.has(link))return instances.get(link);
 const saved={html:link.innerHTML,label:link.getAttribute('aria-label'),description:link.getAttribute('aria-describedby')};
 const abort=new AbortController(),signal=abort.signal,reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const canvas=document.createElement('canvas');canvas.setAttribute('aria-hidden','true');
 const fallback=document.createElement('span');fallback.className='gq-logo-fallback';fallback.textContent='GraniteQuery';fallback.setAttribute('aria-hidden','true');
 const help=document.createElement('span');help.className='gq-logo-help';help.id='gq-logo-help';help.textContent='Animated GraniteQuery logo. Space pauses or resumes the light and turn; Escape pauses. Enter goes to the homepage.';
 link.classList.add('gq-logo-link');link.setAttribute('aria-label','GraniteQuery home');link.setAttribute('aria-describedby',help.id);link.replaceChildren(fallback,canvas,help);
 let material=null,clock=1.5,request=0,previous=0,lastPaint=-Infinity,inView=true,paused=reduced.matches,lost=false,destroyed=false,width=0,height=0,ratio=1;
 const lightSurface=!!link.closest('.library-page,.gq-site-header,header.site-header'),compact=matchMedia('(max-width:560px)');
 function stop(){if(request)cancelAnimationFrame(request);request=0;previous=0}
 function schedule(){if(!request&&!destroyed&&!lost&&!paused&&inView&&!document.hidden)request=requestAnimationFrame(tick)}
 function draw(){
  if(!material||lost||destroyed)return;
  material.draw(clock);
  const turn=reduced.matches?0:Math.sin(clock*.65)*5,tilt=reduced.matches?0:Math.sin(clock*.65+.6)*1.8;
  canvas.style.transform=`perspective(950px) rotateY(${turn}deg) rotateX(${tilt}deg)`;
  Object.assign(link.dataset,{gqReady:'true',gqPlaying:String(!paused&&!document.hidden&&inView),gqTime:clock.toFixed(3),gqMotion:'slow-turn',gqSymbolCount:String(GLYPH_COUNT)});
 }
 function create(){material=createNavigationMaterial(canvas,{get:()=>({width,height,ratio,lightSurface,stacked:compact.matches})});if(!material)throw Error('Canvas unavailable')}
 function resize(){
  if(destroyed||lost)return;
  width=link.clientWidth;height=link.clientHeight;if(!width||!height)return;
  const dpr=Math.min(2,devicePixelRatio||1),nextWidth=Math.round(width*dpr),nextHeight=Math.round(height*dpr);
  if(canvas.width!==nextWidth)canvas.width=nextWidth;if(canvas.height!==nextHeight)canvas.height=nextHeight;
  ratio=dpr;
  try{if(!material)create();material.resize();draw();schedule()}catch{material=null;link.dataset.gqReady='false';stop()}
 }
 function tick(now){request=0;if(destroyed||lost||paused||!inView||document.hidden){previous=0;return}const dt=previous?Math.min(.06,(now-previous)/1000):0;previous=now;clock+=dt;if(now-lastPaint>=1000/24){draw();lastPaint=now}schedule()}
 function setPaused(value){paused=value;stop();draw();schedule()}
 link.addEventListener('keydown',event=>{if(event.key===' '){event.preventDefault();setPaused(!paused)}else if(event.key==='Escape')setPaused(true)},{signal});
 document.addEventListener('visibilitychange',()=>{stop();if(document.hidden)link.dataset.gqPlaying='false';else{draw();schedule()}},{signal});
 reduced.addEventListener('change',event=>{if(event.matches){clock=1.5;setPaused(true)}},{signal});
 canvas.addEventListener('contextlost',()=>{lost=true;link.dataset.gqReady='false';link.dataset.gqPlaying='false';stop()},{signal});
 canvas.addEventListener('contextrestored',()=>{lost=false;material?.destroy();material=null;resize()},{signal});
 const sizeObserver=new ResizeObserver(resize);sizeObserver.observe(link);
 const visibilityObserver=new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;stop();if(inView){draw();schedule()}else link.dataset.gqPlaying='false'},{threshold:.01});visibilityObserver.observe(link);
 const controller={pause:()=>setPaused(true),play:()=>setPaused(false),destroy(){if(destroyed)return;destroyed=true;stop();abort.abort();sizeObserver.disconnect();visibilityObserver.disconnect();material?.destroy();material=null;link.innerHTML=saved.html;link.classList.remove('gq-logo-link');for(const [key,value]of [['aria-label',saved.label],['aria-describedby',saved.description]])value===null?link.removeAttribute(key):link.setAttribute(key,value);for(const key of ['gqReady','gqPlaying','gqTime','gqMotion','gqSymbolCount'])delete link.dataset[key];instances.delete(link)}};
 instances.set(link,controller);resize();return controller;
}

document.querySelectorAll('header.site-nav .wordmark,header.site-header .wordmark,.gq-site-header .gq-wordmark').forEach(mountNavigationLogo);
