import assert from 'node:assert/strict';
import {RECORD,FIELDS,valueText,jsonGroups} from './record.mjs';
assert.equal(new Set(FIELDS.map(field=>field.key)).size,4);
for(const field of FIELDS){assert.ok(Object.hasOwn(RECORD,field.key));assert.ok(valueText(field.key));}
const groups=jsonGroups(),restored=groups.flatMap(group=>group.lines).map(line=>line.text).join('\n');assert.deepEqual(JSON.parse(restored),RECORD);
for(const field of FIELDS){const group=groups.find(value=>value.key===field.key);assert.ok(group);assert.ok(group.lines[0].text.includes('"'+field.key+'"'));}
assert.equal(groups.flatMap(group=>group.lines).every((line,index)=>line.number===index+1),true);
assert.ok(RECORD.limitations.some(text=>text.includes('No model')));
console.log('Record identity, field completeness, exact JSON roundtrip, highlight ownership and line numbering passed.');
