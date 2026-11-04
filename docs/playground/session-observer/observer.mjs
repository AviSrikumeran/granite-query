import {FRAMES,PAGES,clampFrame,nextFrame} from './model.mjs?v=session-observer-20261104-1';
const $=selector=>document.querySelector(selector),viewport=$('#mock-viewport'),page=$('#document-page');
const events=[...document.querySelectorAll('[data-event]')],films=[...document.querySelectorAll('[data-film]')];
const reduced=matchMedia('(prefers-reduced-motion:reduce)'),params=new URLSearchParams(location.search);
let selected=clampFrame(params.get('frame')??0),playing=false,timer=null,inView=true,currentPage=null;

function intersectsViewport(){
  const box=$('#observer').getBoundingClientRect();
  const width=document.documentElement.clientWidth,height=document.documentElement.clientHeight;
  return box.width>0&&box.height>0&&box.bottom>0&&box.right>0&&box.top<height&&box.left<width;
}

function positionTarget(){
  const frame=FRAMES[selected],target=$('#'+frame.target);
  if(!target)return;
  const box=target.getBoundingClientRect(),surface=viewport.getBoundingClientRect();
  const left=Math.max(5,box.left-surface.left-5),top=Math.max(17,box.top-surface.top-5);
  const width=Math.min(surface.width-left-5,box.width+10),height=Math.min(surface.height-top-5,box.height+10);
  Object.assign($('#target-ring').style,{left:left+'px',top:top+'px',width:Math.max(0,width)+'px',height:Math.max(0,height)+'px'});
  const x=Math.min(surface.width-87,left+width*.72),y=Math.min(surface.height-38,top+height*.65);
  Object.assign($('#replay-cursor').style,{left:Math.max(9,x)+'px',top:Math.max(9,y)+'px'});
}

function render({announce=false}={}){
  const frame=FRAMES[selected];
  if(currentPage!==frame.page){page.innerHTML=PAGES[frame.page];currentPage=frame.page;}
  for(const button of events)button.setAttribute('aria-pressed',String(Number(button.dataset.event)===selected));
  for(const button of films)button.setAttribute('aria-pressed',String(Number(button.dataset.film)===selected));
  $('#address').textContent=frame.address;
  $('#target-label').textContent=`${frame.id} / ${frame.action}`;
  $('#frame-caption').textContent=frame.caption;$('#frame-id').textContent=frame.id;
  $('#frame-counter').textContent=`${String(selected+1).padStart(2,'0')} / 05`;
  $('#transport-position').textContent=`Frame ${selected+1} of ${FRAMES.length}`;
  $('#previous').disabled=selected===0;$('#next').disabled=selected===FRAMES.length-1;
  $('#scrub').value=String(selected);$('#scrub').setAttribute('aria-valuetext',`${frame.id}: ${frame.title}`);
  $('#detail-id').textContent=`Selected event / ${frame.id}`;$('#detail-title').textContent=frame.title;
  $('#detail-input').textContent=frame.input;$('#detail-change').textContent=frame.change;$('#detail-outcome').textContent=frame.outcome;
  Object.assign($('#observer').dataset,{selected:frame.id,page:frame.page,target:frame.target});
  positionTarget();
  requestAnimationFrame(positionTarget);
  if(announce)$('#announcement').textContent=`${frame.id}. ${frame.title}. ${frame.change}`;
}

function setPlaying(value,{complete=false}={}){
  const wasPlaying=playing;
  playing=value;
  $('#play-text').textContent=playing?'Pause replay':'Replay 5 frames';
  $('#play-icon').textContent=playing?'Ⅱ':'▷';
  $('#session-state').textContent=playing?'Playing / Authored replay':complete?'Completed / Authored replay':'Paused / Authored replay';
  $('#observer').dataset.playing=String(playing);
  $('#observer').dataset.completed=String(complete);
  if(playing)$('#announcement').textContent='Replaying five authored frames. Press Escape to pause.';
  else if(wasPlaying){const frame=FRAMES[selected];$('#announcement').textContent=`Replay ${complete?'finished':'paused'} at ${frame.id}. ${frame.title}.`;}
  schedule();
}

function select(index,{manual=true,focus=null}={}){
  if(manual)setPlaying(false);
  selected=clampFrame(index);render({announce:manual});
  if(focus==='event')events[selected].focus({preventScroll:true});
  if(focus==='film')films[selected].focus({preventScroll:true});
}

function schedule(){
  if(timer!==null){clearTimeout(timer);timer=null;}
  if(!playing)return;
  // Explicit playback reads current geometry; an older observer callback cannot
  // leave the control saying Playing without an advancing timer.
  inView=intersectsViewport();
  if(document.hidden||!inView){setPlaying(false);return;}
  timer=setTimeout(()=>{
    timer=null;
    if(selected===FRAMES.length-1){setPlaying(false,{complete:true});return;}
    select(nextFrame(selected),{manual:false});schedule();
  },3000);
}

for(const group of [events,films])group.forEach((button,index)=>{
  button.addEventListener('click',()=>select(index));
  button.addEventListener('keydown',event=>{
    let next;
    if(event.key==='ArrowDown'||event.key==='ArrowRight')next=Math.min(FRAMES.length-1,index+1);
    else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=Math.max(0,index-1);
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=FRAMES.length-1;
    else return;
    event.preventDefault();select(next,{focus:group===events?'event':'film'});
  });
});
page.addEventListener('click',event=>{const button=event.target.closest('[data-frame]');if(button)select(Number(button.dataset.frame));});
$('#previous').addEventListener('click',()=>select(selected-1));$('#next').addEventListener('click',()=>select(selected+1));
$('#scrub').addEventListener('input',()=>select(Number($('#scrub').value)));
$('#play').addEventListener('click',()=>{if(playing){setPlaying(false);return;}select(0);setPlaying(true);});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPlaying(false);});
document.addEventListener('visibilitychange',()=>{if(document.hidden)setPlaying(false);});
reduced.addEventListener('change',event=>{if(event.matches)setPlaying(false);});
new IntersectionObserver(()=>{
  inView=intersectsViewport();
  if(!inView)setPlaying(false);
  else if(playing&&timer===null)schedule();
},{threshold:.04}).observe($('#observer'));
new ResizeObserver(positionTarget).observe(viewport);
render();setPlaying(false);
