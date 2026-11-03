import test from 'node:test';
import assert from 'node:assert/strict';
import { parseSnapshot, snapshotIsOlder, filterEvents, isStale, ageLabel } from '../docs/playground/data.mjs';

const event = (id, kind, at = '2026-11-03T12:00:00Z') => ({ id, title: id, kind, at_utc: at, detail: '<script>untrusted text</script>' });
const raw = overrides => ({ generated_at_utc: '2026-11-03T12:01:00Z', stage: 'completed', events: [], ...overrides });

test('bad snapshots fail rather than inventing a ready state', () => {
  for (const input of [null, {}, raw({ events: null }), raw({ generated_at_utc: 'invalid' }), raw({ stage: false })]) assert.throws(() => parseSnapshot(input));
});
test('missing, invalid or inconsistent counts remain unavailable', () => {
  assert.equal(parseSnapshot(raw()).teacher, null);
  const snapshot = parseSnapshot(raw({ metrics: { teacher_responses: 16, strict_answer_passes: 20 } }));
  assert.equal(snapshot.teacher, 16); assert.equal(snapshot.passes, null);
  assert.equal(parseSnapshot(raw({ metrics: { teacher_responses: -5 } })).teacher, null);
});
test('events are validated, deduplicated and ordered by evidence time', () => {
  const snapshot = parseSnapshot(raw({ events: [event('older', 'failed'), event('newer', 'resolved', '2026-11-03T12:02:00Z'), event('older', 'failed'), { title: 'broken', at_utc: 'no-date' }] }));
  assert.deepEqual(snapshot.events.map(e => e.id), ['newer', 'older']);
  assert.equal(snapshot.events[0].detail, '<script>untrusted text</script>'); // The view must use textContent, never HTML.
});
test('an out-of-order response cannot replace a newer snapshot', () => {
  const current = parseSnapshot(raw({ generated_at_utc: '2026-11-03T13:00:00Z' }));
  assert.equal(snapshotIsOlder(parseSnapshot(raw()), current), true);
  assert.equal(snapshotIsOlder(current, current), false);
  assert.equal(snapshotIsOlder(current, null), false);
});
test('issues include failed and resolved evidence, not just successes', () => {
  const events = parseSnapshot(raw({ events: [event('f', 'failed'), event('r', 'resolved'), event('c', 'completed'), event('p', 'planned')] })).events;
  assert.deepEqual(filterEvents(events, 'issues').map(e => e.id), ['f', 'r']);
  assert.deepEqual(filterEvents(events, 'completed').map(e => e.id), ['c']);
});
test('staleness reflects publication age; future timestamps do not become negative ages', () => {
  const snapshot = parseSnapshot(raw());
  assert.equal(isStale(snapshot, Date.parse('2026-11-03T12:31:00Z')), false);
  assert.equal(isStale(snapshot, Date.parse('2026-11-03T12:32:00Z')), true);
  assert.equal(ageLabel('2026-11-03T13:00:00Z', Date.parse('2026-11-03T12:00:00Z')), 'just now');
});
