/* Small, safe research-reader renderer. It emits only authored tags; source HTML
   is text, code is inert, and links are restricted to HTTP(S)/local headings. */
const escape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const slug=value=>value.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,'-').replace(/^-+|-+$/g,'')||'section';

export function renderMarkdown(markdown,{baseUrl='https://avisrikumeran.github.io/granite-query/'}={}){
  if(typeof markdown!=='string')throw new TypeError('Markdown must be a string');
  const base=new URL(baseUrl);
  if(!['http:','https:'].includes(base.protocol))throw new TypeError('Markdown source URL must use HTTP(S)');
  const headings=[],usedIds=new Set();

  function hrefFor(raw){
    const value=raw.trim().replace(/^<([^<>]*)>$/,'$1');
    if(value.startsWith('#')){
      if(value==='#')return '#';
      let fragment=value.slice(1);try{fragment=decodeURIComponent(fragment);}catch{}
      return '#'+(fragment.startsWith('doc-')?fragment:'doc-'+slug(fragment));
    }
    try{const url=new URL(value,base);return ['http:','https:'].includes(url.protocol)?url.href:null;}catch{return null;}
  }
  function imageSource(raw){
    const value=raw.trim().replace(/^<([^<>]*)>$/,'$1');
    try{const url=new URL(value,base);return ['http:','https:'].includes(url.protocol)?url.href:null;}catch{return null;}
  }

  function linkAt(source,start){
    let close=start+1;
    while(close<source.length){if(source[close]==='\\'){close+=2;continue;}if(source[close]===']')break;close++;}
    if(source[close]!==']'||source[close+1]!=='(')return null;
    let end=close+2,depth=1,quoted=null;
    for(;end<source.length;end++){
      const char=source[end];if(char==='\\'){end++;continue;}
      if(quoted){if(char===quoted)quoted=null;continue;}
      if((char==='"'||char==="'")&&/\s/.test(source[end-1]??'')){quoted=char;continue;}
      if(char==='(')depth++;else if(char===')'&&--depth===0)break;
    }
    if(depth!==0)return null;
    const raw=source.slice(close+2,end).trim().replace(/\s+["'][^"']*["']\s*$/,'');
    return {label:source.slice(start+1,close),raw,end:end+1,whole:source.slice(start,end+1)};
  }

  function inline(source,{links=true,depth=0}={}){
    if(depth>20)return {html:escape(source),text:source};
    let html='',plain='',i=0;
    while(i<source.length){
      const char=source[i];
      if(char==='\\'&&i+1<source.length&&/[\\`*_[\]()|]/.test(source[i+1])){html+=escape(source[i+1]);plain+=source[i+1];i+=2;continue;}
      if(char==='`'){
        const run=source.slice(i).match(/^`+/)[0],end=source.indexOf(run,i+run.length);
        if(end!==-1){const content=source.slice(i+run.length,end);html+='<code>'+escape(content)+'</code>';plain+=content;i=end+run.length;continue;}
      }
      const marker=source.slice(i,i+2);
      if(marker==='**'||marker==='__'){
        const end=source.indexOf(marker,i+2);
        if(end!==-1){const content=inline(source.slice(i+2,end),{links,depth:depth+1});html+='<strong>'+content.html+'</strong>';plain+=content.text;i=end+2;continue;}
      }
      if(links&&char==='!'&&source[i+1]==='['){
        const image=linkAt(source,i+1);
        if(image){
          const src=imageSource(image.raw),alt=inline(image.label,{links:false,depth:depth+1}).text;
          if(src!==null){html+='<img src="'+escape(src)+'" alt="'+escape(alt)+'" loading="lazy" decoding="async">';plain+=alt;}
          else{html+=escape('!'+image.whole);plain+='!'+image.whole;}
          i=image.end;continue;
        }
      }
      if(links&&char==='['){
        const link=linkAt(source,i);
        if(link){
          const href=hrefFor(link.raw),label=inline(link.label,{links:false,depth:depth+1});
          if(href!==null){html+='<a href="'+escape(href)+'"'+(href.startsWith('#')?'':' rel="noopener noreferrer"')+'>'+label.html+'</a>';plain+=label.text;}
          else{html+=escape(link.whole);plain+=link.whole;}
          i=link.end;continue;
        }
      }
      html+=escape(char);plain+=char;i++;
    }
    return {html,text:plain};
  }

  function cells(line){
    let value=line.trim();if(value.startsWith('|'))value=value.slice(1);if(value.endsWith('|')&&!value.endsWith('\\|'))value=value.slice(0,-1);
    const result=[];let cell='',code=false;
    for(let i=0;i<value.length;i++){
      if(value[i]==='\\'&&value[i+1]==='|'){cell+='|';i++;continue;}
      if(value[i]==='`')code=!code;
      if(value[i]==='|'&&!code){result.push(cell.trim());cell='';}else cell+=value[i];
    }
    result.push(cell.trim());return result;
  }
  const divider=line=>{const values=cells(line);return values.length>0&&values.every(value=>/^:?-{3,}:?$/.test(value));};
  const tableAt=(lines,index)=>index+1<lines.length&&lines[index].includes('|')&&divider(lines[index+1]);
  const heading=line=>{const match=line.match(/^ {0,3}(#{1,4})[\t ]+(.+?)\s*$/);if(match)match[2]=match[2].replace(/[\t ]+#+[\t ]*$/,'');return match;};
  const fence=line=>line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
  const list=line=>{const match=line.match(/^( *)([-+*]|\d+[.)])[\t ]+(.*)$/);return match?{indent:match[1].length,ordered:/^\d/.test(match[2]),start:parseInt(match[2],10),body:match[3]}:null;};
  const blockStart=(lines,index)=>Boolean(heading(lines[index])||fence(lines[index])||list(lines[index])||/^ {0,3}>/.test(lines[index])||tableAt(lines,index));

  function blocks(lines,depth=0){
    if(depth>32)return '<p>'+inline(lines.join('\n')).html+'</p>';
    let html='',i=0;
    while(i<lines.length){
      if(!lines[i].trim()){i++;continue;}
      const opening=fence(lines[i]);
      if(opening){
        const marker=opening[1][0],length=opening[1].length,info=opening[2].trim().split(/\s+/)[0];
        const language=/^[a-zA-Z0-9_+-]{1,32}$/.test(info)?info:'';
        const content=[];i++;
        while(i<lines.length){const closing=lines[i].trim();if(new RegExp('^'+(marker==='`'?'`':'~')+'{'+length+',}\\s*$').test(closing)){i++;break;}content.push(lines[i++]);}
        html+='<pre><code'+(language?' class="language-'+language+'"':'')+'>'+escape(content.join('\n'))+'</code></pre>';continue;
      }
      const title=heading(lines[i]);
      if(title){
        const content=inline(title[2]),level=Math.max(2,title[1].length),baseId='doc-'+slug(content.text);
        let id=baseId,suffix=2;while(usedIds.has(id))id=baseId+'-'+suffix++;
        usedIds.add(id);headings.push({id,text:content.text,level});html+='<h'+level+' id="'+escape(id)+'">'+content.html+'</h'+level+'>';i++;continue;
      }
      if(tableAt(lines,i)){
        const header=cells(lines[i]);i+=2;const rows=[];
        while(i<lines.length&&lines[i].trim()&&lines[i].includes('|'))rows.push(cells(lines[i++]));
        const width=Math.max(header.length,...rows.map(row=>row.length));
        html+='<div class="md-table"><table><thead><tr>';
        for(let col=0;col<width;col++)html+='<th scope="col">'+inline(header[col]??'').html+'</th>';
        html+='</tr></thead><tbody>';
        for(const row of rows){html+='<tr>';for(let col=0;col<width;col++)html+='<td>'+inline(row[col]??'').html+'</td>';html+='</tr>';}
        html+='</tbody></table></div>';continue;
      }
      if(/^ {0,3}>/.test(lines[i])){
        const quote=[];while(i<lines.length&&/^ {0,3}>/.test(lines[i]))quote.push(lines[i++].replace(/^ {0,3}> ?/,''));
        html+='<blockquote>'+blocks(quote,depth+1)+'</blockquote>';continue;
      }
      const first=list(lines[i]);
      if(first){
        const tag=first.ordered?'ol':'ul';html+='<'+tag+(first.ordered&&first.start!==1?' start="'+first.start+'"':'')+'>';
        while(i<lines.length){
          const item=list(lines[i]);if(!item||item.indent!==first.indent||item.ordered!==first.ordered)break;
          const content=[item.body];i++;
          while(i<lines.length){
            const next=list(lines[i]);if(next&&next.indent<=first.indent)break;
            if(!lines[i].trim()){
              let following=i+1;while(following<lines.length&&!lines[following].trim())following++;
              const nextItem=following<lines.length?list(lines[following]):null;
              if(nextItem&&nextItem.indent===first.indent&&nextItem.ordered===first.ordered){i=following;break;}
              if(following<lines.length&&(lines[following].match(/^ */)[0].length>first.indent)){content.push('');i++;continue;}
              break;
            }
            const indentation=lines[i].match(/^ */)[0].length;
            if(indentation>first.indent){content.push(lines[i].slice(Math.min(indentation,first.indent+2)));i++;continue;}
            if(blockStart(lines,i))break;
            content.push(lines[i++]);
          }
          html+='<li>'+blocks(content,depth+1)+'</li>';
        }
        html+='</'+tag+'>';continue;
      }
      const paragraph=[lines[i++]];
      while(i<lines.length&&lines[i].trim()&&!blockStart(lines,i))paragraph.push(lines[i++]);
      html+='<p>'+inline(paragraph.join('\n')).html+'</p>';
    }
    return html;
  }
  const html=blocks(markdown.replace(/\r\n?/g,'\n').split('\n'));
  return {html,headings};
}
