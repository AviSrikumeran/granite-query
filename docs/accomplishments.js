async function refreshAccomplishments(){
  try{
    const response=await fetch('project-status.json?t='+Date.now(),{cache:'no-store'});
    if(!response.ok)return;
    const data=await response.json(),get=id=>document.getElementById(id);
    get('audit-summary').textContent=data.summary;
    get('audit-title').textContent=data.accuracy_improved?'Measured development gain; final-test validation pending.':'Working prototype. Accuracy gain not demonstrated.';
    get('audit-model').textContent=data.model.name+' · '+data.model.training_method;
    const render=(id,items,withLinks=false)=>{
      const list=get(id);list.replaceChildren();
      for(const item of items){const li=document.createElement('li');li.style.marginBottom='16px';
        const title=document.createElement('strong');title.textContent=item.title||item.name;
        const detail=document.createElement('p');detail.style.margin='3px 0';detail.className='muted';detail.textContent=item.detail||item.used_for;
        li.append(title);if(item.status){const status=document.createElement('span');status.textContent=' · '+item.status.replaceAll('_',' ');status.className=item.status==='failed'?'failed':'label';li.append(status)}
        li.append(detail);const url=item.evidence_url||(item.actual_source?.startsWith('https://')?item.actual_source:null);if(withLinks&&url){const link=document.createElement('a');link.href=url;link.textContent='View source / evidence ↗';link.style.fontSize='13px';li.append(link)}
        list.append(li);
      }
    };
    render('audit-completed',data.completed,true);render('audit-current',data.current_work);render('audit-datasets',data.dataset_coverage,true);
    const missing=get('audit-missing');missing.replaceChildren();for(const text of data.not_done){const li=document.createElement('li');li.textContent=text;missing.append(li)}
    get('audit-updated').textContent='Evidence checked: '+new Date(data.updated_at_utc).toLocaleString();
    const active=data.current_work.find(x=>x.status==='running')||data.current_work.find(x=>x.status==='queued');
    if(active){get('stage').textContent=active.title;get('next').textContent=active.detail}
  }catch(error){/* Preserve last rendered evidence and keep static summary readable. */}
}
refreshAccomplishments();setInterval(refreshAccomplishments,60000);
