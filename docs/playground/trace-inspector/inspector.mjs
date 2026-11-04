import {RECORDS,SOURCES,byId,childrenOf,ancestorsOf,filteredRecords,visibleRecords} from './model.mjs?v=trace-inspector-20261104-1';

const $=selector=>document.querySelector(selector);
const tree=$('#tree'),search=$('#record-search'),kind=$('#kind');
const views=['overview','input','output','source'];
const symbols={Packet:'▦',Source:'▤',Check:'◇',Qualification:'◈',Reference:'↗',Finding:'◆'};
const params=new URLSearchParams(location.search);
let selected=byId(params.get('record'))?.id??'interval';
let view='overview';
let expanded=new Set(['packet','interpretation']);
ancestorsOf(selected).forEach(record=>expanded.add(record.id));
let current=[];

const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
function button(text,action){const node=el('button',text);node.type='button';node.addEventListener('click',action);return node;}
function announce(text){$('#announcement').textContent=text;}

function selectRecord(id,{focusTree=false}={}){
  if(!byId(id))return;
  selected=id;
  ancestorsOf(id).forEach(parent=>expanded.add(parent.id));
  renderTree();renderDetail();
  if(focusTree)tree.querySelector(`[data-id="${id}"]`)?.focus({preventScroll:true});
  announce(`${byId(id).label}. Parent: ${byId(byId(id).parent)?.label??'packet root'}. ${byId(id).summary}`);
}

function toggleRecord(id){
  if(!childrenOf(id).length)return;
  if(expanded.has(id))expanded.delete(id);else expanded.add(id);
  renderTree();tree.querySelector(`[data-id="${id}"]`)?.focus({preventScroll:true});
}

function renderTree(){
  const result=visibleRecords({query:search.value,kind:kind.value,expanded});
  current=result.records;
  tree.replaceChildren();
  for(const record of current){
    const children=childrenOf(record.id),depth=ancestorsOf(record.id).length;
    const row=el('button',undefined,'tree-row');row.type='button';row.dataset.id=record.id;
    row.style.setProperty('--depth',String(depth));
    row.setAttribute('role','treeitem');row.setAttribute('aria-level',String(depth+1));
    row.setAttribute('aria-selected',String(record.id===selected));
    row.tabIndex=record.id===selected||(!current.some(item=>item.id===selected)&&record.id===current[0]?.id)?0:-1;
    row.setAttribute('aria-label',`${record.label}, ${record.kind}, ${record.code}${children.length?', '+children.length+' child records':''}`);
    if(children.length)row.setAttribute('aria-expanded',String(result.filter.active||expanded.has(record.id)));
    if(result.filter.active&&!result.filter.matches.some(match=>match.id===record.id))row.classList.add('context-only');
    const chevron=el('span',children.length?(result.filter.active||expanded.has(record.id)?'⌄':'›'):'','tree-chevron');chevron.setAttribute('aria-hidden','true');
    const symbol=el('span',symbols[record.kind]??'·','tree-symbol');symbol.setAttribute('aria-hidden','true');
    row.append(chevron,symbol,el('span',record.label,'tree-label'),el('span',record.kind,'tree-kind'));
    row.addEventListener('click',event=>{if(event.target===chevron&&children.length&&!result.filter.active){toggleRecord(record.id);return;}selectRecord(record.id,{focusTree:true});});
    row.addEventListener('keydown',event=>{
      const index=current.findIndex(item=>item.id===record.id);let target;
      if(event.key==='ArrowDown')target=current[Math.min(current.length-1,index+1)];
      else if(event.key==='ArrowUp')target=current[Math.max(0,index-1)];
      else if(event.key==='Home')target=current[0];
      else if(event.key==='End')target=current.at(-1);
      else if(event.key==='ArrowRight'){
        if(children.length&&!expanded.has(record.id)&&!result.filter.active){event.preventDefault();toggleRecord(record.id);return;}
        target=current.find(item=>item.parent===record.id);
      }else if(event.key==='ArrowLeft'){
        if(children.length&&expanded.has(record.id)&&!result.filter.active){event.preventDefault();toggleRecord(record.id);return;}
        target=byId(record.parent);
      }else return;
      event.preventDefault();if(target&&current.some(item=>item.id===target.id))selectRecord(target.id,{focusTree:true});
    });
    tree.append(row);
  }
  $('#empty-state').hidden=result.filter.matches.length>0;
  $('#match-count').textContent=result.filter.active?`${result.filter.matches.length} matching / ${RECORDS.length} records`:`${RECORDS.length} records · ${current.length} visible`;
  $('#clear-filters').hidden=!result.filter.active;
  $('#outside-filter').hidden=current.some(record=>record.id===selected);
  const allExpanded=RECORDS.filter(record=>childrenOf(record.id).length).every(record=>expanded.has(record.id));
  $('#expand-all').textContent=allExpanded?'Collapse groups':'Expand all';
  $('#inspector').dataset.visible=String(current.length);
  $('#inspector').dataset.matches=String(result.filter.matches.length);
}

