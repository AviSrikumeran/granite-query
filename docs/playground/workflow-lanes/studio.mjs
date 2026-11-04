import {STEPS,stateAt,activeStep} from './trace.mjs?v=workflow-20261104-1';
const $=s=>document.querySelector(s), rows=$('#rows'), range=$('#progress'), play=$('#play'), reduced=matchMedia('(prefers-reduced-motion: reduce)');
let progress=100,selected='walkthrough',playing=false,visible=!document.hidden,inView=true,frame=0,last=0;
const duration=18000;
const buttons=STEPS.map((step,index)=>{
  const button=document.createElement('button');button.type='button';button.className='row';button.style.setProperty('--depth',step.depth);button.style.setProperty('--start',step.start);button.style.setProperty('--length',step.end-step.start);button.dataset.id=step.id;button.setAttribute('aria-pressed',String(index===0));button.setAttribute('aria-label',step.name+', '+step.type+', position '+step.start+' to '+step.end+' percent');
  const label=document.createElement('span');label.className='step-label';const copy=document.createElement('span');copy.className='label-copy';const title=document.createElement('strong');title.textContent=step.name;const type=document.createElement('small');type.textContent=step.type;copy.append(title,type);label.append(copy);
  const cell=document.createElement('span');cell.className='bar-cell';const bar=document.createElement('span');bar.className='bar';const fill=document.createElement('i');bar.append(fill);cell.append(bar);button.append(label,cell);rows.append(button);
  button.addEventListener('click',()=>select(step.id));button.addEventListener('keydown',event=>{let next=index;if(event.key==='ArrowDown'||event.key==='ArrowRight')next=(index+1)%STEPS.length;else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=(index+STEPS.length-1)%STEPS.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=STEPS.length-1;else return;event.preventDefault();select(STEPS[next].id);buttons[next].focus();});
  return button;
});
function select(id){
  const index=STEPS.findIndex(step=>step.id===id),step=STEPS[index];if(!step)return;selected=id;
  buttons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.id===id)));
  $('#step-number').textContent=String(index).padStart(2,'0')+' / 05';$('#step-title').textContent=step.name;$('#description').textContent=step.description;$('#input').textContent=step.input;$('#output').textContent=step.output;$('#record-title').textContent=step.record;$('#excerpt').textContent=step.excerpt;
  const fields=$('#fields');fields.replaceChildren();for(const [key,value] of step.fields){const div=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value;div.append(dt,dd);fields.append(div);}
  $('#source').href=step.source;$('#source').replaceChildren(document.createTextNode(step.sourceLabel+' '));const arrow=document.createElement('span');arrow.setAttribute('aria-hidden','true');arrow.textContent='↗';$('#source').append(arrow);
}
function paint(){
  const states=stateAt(progress);states.forEach((step,index)=>{buttons[index].dataset.state=step.state;buttons[index].style.setProperty('--fraction',step.fraction);});
  $('#playhead').style.left=progress+'%';$('#playhead').dataset.edge=String(progress>87);$('#playhead-label').textContent=Math.round(progress)+'%';range.value=String(Math.round(progress));$('#position').value=Math.round(progress)+'%';range.setAttribute('aria-valuetext',Math.round(progress)+' percent of the illustrative sequence');
  document.body.dataset.progress=progress.toFixed(2);document.body.dataset.playing=String(playing);
}
function schedule(){if(playing&&visible&&inView&&!frame)frame=requestAnimationFrame(tick);}
function setPlaying(value){playing=value;last=0;if(frame){cancelAnimationFrame(frame);frame=0;}play.replaceChildren(document.createTextNode(playing?'Pause replay':progress>=100?'Replay sequence':'Continue replay'));const arrow=document.createElement('span');arrow.setAttribute('aria-hidden','true');arrow.textContent=playing?'Ⅱ':'↗';play.append(arrow);play.setAttribute('aria-label',playing?'Pause illustrative replay':progress>=100?'Replay illustrative sequence':'Continue illustrative replay');$('#playback-state').textContent=playing?'Replaying authored steps · not live activity':progress>=100?'Complete view · select any step':'Paused · '+Math.round(progress)+'% of the illustrative sequence';paint();schedule();}
function tick(now){frame=0;if(!playing||!visible||!inView){last=0;return;}const dt=last?Math.min(100,now-last):0;last=now;progress=Math.min(100,progress+dt/duration*100);paint();if(progress>=100){setPlaying(false);select('answer');return;}schedule();}
play.addEventListener('click',()=>{if(playing)setPlaying(false);else{if(progress>=100)progress=0;setPlaying(true);}});
$('#reset').addEventListener('click',()=>{progress=100;setPlaying(false);select('walkthrough');});
range.addEventListener('input',()=>{progress=Number(range.value);setPlaying(false);select(activeStep(progress).id);});
const region=$('.trace-region'),rail=$('#time-rail');region.addEventListener('pointermove',event=>{if(event.pointerType==='touch'||reduced.matches)return;const rect=rail.getBoundingClientRect(),value=Math.max(0,Math.min(100,(event.clientX-rect.left)/rect.width*100));if(event.clientX<rect.left||event.clientX>rect.right){region.classList.remove('is-hovering');return;}$('#hoverhead').style.left=value+'%';$('#hover-label').textContent=Math.round(value)+'%';region.classList.add('is-hovering');});region.addEventListener('pointerleave',()=>region.classList.remove('is-hovering'));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPlaying(false);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;last=0;if(!visible&&frame){cancelAnimationFrame(frame);frame=0;}else schedule();});
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;last=0;if(!inView&&frame){cancelAnimationFrame(frame);frame=0;}else schedule();}).observe($('.console'));
reduced.addEventListener('change',event=>{if(event.matches){region.classList.remove('is-hovering');setPlaying(false);}});
select('walkthrough');setPlaying(false);
