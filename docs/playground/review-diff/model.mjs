export function derivePatch(input){
  if(input?.kind!=='illustrative-change-review'||!Array.isArray(input.context)||!Array.isArray(input.changes)||!Array.isArray(input.ending)||input.changes.length!==4)throw Error('The illustrative review record is invalid.');
  if(new Set(input.changes.map(c=>c.id)).size!==input.changes.length)throw Error('Change identities must be unique.');
  let oldLine=1,newLine=1;const before=[],after=[],sections=[];
  const context=text=>{const row={kind:'context',old:oldLine++,next:newLine++,text};before.push(text);after.push(text);return row;};
  sections.push({id:'intro',rows:input.context.map(context)});
  for(const [index,change]of input.changes.entries()){
    if(!change.id||!change.title||!change.why||!change.protects||!Array.isArray(change.before)||!Array.isArray(change.after)||!change.before.length||!change.after.length||[...change.before,...change.after].some(line=>typeof line!=='string'))throw Error('A change is incomplete.');
    const oldStart=oldLine,newStart=newLine;
    const removed=change.before.map(text=>{before.push(text);return{kind:'removed',old:oldLine++,next:null,text};}),added=change.after.map(text=>{after.push(text);return{kind:'added',old:null,next:newLine++,text};});
    const split=Array.from({length:Math.max(removed.length,added.length)},(_,i)=>({old:removed[i]??null,next:added[i]??null}));
    sections.push({...change,index,oldStart,newStart,rows:[...removed,...added],split});
    if(index<input.changes.length-1)sections.push({id:'gap-'+index,rows:[context('')]});
  }
  sections.push({id:'ending',rows:input.ending.map(context)});
  return {file:input.file,changes:sections.filter(s=>s.index!==undefined),sections,before:before.join('\n'),after:after.join('\n'),removed:input.changes.reduce((sum,c)=>sum+c.before.length,0),added:input.changes.reduce((sum,c)=>sum+c.after.length,0)};
}
