export const RECORD=Object.freeze({
  record_id:'demo-evidence-001',
  kind:'authored_interface_fixture',
  question:'What supports this finding?',
  finding:'A research finding should travel with its sources and limitations.',
  sources:['Study setup','Measured results','Run record'],
  limitations:['This is an authored interface demonstration.','No model was run and no accuracy claim is made.']
});
export const FIELDS=Object.freeze([
  {key:'question',label:'Question',number:'01',path:'$.question',type:'string',reason:'The same question anchors every representation.'},
  {key:'finding',label:'Finding',number:'02',path:'$.finding',type:'string',reason:'Readable prose and structured data retain the same finding.'},
  {key:'sources',label:'Sources',number:'03',path:'$.sources',type:'string[]',reason:'The source labels stay attached when the reading mode changes.'},
  {key:'limitations',label:'Limitations',number:'04',path:'$.limitations',type:'string[]',reason:'A code view cannot silently drop the qualifications.'}
]);
export function valueText(key){const value=RECORD[key];return Array.isArray(value)?value.join(' · '):value;}
export function jsonGroups(){
  const lines=JSON.stringify(RECORD,null,2).split('\n'),groups=[];let owner=null;
  for(let index=0;index<lines.length;index++){
    const line=lines[index],match=line.match(/^  "([^"]+)":/);
    if(match)owner=FIELDS.some(field=>field.key===match[1])?match[1]:null;
    if(index===lines.length-1)owner=null;
    if(groups.at(-1)?.key===owner)groups.at(-1).lines.push({number:index+1,text:line});else groups.push({key:owner,lines:[{number:index+1,text:line}]});
  }
  return groups;
}
