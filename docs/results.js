// Only aggregate, allowlisted results are exposed by status.json.
async function refreshResults(){
  try{
    const response=await fetch('status.json?t='+Date.now(),{cache:'no-store'});
    if(!response.ok)return;
    const snapshot=await response.json(),result=snapshot.comparison;
    if(!result)return;
    const body=document.getElementById('result-rows');body.replaceChildren();
    for(const name of ['baseline','ranked','random']){
      const m=result.metrics[name],row=document.createElement('tr');
      const values=[name==='baseline'?'Original Granite':name==='ranked'?'BM25 selected':'Random selected',
        `${m.numeric_correct}/${m.count} (${(100*m.numeric_correct/m.count).toFixed(2)}%)`,
        `${m.strict_format_correct}/${m.count}`,String(m.truncated),
        m.supervised_tokens===undefined?'—':m.supervised_tokens.toLocaleString(),
        (m.latency_seconds_total/m.count).toFixed(2)];
      for(const value of values){const cell=document.createElement('td');cell.textContent=value;cell.style.padding='12px 14px';row.append(cell)}
      body.append(row);
    }
    const delta=result.ranked_minus_random_correct;
    document.getElementById('result-summary').textContent=`Ranked minus random: ${delta>0?'+':''}${delta} correct answers out of ${result.count}. One question changes accuracy by 6.25 percentage points. This is a single-seed development pilot; final-test generalization is not established.`;
    const caveats=document.getElementById('result-limitations');caveats.replaceChildren();
    for(const text of result.limitations){const li=document.createElement('li');li.textContent=text;caveats.append(li)}
    document.getElementById('results-panel').hidden=false;
  }catch(error){/* Keep any last successfully rendered results. */}
}
refreshResults();setInterval(refreshResults,60000);
async function refreshResearch(){
  try{const response=await fetch('research.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)return;
    const data=await response.json();if(data.token_matched32768){const t=data.token_matched32768;document.getElementById('controlled-panel').hidden=false;document.getElementById('controlled-image').src='figures/token-matched-accuracy.svg?t='+Date.now();document.getElementById('controlled-summary').textContent=t.completed_arms+' of '+t.planned_arms+' arms complete. '+Object.entries(t.correct).map(([name,count])=>name+': '+count+'/64').join('; ')+'. Matched controls and repeated seeds are needed before claiming a selection advantage.';}if(['completed','partial'].includes(data.matched64?.stage)){
      document.getElementById('larger-image').src='figures/matched64-accuracy.svg?t='+Date.now();
      document.getElementById('larger-figure').hidden=false;
      const counts=data.matched64.correct||{};
      const measured=['DeepSeek Pro','baseline','ranked32','random32','Granite full120'].filter(name=>Number.isInteger(counts[name])).map(name=>`${({baseline:'Original Granite',ranked32:'BM25-trained Granite',random32:'Random-trained Granite'})[name]||name}: ${counts[name]}/64`).join('; ');
      document.getElementById('research-phase').textContent=data.matched64.stage==='partial'
        ? 'The larger matched baseline is complete: DeepSeek 63/64 and original Granite 58/64 on the same questions. The trained checkpoints are still being recovered and evaluated. This is not an improvement from the earlier 16-question score; it is a different evaluation set.'
        : data.training120?.stage==='completed'
        ? measured+'. The 120-example round is complete; these are development results, with final evaluation still pending.'
        : measured+'. Both32-example adapters regressed from the original model. The120-example round is '+(data.training120?.stage==='queued'?'queued':'running')+'; its accuracy has not been measured yet.';
    }
  }catch(error){/* Newer figures remain hidden until measured results exist. */}
}
refreshResearch();setInterval(refreshResearch,60000);
