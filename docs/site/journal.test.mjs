import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseJournal, filterJournalEvents, groupJournalEvents} from './journal.mjs';

test('the published journal retains all 267 exact event bodies and its introduction', async () => {
  const source = await readFile(new URL('../journal.md', import.meta.url), 'utf8');
  const {intro, events} = parseJournal(source);
  assert.equal(events.length, 267);
  assert.equal(intro + events.map(event => event.raw).join(''), source);
  for (const event of events) {
    const newline = event.raw.indexOf('\n');
    assert.equal(event.body, newline === -1 ? '' : event.raw.slice(newline + 1));
    assert.match(event.timestamp, /^2026-/);
  }
  assert.match(intro, /Current stage:/);
});

test('CRLF, invalid headings, duplicate timestamps and final lines remain intact', () => {
  const source = '# Journal\r\n\r\n## not a timestamp | failed | preserve this\r\n\r\n' +
    '## 2026-11-03T23:59:59Z | completed | First\r\n\r\nA <script> is source text.\r\n\r\n' +
    '## 2026-11-04T00:00:00+00:00 | failed | Second\r\n\r\nBody\r\n' +
    '## 2026-11-04T00:00:00+00:00 | resolved | Third';
  const parsed = parseJournal(source);
  assert.equal(parsed.events.length, 3);
  assert.equal(parsed.intro + parsed.events.map(event => event.raw).join(''), source);
  assert.equal(parsed.events[0].body, '\r\nA <script> is source text.\r\n\r\n');
  assert.equal(parsed.events[2].body, '');
  const originalOrder = parsed.events.map(event => event.title);
  assert.deepEqual(groupJournalEvents(parsed.events).map(group => [group.day, group.events.map(event => event.title)]), [
    ['2026-11-04', ['Second', 'Third']], ['2026-11-03', ['First']]
  ]);
  assert.deepEqual(parsed.events.map(event => event.title), originalOrder);
});

test('filtering searches every original body and combines terms with an exact status', () => {
  const source = '## 2026-11-03T10:00:00Z | completed | Teacher pass\n\nStrict parser retained currency output.\n' +
    '## 2026-11-04T10:00:00Z | failed | Format rejection\n\nCurrency output was retained.\n';
  const {events} = parseJournal(source);
  assert.equal(filterJournalEvents(events, {query: 'CURRENCY retained'}).length, 2);
  assert.equal(filterJournalEvents(events, {query: 'currency', status: 'failed'})[0].title, 'Format rejection');
  assert.equal(filterJournalEvents(events, {query: 'missing'}).length, 0);
  assert.equal(filterJournalEvents(events).length, 2);
  assert.deepEqual(parseJournal('Only an introduction.'), {intro: 'Only an introduction.', events: []});
});