function showView(next,{focus=false}={}){
  view=views.includes(next)?next:'overview';
  for(const id of views){
    const tab=$('#tab-'+id);tab.setAttribute('aria-selected',String(id===view));tab.tabIndex=id===view?0:-1;
    $('#panel-'+id).hidden=id!==view;
  }
  $('#inspector').dataset.view=view;
  if(focus)$('#tab-'+view).focus();
}

function renderDetail(){
  const record=byId(selected),parent=byId(record.parent),children=childrenOf(selected);
  const breadcrumbs=$('#breadcrumbs');breadcrumbs.replaceChildren();
  for(const ancestor of ancestorsOf(selected)){breadcrumbs.append(button(ancestor.label,()=>selectRecord(ancestor.id)),el('span','/'));}
  breadcrumbs.append(el('span',record.label));
  $('#record-kind').textContent=`${record.kind} / ${record.code}`;
  $('#record-title').textContent=record.label;
  $('#record-id').textContent=record.code;
  $('#record-summary').textContent=record.summary;
  $('#parent-link').textContent=parent?`${parent.label} ↖`:'Packet root';
  $('#parent-link').disabled=!parent;
  $('#child-count').textContent=children.length?`${children.length} child records`:'Leaf record';
  $('#source-count').textContent=String(record.sources.length);
  $('#source-tab-count').textContent=String(record.sources.length);
  $('#overview-input').textContent=record.input;$('#overview-output').textContent=record.output;
  $('#input-text').textContent=record.input;$('#output-text').textContent=record.output;
  $('#input-parent').textContent=parent?`${parent.label} ↖`:'Packet root';$('#input-parent').disabled=!parent;
  const first=SOURCES[record.sources[0]];
  $('#preview-document').textContent=`${first.document} / ${first.section}`;
  $('#preview-quote').textContent=first.text;
  $('#child-records').hidden=children.length===0;
  const childLinks=$('#child-links');childLinks.replaceChildren();
  children.forEach(child=>childLinks.append(button(`${child.code} · ${child.label} ↗`,()=>selectRecord(child.id))));
  const sources=$('#source-documents');sources.replaceChildren();
  record.sources.forEach((id,index)=>{
    const source=SOURCES[id],article=el('article',undefined,'source-document');
    const heading=el('div',undefined,'source-document-head');heading.append(el('strong',source.document),el('span',`SOURCE ${String(index+1).padStart(2,'0')}`));
    article.append(heading,el('h4',source.section),el('blockquote',source.text));sources.append(article);
  });
  $('#selection-status').textContent=`Selected: ${record.code} / ${record.label}`;
  $('#inspector').dataset.selected=selected;
  showView(view);
}

function clearFilters(){search.value='';kind.value='all';renderTree();}
search.addEventListener('input',renderTree);kind.addEventListener('change',renderTree);
$('#clear-filters').addEventListener('click',clearFilters);$('#clear-empty').addEventListener('click',()=>{clearFilters();search.focus();});
$('#reveal-record').addEventListener('click',()=>{clearFilters();ancestorsOf(selected).forEach(parent=>expanded.add(parent.id));renderTree();tree.querySelector(`[data-id="${selected}"]`)?.focus({preventScroll:true});});
$('#expand-all').addEventListener('click',()=>{
  const branches=RECORDS.filter(record=>childrenOf(record.id).length);
  expanded=branches.every(record=>expanded.has(record.id))?new Set(['packet']):new Set(branches.map(record=>record.id));
  renderTree();
});
for(const id of ['parent-link','input-parent'])$('#'+id).addEventListener('click',()=>{const parent=byId(selected).parent;if(parent)selectRecord(parent);});
for(const id of ['open-sources','output-source'])$('#'+id).addEventListener('click',()=>showView('source'));
for(const next of views){
  $('#tab-'+next).addEventListener('click',()=>showView(next));
  $('#tab-'+next).addEventListener('keydown',event=>{
    const index=views.indexOf(next);let target;
    if(event.key==='ArrowRight')target=views[(index+1)%views.length];
    else if(event.key==='ArrowLeft')target=views[(index+views.length-1)%views.length];
    else if(event.key==='Home')target=views[0];
    else if(event.key==='End')target=views.at(-1);
    else return;
    event.preventDefault();showView(target,{focus:true});
  });
}
document.addEventListener('keydown',event=>{
  if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){event.preventDefault();search.focus();}
  if(event.key==='Escape'&&document.activeElement===search){clearFilters();search.blur();}
});
renderTree();renderDetail();
