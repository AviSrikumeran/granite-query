import {renderMarkdown} from './markdown.js?v=20261104-1';
import {parseJournal, filterJournalEvents, groupJournalEvents} from './journal.mjs?v=20261105-1';

const $ = selector => document.querySelector(selector);
const root = new URL('../', import.meta.url);
const sourceUrl = path => new URL(path, root).href;
const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const menu = $('.menu-toggle'), navigation = $('#main-nav');
function closeMenu(focus = false) {
  menu.setAttribute('aria-expanded', 'false');
  navigation.classList.remove('is-open');
  if (focus) menu.focus();
}
menu.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(open));
  navigation.classList.toggle('is-open', open);
});
navigation.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') closeMenu(true);
});
matchMedia('(min-width:651px)').addEventListener('change', event => { if (event.matches) closeMenu(); });

const catalogue = $('#library-catalogue'), narrowCatalogue = matchMedia('(max-width:900px)');
catalogue.open = !narrowCatalogue.matches;
narrowCatalogue.addEventListener('change', event => { catalogue.open = !event.matches; });
const collections = new Set(['Reports', 'Methods', 'Data', 'History', 'all']);
let records = [], selectedId = 'overnight', query = '', category = 'Reports';
let requestId = 0, currentController = null, displayedId = null, journalView = null;
let journalQuery = '', journalStatus = 'all';
const cache = new Map();
const permitted = value => {
  try { return ['https:', 'http:'].includes(new URL(value, root).protocol); } catch { return false; }
};
const stamp = value => new Date(value).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';

