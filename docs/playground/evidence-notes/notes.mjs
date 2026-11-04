const $=selector=>document.querySelector(selector);
const workspace=$('#workspace'),rail=$('#evidence-rail'),list=$('#source-list'),editor=$('.editor');
const claims=[...document.querySelectorAll('[data-claim]')],reduced=matchMedia('(prefers-reduced-motion: reduce)'),narrow=matchMedia('(max-width:760px)');
let records=[],selected='baseline',reading=false,queued=0;
function schedule(){if(!queued)queued=requestAnimationFrame(()=>{queued=0;positionNotes();});}
function select(id,{announce=false,scroll=false}={}){
  if(reading||!records.some(record=>record.id===id))return;
  selected=id;const current=records.find(record=>record.id===id);
  for(const claim of claims)claim.setAttribute('aria-expanded',String(claim.dataset.claim===id));
  for(const note of list.children){const active=note.dataset.source===id;note.classList.toggle('selected',active);note.querySelector('.source-title').setAttribute('aria-expanded',String(active));note.querySelector('.source-body').hidden=!active;}
  $('#selected-count').textContent=String(current.number).padStart(2,'0')+' / 04';
  if(announce)$('#selection-status').textContent='Source '+current.number+' selected · '+current.title;
  if(scroll)document.querySelector('[data-claim="'+id+'"]').scrollIntoView({behavior:reduced.matches?'instant':'smooth',block:'center'});
  schedule();
}
function positionNotes(){
  if(reading||!records.length)return;
  const canvas=workspace.getBoundingClientRect(),railRect=rail.getBoundingClientRect();
  const selectedClaim=document.querySelector('[data-claim="'+selected+'"]');
  let bottom=45;
  for(const record of records){const claim=document.querySelector('[data-claim="'+record.id+'"]'),note=document.querySelector('[data-source="'+record.id+'"]'),rect=claim.getBoundingClientRect();const top=Math.max(bottom,rect.top-railRect.top-10);note.style.top=top+'px';bottom=top+note.offsetHeight+17;}
  rail.style.minHeight=(bottom+75)+'px';
  if(narrow.matches)return;
  const anchor=selectedClaim.getBoundingClientRect(),note=document.querySelector('[data-source="'+selected+'"] .source-title').getBoundingClientRect();
  const x1=anchor.right-canvas.left+8,y1=anchor.top-canvas.top+anchor.height/2,x2=note.left-canvas.left-9,y2=note.top-canvas.top+10;
  const distance=Math.max(12,(x2-x1)*.45);
  $('#connection').setAttribute('d',`M ${x1} ${y1} C ${x1+distance} ${y1},${x2-distance} ${y2},${x2} ${y2}`);$('#endpoint').setAttribute('cx',x2);$('#endpoint').setAttribute('cy',y2);
}
function makeNote(record){
  const note=document.createElement('section');note.className='source-note';note.id='source-'+record.id;note.dataset.source=record.id;note.setAttribute('aria-label','Source '+record.number+': '+record.title);
  const button=document.createElement('button');button.type='button';button.className='source-title';button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','body-'+record.id);
  for(const [className,text] of [['note-number',String(record.number).padStart(2,'0')],['title',record.title],['note-chevron','↗']]){const span=document.createElement('span');span.className=className;span.textContent=text;button.append(span);}
  const body=document.createElement('div');body.id='body-'+record.id;body.className='source-body';body.hidden=true;
  const kind=document.createElement('p');kind.className='record-key';kind.textContent=record.kind.toUpperCase()+' / EXAMPLE RECORD';
  const quote=document.createElement('blockquote');quote.textContent=record.quote;
  const detail=document.createElement('p');detail.textContent=record.detail;
  const actions=document.createElement('div');actions.className='source-actions';
  const raw=document.createElement('button');raw.type='button';raw.textContent='Show record';raw.setAttribute('aria-expanded','false');
  const link=document.createElement('a');link.href='./records.json';link.target='_blank';link.rel='noopener';link.textContent='Example file ↗';
  const pre=document.createElement('pre');pre.textContent=JSON.stringify(record.record,null,2);pre.hidden=true;
  raw.addEventListener('click',()=>{pre.hidden=!pre.hidden;raw.textContent=pre.hidden?'Show record':'Hide record';raw.setAttribute('aria-expanded',String(!pre.hidden));schedule();});
  button.addEventListener('click',()=>select(record.id,{announce:true,scroll:true}));
  actions.append(raw,link);body.append(kind,quote,detail,actions,pre);note.append(button,body);return note;
}
for(const claim of claims){claim.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch')select(claim.dataset.claim);});claim.addEventListener('focus',()=>select(claim.dataset.claim,{announce:true}));claim.addEventListener('click',()=>{select(claim.dataset.claim,{announce:true});if(narrow.matches)document.querySelector('[data-source="'+claim.dataset.claim+'"]').scrollIntoView({behavior:reduced.matches?'instant':'smooth',block:'center'});});claim.addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const index=claims.indexOf(claim),next=event.key==='Home'?0:event.key==='End'?claims.length-1:(index+(['ArrowDown','ArrowRight'].includes(event.key)?1:-1)+claims.length)%claims.length;claims[next].focus();});}
function setReading(value){reading=value;editor.classList.toggle('reading',value);$('#annotated').setAttribute('aria-pressed',String(!value));$('#reading').setAttribute('aria-pressed',String(value));for(const claim of claims){claim.disabled=value;claim.tabIndex=value?-1:0;}$('#selection-status').textContent=value?'Reading view · Evidence notes hidden':'Source '+(records.find(record=>record.id===selected)?.number??1)+' selected · '+(records.find(record=>record.id===selected)?.title??'Loading');if(!value)schedule();}
$('#annotated').addEventListener('click',()=>setReading(false));$('#reading').addEventListener('click',()=>setReading(true));
for(const [id,direction] of [['previous',-1],['next',1]])$('#'+id).addEventListener('click',()=>{if(!records.length)return;const index=records.findIndex(record=>record.id===selected),next=records[(index+direction+records.length)%records.length];select(next.id,{announce:true,scroll:true});});
window.addEventListener('resize',schedule);narrow.addEventListener('change',schedule);new ResizeObserver(schedule).observe(workspace);
try{const response=await fetch('./records.json');if(!response.ok)throw Error('Example records could not be loaded.');const fixture=await response.json();if(fixture.kind!=='illustrative-interface-fixture'||fixture.records.length!==claims.length||fixture.records.some((record,index)=>record.id!==claims[index].dataset.claim))throw Error('The example records do not match this document.');records=fixture.records;list.replaceChildren(...records.map(makeNote));select(selected);document.documentElement.dataset.state='ready';}
catch(error){$('#selection-status').textContent=error.message+' The document remains readable.';$('#selected-count').textContent='Unavailable';$('#connection').setAttribute('d','');$('#endpoint').setAttribute('r','0');document.documentElement.dataset.state='unavailable';}
