import {RECORD,PASSAGES,passageIndex,evidenceFor} from './model.mjs?v=source-lens-20261104-1';

const $ = selector => document.querySelector(selector);
const passages = [...document.querySelectorAll('.passage')];
const steps = [...document.querySelectorAll('[data-step]')];
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const band = $('#inspection-band');
const pane = $('#passages');
const play = $('#play');
let selected = 0;
let playing = false;
let inView = true;
let timer = null;
let view = 'readable';
let pointerSelected = -1;
let pinned = false;

function updateInspectionState() {
  const mode=$('#scan-state');
  mode.disabled=!pinned&&!playing;
  mode.textContent=playing?'Scan · Follow pointer':pinned?'Pinned · Follow pointer':'Pointer preview';
  mode.title=playing?'Stop scanning and resume pointer previews':pinned?'Release the pinned selection and resume pointer previews':'Hover previews passages; click or use the keyboard to pin a selection';
  $('#instrument').dataset.pinned=String(pinned);
}

function setPinned(value) {
  pinned=value;
  updateInspectionState();
}

function positionBand() {
  const passage = passages[selected];
  band.style.top = `${passage.offsetTop}px`;
  band.style.height = `${passage.offsetHeight}px`;
}

function render({announce=false,animate=true}={}) {
  const passage = PASSAGES[selected];
  passages.forEach((button,i) => button.setAttribute('aria-pressed',String(i===selected)));
  steps.forEach((button,i) => button.setAttribute('aria-pressed',String(i===selected)));
  $('#record-position').textContent = `${passage.line} / 04`;
  $('#field-key').textContent = passage.key;
  $('#claim-title').textContent = passage.title;
  $('#claim-explanation').textContent = passage.explanation;
  $('#claim-value').textContent = passage.value;
  $('#source-link').href = `#source-${passage.id}`;
  $('#source-link').replaceChildren(document.createTextNode(`Passage ${passage.line} `));
  const arrow = document.createElement('span');
  arrow.textContent = '↖';
  arrow.setAttribute('aria-hidden','true');
  $('#source-link').append(arrow);
  $('#source-quote').textContent = passage.quote;
  $('#quote-index').textContent = passage.line;
  $('#claim-boundary').textContent = passage.boundary;
  $('#foot-count').textContent = `${selected+1} of ${PASSAGES.length}`;
  $('#json-output').textContent = JSON.stringify(evidenceFor(selected),null,2);
  $('#instrument').dataset.selected = passage.id;
  $('#instrument').dataset.presentation = view;
  positionBand();
  if(animate && !reduced.matches){
    $('#output-content').classList.remove('changed');
    requestAnimationFrame(() => $('#output-content').classList.add('changed'));
  }
  if(announce) $('#announcement').textContent = `Passage ${passage.line}: ${passage.title} ${passage.value}.`;
}

function select(index,{user=false,focus=false,pin=user}={}) {
  const next = passageIndex(index);
  if(user){setPlaying(false);setPinned(pin);}
  if(next!==selected){selected=next;render({announce:user});}
  if(focus) passages[selected].focus({preventScroll:true});
}

function schedule() {
  if(timer!==null){clearTimeout(timer);timer=null;}
  if(!playing || document.hidden || !inView)return;
  timer=setTimeout(() => {
    timer=null;
    select((selected+1)%PASSAGES.length);
    schedule();
  },4800);
}

function setPlaying(value) {
  playing=value;
  play.setAttribute('aria-pressed',String(playing));
  $('#play-text').textContent=playing?'Pause scan':'Play scan';
  play.querySelector('.play-icon').textContent=playing?'Ⅱ':'▷';
  updateInspectionState();
  $('#instrument').dataset.playing=String(playing);
  schedule();
}

passages.forEach((button,index)=>{
  button.addEventListener('click',()=>select(index,{user:true}));
  button.addEventListener('focus',()=>select(index,{user:true}));
  button.addEventListener('pointerenter',event=>{
    if(event.pointerType==='touch'||pinned)return;
    if(pointerSelected!==index){pointerSelected=index;select(index,{user:true,pin:false});}
  });
  button.addEventListener('keydown',event=>{
    let next;
    if(event.key==='ArrowDown'||event.key==='ArrowRight')next=(selected+1)%PASSAGES.length;
    else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=(selected+PASSAGES.length-1)%PASSAGES.length;
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=PASSAGES.length-1;
    else return;
    event.preventDefault();
    select(next,{user:true,focus:true});
  });
});
pane.addEventListener('pointerleave',()=>{pointerSelected=-1;});
steps.forEach((button,index)=>button.addEventListener('click',()=>select(index,{user:true})));
play.addEventListener('click',()=>{if(!playing)setPinned(false);setPlaying(!playing);});
$('#scan-state').addEventListener('click',()=>{
  setPlaying(false);
  setPinned(false);
  pointerSelected=-1;
  $('#announcement').textContent='Pointer preview resumed. Click a passage to pin it.';
});

$('#source-link').addEventListener('click',event=>{
  event.preventDefault();
  const capturedIndex=selected;
  setPinned(true);
  setPlaying(false);
  const source=passages[capturedIndex];
  source.scrollIntoView({behavior:reduced.matches?'instant':'smooth',block:'center'});
  source.focus({preventScroll:true});
  $('#announcement').textContent=`Source passage ${PASSAGES[capturedIndex].line} focused and pinned.`;
});

for(const next of ['readable','json'])$('#view-'+next).addEventListener('click',()=>{
  setPlaying(false);
  setPinned(true);
  view=next;
  $('#view-readable').setAttribute('aria-pressed',String(view==='readable'));
  $('#view-json').setAttribute('aria-pressed',String(view==='json'));
  $('#readable-view').hidden=view!=='readable';
  $('#json-view').hidden=view!=='json';
  $('#instrument').dataset.presentation=view;
});

document.addEventListener('keydown',event=>{if(event.key==='Escape')setPlaying(false);});
document.addEventListener('visibilitychange',schedule);
reduced.addEventListener('change',event=>{if(event.matches)setPlaying(false);});
new ResizeObserver(positionBand).observe(pane);
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;schedule();},{threshold:.05}).observe($('#instrument'));

// A fixed review URL chooses a passage without starting motion.
const params=new URLSearchParams(location.search);
const held=PASSAGES.findIndex(p=>p.id===params.get('passage'));
if(held>=0){selected=held;pinned=true;}
render({animate:false});
setPlaying(false);
