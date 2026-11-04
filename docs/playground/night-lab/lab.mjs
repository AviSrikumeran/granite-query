const list=document.querySelector('#study-list');
const labels={queued:'Queued',building:'In progress',verifying:'Being checked',ready:'Ready to try',partial:'Saved partial',blocked:'Blocked'};
try{
  const response=await fetch('./studies.json',{cache:'no-store'});if(!response.ok)throw Error('The saved index could not be loaded.');
  const data=await response.json();if(!Array.isArray(data.studies))throw Error('The study list needs review.');
  const ready=data.studies.filter(s=>s.status==='ready');
  document.querySelector('#ready-count').textContent=ready.length+' working '+(ready.length===1?'study':'studies');
  document.querySelector('#updated').textContent=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(new Date(data.updated_at));
  document.querySelector('#summary').textContent=ready.length+' ready · '+data.studies.filter(s=>['building','verifying'].includes(s.status)).length+' in progress · '+data.studies.filter(s=>s.status==='queued').length+' queued';
  for(const study of data.studies){
    const row=document.createElement('li');row.className='study';
    const number=document.createElement('span');number.className='number';number.setAttribute('aria-hidden','true');
    const text=document.createElement('div'),title=document.createElement('h3'),purpose=document.createElement('p'),reference=document.createElement('a');
    title.textContent=study.title;purpose.className='purpose';purpose.textContent=study.purpose;
    reference.className='reference';reference.textContent='Reference: '+study.reference_company+' ↗';reference.href=study.reference_url;reference.target='_blank';reference.rel='noopener';text.append(title,purpose,reference);
    const actions=document.createElement('div');actions.className='study-actions';const status=document.createElement('span');status.className='state'+(study.status==='ready'?' ready':'');status.textContent=labels[study.status]??'Review pending';actions.append(status);
    if(study.status==='ready'&&/^\.\.\/[a-z0-9-]+\/$/.test(study.url??'')){const a=document.createElement('a');a.className='open';a.href=study.url;a.textContent='Try the study ↗';a.setAttribute('aria-label','Try '+study.title);actions.append(a);}
    if(study.review){const a=document.createElement('a');a.className='review';a.href=study.review;a.textContent='Build notes ↗';a.target='_blank';a.rel='noopener';actions.append(a);}
    row.append(number,text,actions);list.append(row);
  }
}catch(error){document.querySelector('#ready-count').textContent='Index unavailable';document.querySelector('#summary').textContent=error.message+' Open All experiments for released studies.';}
