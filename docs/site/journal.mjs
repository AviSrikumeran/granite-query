/* Presentation helpers for the append-only journal. Source slices remain exact;
   grouping and filtering never rewrite an event or infer a current job state. */
export function parseJournal(markdown) {
  if (typeof markdown !== 'string') throw new TypeError('Journal source must be a string');
  const headings = [...markdown.matchAll(/^## ([^|\r\n]+) \| ([^|\r\n]+) \| ([^\r\n]+)\r?$/gm)]
    .filter(match => Number.isFinite(Date.parse(match[1].trim())));
  const events = headings.map((match, index) => {
    const end = headings[index + 1]?.index ?? markdown.length;
    const raw = markdown.slice(match.index, end);
    const newline = raw.indexOf('\n');
    const timestamp = match[1].trim();
    return {
      id: `journal-entry-${index + 1}`,
      sequence: index,
      timestamp,
      time: Date.parse(timestamp),
      day: new Date(timestamp).toISOString().slice(0, 10),
      status: match[2].trim(),
      title: match[3].trim(),
      heading: raw.slice(0, newline === -1 ? raw.length : newline).replace(/\r$/, ''),
      body: newline === -1 ? '' : raw.slice(newline + 1),
      raw
    };
  });
  return {intro: markdown.slice(0, headings[0]?.index ?? markdown.length), events};
}

export function filterJournalEvents(events, {query = '', status = 'all'} = {}) {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return events.filter(event => (status === 'all' || event.status === status) &&
    terms.every(term => `${event.title} ${event.status} ${event.timestamp} ${event.body}`.toLowerCase().includes(term)));
}

export function groupJournalEvents(events) {
  const groups = new Map();
  const ordered = [...events].sort((a, b) => b.time - a.time || a.sequence - b.sequence);
  for (const event of ordered) {
    if (!groups.has(event.day)) groups.set(event.day, []);
    groups.get(event.day).push(event);
  }
  return [...groups].map(([day, items]) => ({day, events: items}));
}
