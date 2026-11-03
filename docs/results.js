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
    const data=await response.json();if(data.matched64?.stage==='completed'){
      document.getElementById('larger-image').src='figures/matched64-accuracy.svg?t='+Date.now();
      document.getElementById('larger-figure').hidden=false;
      document.getElementById('research-phase').textContent=data.training120?.stage==='completed'
        ? 'The shared 64-question teacher/student evaluation and the 120-example training round are complete. The chart below shows their measured results.'
        : 'The shared 64-question benchmark is complete. The 120-example training round is queued or running; no improvement is claimed before its evaluation finishes.';
    }
  }catch(error){/* Newer figures remain hidden until measured results exist. */}
}
refreshResearch();setInterval(refreshResearch,60000);
