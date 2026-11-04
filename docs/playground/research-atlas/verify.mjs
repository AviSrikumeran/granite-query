import assert from 'node:assert/strict';
import {SECTIONS,searchSections,snippet,normalize} from './content.mjs';
assert.equal(new Set(SECTIONS.map(section=>section.id)).size,6);
for(const section of SECTIONS){const result=searchSections(section.title);assert.equal(result[0].id,section.id);assert.ok(snippet(section,section.title).length<=147);}
assert.equal(searchSections('').length,6);assert.equal(searchSections('uncertainty')[0].id,'finding');assert.equal(searchSections('no such electric pineapple').length,0);assert.ok(searchSections('model revision').some(section=>section.id==='protocol'));assert.equal(searchSections('UNCERTAINTY').map(x=>x.id).join(),searchSections('uncertainty').map(x=>x.id).join());assert.equal(normalize('  méthod!  '),'method');
for(const query of ['protocol','sources','limitations','<script>','\\','[unmatched',''])for(const result of searchSections(query)){assert.ok(SECTIONS.some(section=>section.id===result.id));assert.ok(Number.isFinite(result.score));}
console.log('Atlas search: section identity, full-title ranking, AND terms, case/accent normalization, empty/no-result queries and bounded snippets passed.');
