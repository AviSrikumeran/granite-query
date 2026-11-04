import {STEPS,LAYOUTS,indexOfStep,nextStep} from './model.mjs?v=code-map-20261104-1';
const $=selector=>document.querySelector(selector);
const code=[...document.querySelectorAll('[data-step]')],regions=[...document.querySelectorAll('[data-region]')];
const narrow=matchMedia('(max-width:760px)'),reduced=matchMedia('(prefers-reduced-motion:reduce)');
const params=new URLSearchParams(location.search);
let selected=indexOfStep(params.get('step')),playing=false,timer=null,inView=true;

function render({announce=false}={}){
  const step=STEPS[selected];
  for(const item of [...code,...regions])item.setAttribute('aria-pressed',String((item.dataset.step??item.dataset.region)===step.id));
  regions.forEach(region=>region.classList.toggle('active',region.dataset.region===step.id));
  $('#wire-scope').classList.toggle('active',step.id==='scope'||step.id==='compare');
  $('#wire-budget').classList.toggle('active',step.id==='budget'||step.id==='compare');
  $('#wire-qualify').classList.toggle('active',step.id==='compare'||step.id==='qualify');
  $('#view-count').textContent=`${step.number} / 04`;
  $('#selected-number').textContent=step.number;
  $('#selected-artifact').textContent=step.artifact;
  $('#selected-title').textContent=step.statement;
  $('#selected-explanation').textContent=step.explanation;
  $('#selected-boundary').textContent=step.boundary;
  $('#current-step').textContent=`${step.number} · ${step.label}`;
  $('#previous').disabled=selected===0;
  $('#next').disabled=selected===STEPS.length-1;
  $('#instrument').dataset.selected=step.id;
  if(announce)$('#announcement').textContent=`${step.number}. ${step.label}. ${step.statement}`;
}

function setPlaying(value){
  playing=value;
  $('#replay-text').textContent=playing?'Pause guided view':'Guide through 4 records';
  $('#playback-status').textContent=playing?'Guided view · 4 records':'Manual view';
  $('#instrument').dataset.playing=String(playing);
  schedule();
}

function select(index,{manual=true,focus=null}={}){
  if(manual)setPlaying(false);
  selected=Math.max(0,Math.min(STEPS.length-1,index));
  render({announce:manual});
  if(focus==='code')code[selected].focus({preventScroll:true});
  if(focus==='diagram')regions[selected].focus({preventScroll:true});
}

function schedule(){
  if(timer!==null){clearTimeout(timer);timer=null;}
  if(!playing||document.hidden||!inView)return;
  timer=setTimeout(()=>{
    timer=null;
    if(selected===STEPS.length-1){setPlaying(false);return;}
    select(nextStep(selected),{manual:false});
    schedule();
  },3600);
}

for(const group of [code,regions])group.forEach((item,index)=>{
  item.addEventListener('click',()=>select(index));
  item.addEventListener('keydown',event=>{
    let next;
    if(event.key==='ArrowDown'||event.key==='ArrowRight')next=Math.min(STEPS.length-1,index+1);
    else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=Math.max(0,index-1);
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=STEPS.length-1;
    else if(group===regions&&(event.key==='Enter'||event.key===' '))next=index;
    else return;
    event.preventDefault();select(next,{focus:group===code?'code':'diagram'});
  });
});
$('#previous').addEventListener('click',()=>select(selected-1));
$('#next').addEventListener('click',()=>select(selected+1));
$('#replay').addEventListener('click',()=>{
  if(playing){setPlaying(false);return;}
  select(0);setPlaying(true);
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPlaying(false);});
document.addEventListener('visibilitychange',schedule);
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;schedule();},{threshold:.04}).observe($('#instrument'));
reduced.addEventListener('change',event=>{if(event.matches)setPlaying(false);});
function layout(){
  const config=narrow.matches?LAYOUTS.narrow:LAYOUTS.wide;
  $('#diagram').setAttribute('viewBox',config.viewBox);
  for(const [id,point] of Object.entries(config.positions))$('#region-'+id).setAttribute('transform',`translate(${point.join(' ')})`);
  for(const [id,path] of Object.entries(config.paths))$('#wire-'+id).setAttribute('d',path);
  $('#instrument').dataset.layout=narrow.matches?'narrow':'wide';
}
narrow.addEventListener('change',layout);
layout();render();setPlaying(false);
