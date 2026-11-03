// The public snapshot is untrusted input. Keep display data separate from motion state.
const kinds = new Set(['completed', 'in_progress', 'failed', 'resolved', 'planned', 'decision']);
const clean = (value, max = 4000) => typeof value === 'string' ? value.slice(0, max) : '';
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;

export function parseSnapshot(raw) {
  if (!raw || typeof raw !== 'object' || !Number.isFinite(Date.parse(raw.generated_at_utc)) || typeof raw.stage !== 'string' || !Array.isArray(raw.events)) {
    throw new Error('The public snapshot has an unsupported format.');
  }
  const seen = new Set();
  const events = raw.events.flatMap((event, index) => {
    if (!event || typeof event.title !== 'string' || !Number.isFinite(Date.parse(event.at_utc))) return [];
    const id = clean(event.id, 500) || `event-${event.at_utc}-${index}`;
    if (seen.has(id)) return [];
    seen.add(id);
    return [{ id, title: clean(event.title, 500), detail: clean(event.detail), at: event.at_utc, kind: kinds.has(event.kind) ? event.kind : 'decision' }];
  }).sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  const teacher = count(raw.metrics?.teacher_responses);
  const passes = count(raw.metrics?.strict_answer_passes);
  return {
    generated: raw.generated_at_utc,
    stage: clean(raw.stage, 500), next: clean(raw.next_action),
    caveat: clean(raw.caveat) || 'Teacher verification is not held-out student accuracy.',
    teacher, passes: teacher !== null && passes !== null && passes <= teacher ? passes : null,
    events,
  };
}

export function snapshotIsOlder(candidate, current) {
  return !!current && Date.parse(candidate.generated) < Date.parse(current.generated);
}

export function ageLabel(date, now = Date.now()) {
  const seconds = Math.max(0, (now - Date.parse(date)) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function isStale(snapshot, now = Date.now()) {
  return now - Date.parse(snapshot.generated) > 30 * 60 * 1000;
}

export function filterEvents(events, filter) {
  if (filter === 'issues') return events.filter(event => event.kind === 'failed' || event.kind === 'resolved');
  if (filter === 'completed') return events.filter(event => event.kind === 'completed');
  return events;
}
