import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {renderMarkdown} from './markdown.js';

test('the complete public overnight report retains all five rows and its final body',()=>{
  const markdown=fs.readFileSync(new URL('../overnight-results.md',import.meta.url),'utf8');
  const {html,headings}=renderMarkdown(markdown,{baseUrl:'https://avisrikumeran.github.io/granite-query/overnight-results.md'});
  const body=html.match(/<tbody>([\s\S]*?)<\/tbody>/)[1];
  assert.equal((body.match(/<tr>/g)??[]).length,5);
  for(const phrase of ['Untouched Granite','Small correction adapter, 8 updates','Larger random-control adapter, 64 updates','A follow-up was stopped before spending','Costs and saved outputs','Next scientific step','no paid request was retried.'])assert.ok(html.includes(phrase),phrase);
  assert.match(html,/class="md-table"/);assert.ok(!html.includes('<h1'));
  assert.ok(headings.length>=6);assert.equal(headings[0].level,2);
});
test('raw HTML and unsafe links stay text, including malicious attribute payloads',()=>{
  const source='<script>alert(1)</script> <img src=x onerror="evil()">\n\n[x](javascript:alert(1)) [y](data:text/html,boom) [z](vbscript:run)\n\n[safe](https://example.com/\" onmouseover=\"evil)';
  const {html}=renderMarkdown(source);
  assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('&lt;img'));
  assert.ok(!/<script\b|<img\b|href="(?:javascript|data|vbscript):/i.test(html));
  assert.ok(!/href="[^"]*"\s+onmouseover=/i.test(html));
  assert.ok(html.includes('javascript:alert(1)'));assert.ok(html.includes('data:text/html,boom'));
});
test('fenced code and inline code escape executable markup and preserve complete contents',()=>{
  const {html}=renderMarkdown('```js" onload="bad\n<script>const x = "<&";</script>\n```\n\nUse `<img onerror=bad>` and x^2 + β unchanged.\n\n~~~python\nprint("tail")');
  assert.equal((html.match(/<pre>/g)??[]).length,2);
  assert.ok(html.includes('&lt;script&gt;const x = &quot;&lt;&amp;&quot;;&lt;/script&gt;'));
  assert.ok(html.includes('<code>&lt;img onerror=bad&gt;</code>'));
  assert.ok(html.includes('x^2 + β unchanged.'));assert.ok(html.includes('print(&quot;tail&quot;)'));
  assert.ok(!html.includes(' onload='));
});
test('headings have globally unique IDs, downgrade H1, and internal navigation matches',()=>{
  const {html,headings}=renderMarkdown('# **Methods**\n\n## Methods\n\n### Methods-2\n\n#### Methods\n\n[Back](#methods)');
  assert.equal(new Set(headings.map(heading=>heading.id)).size,4);
  assert.deepEqual(headings.map(heading=>heading.level),[2,2,3,4]);
  assert.ok(headings.every(heading=>heading.id.startsWith('doc-')));
  for(const heading of headings)assert.ok(html.includes('id="'+heading.id+'"'));
  assert.ok(html.includes('href="#doc-methods"'));assert.equal(headings[0].text,'Methods');
  assert.equal(renderMarkdown('## C# and x^2').headings[0].text,'C# and x^2');
  assert.equal(renderMarkdown('## C#').headings[0].text,'C#');
});
test('lists, nested lists, quotes and pipe tables retain their content',()=>{
  const {html}=renderMarkdown('- first **bold**\n  - nested `code`\n- second\n\n1. ordered\n2. final\n\n> quoted <unsafe>\n> still quoted\n\n| A | B |\n| --- | --- |\n| one | `x|y` |\n| two | three | extra |');
  assert.equal((html.match(/<ul>/g)??[]).length,2);assert.ok(html.includes('<ol>'));
  assert.ok(html.includes('<strong>bold</strong>'));assert.ok(html.includes('<code>code</code>'));
  assert.ok(html.includes('<blockquote>'));assert.ok(html.includes('&lt;unsafe&gt;'));
  assert.ok(html.includes('<code>x|y</code>'));assert.ok(html.includes('<td>extra</td>'));
  assert.ok(html.includes('still quoted'));assert.ok(html.includes('final'));
});
test('relative links resolve against the source document and forbidden base protocols fail',()=>{
  const {html}=renderMarkdown('[report](../results.md) [root](/granite-query/) [web](https://example.org/a_(b)) [local](#next-section)',{baseUrl:'https://avisrikumeran.github.io/granite-query/progress/note.md'});
  assert.ok(html.includes('href="https://avisrikumeran.github.io/granite-query/results.md"'));
  assert.ok(html.includes('href="https://avisrikumeran.github.io/granite-query/"'));
  assert.ok(html.includes('href="https://example.org/a_(b)"'));assert.ok(html.includes('href="#doc-next-section"'));
  assert.throws(()=>renderMarkdown('text',{baseUrl:'javascript:alert(1)'}),/HTTP/);
  assert.throws(()=>renderMarkdown(null),/string/);
});
test('the original teacher report resolves its public SVG against the source file',()=>{
  const markdown=fs.readFileSync(new URL('../../progress/DEVELOPMENT_TEACHER200.md',import.meta.url),'utf8');
  const {html}=renderMarkdown(markdown,{baseUrl:'https://raw.githubusercontent.com/AviSrikumeran/granite-query/main/progress/DEVELOPMENT_TEACHER200.md'});
  assert.ok(html.includes('<img src="https://raw.githubusercontent.com/AviSrikumeran/granite-query/main/docs/figures/development-teacher200.svg" alt="Matched200 development comparison"'));
  assert.ok(!html.includes('!<a'));
  assert.ok(html.includes('97.0%'));assert.ok(html.includes('official test set remains sealed'));
});
test('image alt and source attributes are escaped and unsafe image protocols remain text',()=>{
  const {html}=renderMarkdown('![<img src=x onerror="bad"> & "quote"](https://example.org/chart.svg)\n\n![unsafe](javascript:alert(1)) ![payload](data:image/svg+xml,boom) ![other](vbscript:run)');
  assert.equal((html.match(/<img /g)??[]).length,1);
  assert.ok(html.includes('alt="&lt;img src=x onerror=&quot;bad&quot;&gt; &amp; &quot;quote&quot;"'));
  assert.ok(!html.includes('alt="" onerror='));
  assert.ok(!/<img[^>]+src="(?:javascript|data|vbscript):/i.test(html));
  assert.ok(html.includes('![unsafe](javascript:alert(1))'));
  assert.ok(html.includes('data:image/svg+xml,boom'));
});