function readLocation() {
  const params = new URLSearchParams(location.search);
  const requested = params.get('report') || 'overnight';
  selectedId = records.some(record => record.id === requested && record.mode === 'markdown') ? requested : 'overnight';
  const selected = records.find(record => record.id === selectedId);
  category = collections.has(params.get('collection')) ? params.get('collection') : selected?.category || 'Reports';
  query = (params.get('q') || '').slice(0, 200);
  journalQuery = (params.get('journal_q') || '').slice(0, 200);
  journalStatus = params.get('status') || 'all';
  $('#library-query').value = query;
  $('#library-category').value = category;
}
function writeLocation({push = false, clearHash = false} = {}) {
  const address = new URL(location.href);
  address.searchParams.set('report', selectedId);
  address.searchParams.set('collection', category);
  for (const [key, value] of [['q', query], ['journal_q', selectedId === 'journal' ? journalQuery : ''], ['status', selectedId === 'journal' && journalStatus !== 'all' ? journalStatus : '']]) {
    if (value) address.searchParams.set(key, value); else address.searchParams.delete(key);
  }
  if (clearHash) address.hash = '';
  if (address.href !== location.href) history[push ? 'pushState' : 'replaceState']({report: selectedId}, '', address);
}
function formatFor(record) {
  if (record.mode === 'markdown') return record.id === 'journal' ? 'Event journal' : 'Full report';
  if (record.category === 'Data') return 'Original JSON · new tab ↗';
  return record.id === 'repository' ? 'Repository · new tab ↗' : 'Standalone page · new tab ↗';
}
function renderList() {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const visible = records.filter(record => (category === 'all' || record.category === category) && terms.every(term =>
    `${record.title} ${record.category} ${record.description}`.toLowerCase().includes(term)));
  const list = $('#library-list');
  list.replaceChildren();
  for (const record of visible) {
    const item = node('li'), control = node(record.mode === 'markdown' ? 'button' : 'a', undefined, 'library-item');
    if (record.mode === 'markdown') {
      control.type = 'button';
      control.dataset.record = record.id;
      control.setAttribute('aria-pressed', String(record.id === selectedId));
    } else {
      control.href = sourceUrl(record.path);
      control.target = '_blank';
      control.rel = 'noopener';
    }
    control.append(node('small', record.category), node('strong', record.title), node('span', record.description), node('em', formatFor(record)));
    item.append(control);
    list.append(item);
  }
  $('#library-count').textContent = `${visible.length} of ${records.length} records${category === 'all' ? '' : ' · ' + (category === 'Data' ? 'Original data' : category)}`;
  $('#catalogue-summary-count').textContent = `${visible.length} shown`;
  $('#library-empty').hidden = visible.length > 0;
  for (const link of document.querySelectorAll('[data-reading-report]')) {
    if (link.dataset.readingReport === selectedId) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  }
}
function browseCollection(value) {
  category = value;
  query = '';
  $('#library-query').value = '';
  $('#library-category').value = value;
  catalogue.open = true;
  renderList();
  writeLocation({push: true});
  if (narrowCatalogue.matches) catalogue.scrollIntoView({block: 'start', behavior: 'instant'});
  $('#library-category').focus({preventScroll: true});
}
function prepareTables(container) {
  for (const wrapper of container.querySelectorAll('.md-table')) {
    wrapper.tabIndex = 0;
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', 'Research table; scroll horizontally for all columns');
    wrapper.before(node('p', 'Scroll the table horizontally to see all columns.', 'table-scroll-hint'));
  }
}
function makeContents(headings) {
  const toc = $('#reader-toc');
  toc.replaceChildren();
  const sections = headings.filter((heading, index) => index > 0 && heading.level === 2);
  const useful = sections.length ? sections : headings.filter((heading, index) => index > 0 && heading.level === 3);
  toc.hidden = useful.length === 0;
  if (!useful.length) return;
  const disclosure = node('details'), summary = node('summary', `On this page · ${useful.length} sections`), links = node('div', undefined, 'toc-links');
  for (const heading of useful) {
    const link = node('a', heading.text);
    link.href = '#' + heading.id;
    links.append(link);
  }
  disclosure.append(summary, links);
  toc.append(disclosure);
}
function scrollToAddressHash() {
  if (!location.hash) return;
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
  const target = document.getElementById(id);
  if (target) {
    const disclosure = target.closest('details');
    if (disclosure) disclosure.open = true;
    requestAnimationFrame(() => target.scrollIntoView({block: 'start', behavior: 'instant'}));
  }
}
function renderJournal(markdown, record) {
  const parsed = parseJournal(markdown), article = $('#research-article');
  const source = sourceUrl(record.path);
  article.replaceChildren();
  article.classList.add('is-journal');
  $('#reader-toc').replaceChildren();
  $('#reader-toc').hidden = true;
  const title = node('h2', 'Research journal');
  title.id = 'doc-granite-query-research-journal';
  const days = groupJournalEvents(parsed.events).map(group => group.day);
  const period = days.length ? ` Source event dates: ${days.at(-1)} to ${days[0]} (UTC).` : '';
  article.append(title, node('p', 'An append-only historical record. Entries describe work at their recorded time, not live jobs or current model performance.' + period, 'journal-lede'));
  const originalIntro = node('details', undefined, 'journal-intro');
  const introBody = node('div', undefined, 'journal-original');
  introBody.innerHTML = renderMarkdown(parsed.intro, {baseUrl: source}).html;
  // The feed supplies its own title; retain the source title in this historical disclosure.
  for (const heading of introBody.querySelectorAll('[id]')) heading.id = 'original-' + heading.id;
  originalIntro.append(node('summary', 'Original journal introduction · historical snapshot'), introBody);
  article.append(originalIntro);
  const filters = node('div', undefined, 'journal-filters');
  const searchLabel = node('label', 'Search every event and its full text');
  const search = node('input');
  search.id = 'journal-query'; search.type = 'search'; search.placeholder = 'Search journal'; search.maxLength = 200; search.value = journalQuery;
  searchLabel.htmlFor = search.id; searchLabel.append(search);
  const statusLabel = node('label', 'Recorded status'), status = node('select');
  status.id = 'journal-status'; statusLabel.htmlFor = status.id;
  const statuses = [...new Set(parsed.events.map(event => event.status))].sort();
  for (const value of ['all', ...statuses]) {
    const option = node('option', value === 'all' ? 'All statuses' : value.replaceAll('_', ' '));
    option.value = value; status.append(option);
  }
  if (!statuses.includes(journalStatus)) journalStatus = 'all';
  status.value = journalStatus; statusLabel.append(status);
  filters.append(searchLabel, statusLabel);
  const count = node('p', undefined, 'journal-count'); count.setAttribute('role', 'status');
  const feed = node('div', undefined, 'journal-feed');
  const more = node('button', 'Show 30 more events', 'journal-more'); more.type = 'button';
  article.append(filters, node('p', 'Newest day first · all dates and times shown in UTC. Open an event for its complete original text.', 'journal-timezone'), count, feed, more);
  let limit = 30;
  const expanded = new Set();
  // Keep an old heading bookmark usable when the journal changes presentation.
  const sourceHeadings = renderMarkdown(markdown, {baseUrl: source}).headings.filter(heading => /^\d{4}-\d{2}-\d{2}T.* \| /.test(heading.text));
  const anchors = new Map(parsed.events.map((event, index) => [event.id, sourceHeadings[index]?.id || event.id]));
  function update({reset = false, preserveHash = false} = {}) {
    if (reset) limit = 30;
    const filtered = filterJournalEvents(parsed.events, {query: journalQuery, status: journalStatus});
    const ordered = groupJournalEvents(filtered).flatMap(group => group.events);
    if (preserveHash && location.hash) {
      let hash = location.hash.slice(1);
      try { hash = decodeURIComponent(hash); } catch { /* Invalid fragments never block the feed. */ }
      const targetIndex = ordered.findIndex(event => anchors.get(event.id) === hash || event.id === hash);
      if (targetIndex >= 0) limit = Math.max(limit, targetIndex + 1);
    }
    feed.replaceChildren();
    const shown = ordered.slice(0, limit);
    count.textContent = `Showing ${shown.length} of ${filtered.length} matching events · ${parsed.events.length} total records`;
    if (!shown.length) feed.append(node('p', 'No events match these filters. Change the search or recorded status to browse the journal.', 'journal-empty'));
    for (const group of groupJournalEvents(shown)) {
      const section = node('section', undefined, 'journal-day');
      const date = new Date(group.day + 'T12:00:00Z');
      section.append(node('h3', date.toLocaleDateString('en-US', {timeZone: 'UTC', month: 'long', day: 'numeric', year: 'numeric'})));
      for (const event of group.events) {
        const disclosure = node('details', undefined, 'journal-event');
        disclosure.id = anchors.get(event.id);
        disclosure.open = expanded.has(event.id);
        const summary = node('summary'), time = node('time', new Date(event.time).toISOString().slice(11, 19));
        time.dateTime = event.timestamp;
        const badge = node('span', event.status.replaceAll('_', ' '), 'event-status');
        badge.dataset.status = event.status;
        summary.append(time, badge, node('strong', event.title));
        const content = node('div', undefined, 'event-body');
        const body = node('div');
        // Only the existing safe renderer interprets source Markdown.
        body.innerHTML = renderMarkdown(event.body, {baseUrl: source}).html;
        // Event-local heading IDs cannot collide with headings in other records.
        for (const heading of body.querySelectorAll('[id]')) {
          const oldId = heading.id;
          const nextId = event.id + '-' + oldId;
          heading.id = nextId;
          for (const link of body.querySelectorAll('a[href^="#"]')) if (link.getAttribute('href') === '#' + oldId) link.href = '#' + nextId;
        }
        prepareTables(body);
        content.append(node('p', event.timestamp + ' | ' + event.status, 'event-source-time'), body);
        disclosure.append(summary, content);
        disclosure.addEventListener('toggle', () => {
          if (disclosure.open) expanded.add(event.id); else expanded.delete(event.id);
        });
        section.append(disclosure);
      }
      feed.append(section);
    }
    more.hidden = ordered.length <= limit;
    more.textContent = `Show ${Math.min(30, Math.max(0, ordered.length - limit))} more events`;
  }
  search.addEventListener('input', () => { journalQuery = search.value; writeLocation(); update({reset: true}); });
  status.addEventListener('change', () => { journalStatus = status.value; writeLocation({push: true}); update({reset: true}); });
  more.addEventListener('click', () => {
    const oldCount = feed.querySelectorAll('.journal-event').length;
    limit += 30; update();
    const firstNew = feed.querySelectorAll('.journal-event > summary')[oldCount];
    firstNew?.focus({preventScroll: true});
  });
  journalView = {
    updateFromLocation() { search.value = journalQuery; status.value = statuses.includes(journalStatus) ? journalStatus : 'all'; journalStatus = status.value; update({reset: true, preserveHash: true}); },
    showHash() { update({preserveHash: true}); }
  };
  update({preserveHash: true});
}
function renderDocument(markdown, record) {
  const article = $('#research-article');
  journalView = null;
  article.classList.remove('is-journal');
  if (record.id === 'journal') renderJournal(markdown, record);
  else {
    const rendered = renderMarkdown(markdown, {baseUrl: sourceUrl(record.path)});
    article.innerHTML = rendered.html;
    prepareTables(article);
    makeContents(rendered.headings);
  }
  displayedId = record.id;
  scrollToAddressHash();
}
async function openRecord(id, {push = true, focus = false, force = false} = {}) {
  const record = records.find(item => item.id === id && item.mode === 'markdown');
  if (!record) return;
  const changed = selectedId !== id;
  selectedId = id;
  if (changed) { journalQuery = ''; journalStatus = 'all'; }
  if (push) writeLocation({push: true, clearHash: true});
  renderList();
  const generation = ++requestId;
  currentController?.abort();
  currentController = new AbortController();
  const controller = currentController, timeout = setTimeout(() => controller.abort(), 10000);
  const previous = cache.get(id), keepPrevious = displayedId === id && previous !== undefined;
  const article = $('#research-article'), status = $('#reader-status');
  $('#reload-report').disabled = true;
  $('#reader-label').textContent = record.category + ' / ' + record.title;
  $('#reader-source').href = sourceUrl(record.source);
  status.classList.remove('is-stale');
  status.textContent = keepPrevious && force ? 'Checking the published source… The previously loaded text remains visible.' : 'Loading the selected published source…';
  article.setAttribute('aria-busy', 'true');
  if (!keepPrevious) {
    article.classList.remove('is-journal');
    article.replaceChildren(node('h2', record.title), node('p', 'Loading the original published text. Its source is always available above.'));
    $('#reader-toc').replaceChildren(); $('#reader-toc').hidden = true;
  }
  try {
    let entry = force ? undefined : previous;
    let fetched = false;
    if (!entry) {
      const response = await fetch(sourceUrl(record.path), {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw new Error('Document unavailable');
      const markdown = await response.text();
      if (markdown.length > 1200000) throw new Error('Document too large');
      entry = {markdown, fetchedAt: Date.now()};
      if (generation !== requestId) return;
      cache.set(id, entry); fetched = true;
    }
    if (generation !== requestId) return;
    renderDocument(entry.markdown, record);
    const loadedAt = new Date(entry.fetchedAt).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
    status.textContent = `Original source · ${fetched ? 'loaded' : 'previously loaded'} ${loadedAt}`;
    if (focus) {
      if (narrowCatalogue.matches) catalogue.open = false;
      $('#reader').focus({preventScroll: true});
      if (narrowCatalogue.matches) $('#reader').scrollIntoView({behavior: 'instant', block: 'start'});
    }
  } catch {
    if (generation !== requestId) return;
    if (keepPrevious) {
      status.textContent = `Reload failed. Showing the previous source loaded ${stamp(previous.fetchedAt)}; it has not been revalidated. Open the original source or try Reload again.`;
      status.classList.add('is-stale');
    } else {
      displayedId = null; journalView = null;
      article.replaceChildren(node('h2', record.title), node('p', 'The source could not be loaded in this reader. No replacement text or result has been generated.'));
      const link = node('a', 'Open the original source ↗', 'reader-action'); link.href = sourceUrl(record.source); article.append(link);
      status.textContent = 'Source unavailable in the reader. The original source link remains available.';
    }
  } finally {
    clearTimeout(timeout);
    if (generation === requestId) { article.removeAttribute('aria-busy'); $('#reload-report').disabled = false; }
  }
}

$('#reload-report').addEventListener('click', () => openRecord(selectedId, {push: false, force: true}));
$('#library-query').addEventListener('input', event => { query = event.target.value; renderList(); writeLocation(); });
$('#library-category').addEventListener('change', event => { category = event.target.value; renderList(); writeLocation({push: true}); });
for (const button of document.querySelectorAll('[data-browse]')) button.addEventListener('click', () => browseCollection(button.dataset.browse));
for (const link of document.querySelectorAll('[data-reading-report]')) link.addEventListener('click', event => {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || !records.length) return;
  event.preventDefault();
  const record = records.find(item => item.id === link.dataset.readingReport);
  category = record.category; query = ''; $('#library-query').value = ''; $('#library-category').value = category;
  openRecord(record.id, {focus: true});
});
for (const link of document.querySelectorAll('[data-reading-collection]')) link.addEventListener('click', event => {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || !records.length) return;
  event.preventDefault(); browseCollection(link.dataset.readingCollection);
});
$('#library-list').addEventListener('click', event => {
  const button = event.target.closest('button[data-record]');
  if (button) openRecord(button.dataset.record, {focus: true});
});
$('#library-list').addEventListener('keydown', event => {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
  const controls = [...$('#library-list').querySelectorAll('.library-item')], index = controls.indexOf(event.target);
  if (index < 0) return;
  event.preventDefault();
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? controls.length - 1 : Math.max(0, Math.min(controls.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
  controls[next].focus();
});
window.addEventListener('popstate', () => {
  const prior = selectedId;
  readLocation(); renderList();
  if (prior !== selectedId) openRecord(selectedId, {push: false});
  else { journalView?.updateFromLocation(); scrollToAddressHash(); }
});
window.addEventListener('hashchange', () => { journalView?.showHash(); scrollToAddressHash(); });
try {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
  let response;
  try { response = await fetch(new URL('./catalogue.json', import.meta.url), {cache: 'no-store', signal: controller.signal}); }
  finally { clearTimeout(timeout); }
  if (!response.ok) throw new Error('Index unavailable');
  const data = await response.json();
  if (data.schema_version !== 1 || !Array.isArray(data.records)) throw new Error('Unknown index');
  const ids = new Set();
  for (const record of data.records) {
    if (!record || !['id', 'title', 'category', 'description', 'path', 'mode', 'source'].every(key => typeof record[key] === 'string') || ids.has(record.id) || !permitted(record.path) || !permitted(record.source) || !['markdown', 'link'].includes(record.mode)) throw new Error('Invalid index record');
    ids.add(record.id);
  }
  records = data.records;
  readLocation(); renderList();
  await openRecord(selectedId, {push: false});
} catch {
  $('#library-count').textContent = 'Research index unavailable';
  $('#catalogue-summary-count').textContent = 'Index unavailable';
  $('#reader-status').textContent = 'The catalogue could not be loaded. The saved summary and original source links remain available.';
}
