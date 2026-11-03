import { parseSnapshot, snapshotIsOlder, ageLabel, isStale, filterEvents } from './data.mjs';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
const narrow = matchMedia('(max-width: 600px)');
const motion = { paused: false, static: reduced.matches, cubeVisible: true, pipelineVisible: false };
const field = { layout: 'assembled', phase: 0, selected: 12, pinned: false, pointer: null, expanded: 0, x: 0, y: 0 };
let animationFrame = null;
let previousFrame = 0;
let sequenceTimer = null;
let sequencePaused = false;
let selectedStage = 0;
let selectedMethod = 'ranked';
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

const cubeElements = [];
function sizeCubeView() {
  $('cube-art').setAttribute('viewBox', narrow.matches ? '110 20 540 340' : '0 0 760 420');
}
narrow.addEventListener('change', sizeCubeView);
sizeCubeView();
$('cube-field').replaceChildren();
for (let row = 0; row < 5; row++) {
  for (let column = 0; column < 5; column++) {
    const cube = document.createElementNS(NS, 'g');
    cube.classList.add('cube');
    const faces = [
      ['face-top', 'M0-24 24-11 0 2-24-11Z'],
      ['face-left', 'm-24-11 24 13v29l-24-13Z'],
      ['face-right', 'm0 2 24-13v29L0 31Z'],
    ];
    for (const [className, path] of faces) {
      const face = document.createElementNS(NS, 'path');
      face.setAttribute('d', path);
      face.classList.add(className);
      cube.append(face);
    }
    $('cube-field').append(cube);
    cubeElements.push({ element: cube, row, column, x: (column - row) * 45 + 380, y: (column + row) * 22 + 94 });
  }
}

function canMove() { return !motion.static && !motion.paused && !document.hidden; }

function selectCube(index, origin = 'SELECTED') {
  field.selected = index;
  cubeElements.forEach((cube, i) => cube.element.dataset.selected = String(i === index));
  $('cube-inspection').textContent = `UNIT ${String(index + 1).padStart(2, '0')} / ${origin}`;
}

function drawCubes() {
  const expansion = field.expanded;
  for (const cube of cubeElements) {
    const offsetX = (cube.column - cube.row) * 13 * expansion;
    const offsetY = (cube.column + cube.row - 4) * 7 * expansion;
    const distance = field.pointer ? Math.hypot(cube.x + offsetX - field.pointer.x, cube.y + offsetY - field.pointer.y) : 1000;
    const lift = canMove() && finePointer.matches ? Math.max(0, 1 - distance / 125) * 27 : 0;
    const wave = Math.sin(field.phase + cube.row * .55 + cube.column * .5) * 6;
    const middleLift = Math.max(0, 2 - Math.hypot(cube.row - 2, cube.column - 2)) * 8;
    cube.element.setAttribute('transform', `translate(${(cube.x + offsetX + field.x).toFixed(2)} ${(cube.y + offsetY - wave - lift - middleLift + field.y).toFixed(2)})`);
  }
}

function animateCubes(now) {
  animationFrame = null;
  if (!canMove() || !motion.cubeVisible) { previousFrame = 0; return; }
  const elapsed = previousFrame ? Math.min(now - previousFrame, 40) : 16;
  previousFrame = now;
  field.phase += elapsed * .00065;
  const blend = 1 - Math.exp(-elapsed / 130);
  field.expanded += ((field.layout === 'expanded' ? 1 : 0) - field.expanded) * blend;
  const targetX = field.pointer && finePointer.matches ? (field.pointer.x - 380) * .018 : 0;
  const targetY = field.pointer && finePointer.matches ? (field.pointer.y - 210) * .012 : 0;
  field.x += (targetX - field.x) * blend;
  field.y += (targetY - field.y) * blend;
  drawCubes();
  animationFrame = requestAnimationFrame(animateCubes);
}

function syncMotion() {
  const active = canMove();
  document.body.dataset.motion = String(active);
  document.body.classList.toggle('is-static', motion.static);
  $('motion-toggle').disabled = motion.static;
  $('motion-toggle').setAttribute('aria-pressed', String(motion.paused || motion.static));
  $('motion-toggle').replaceChildren(document.createTextNode(motion.paused ? 'Resume motion' : 'Pause motion'));
  $('static-mode').checked = motion.static;
  $('motion-status').textContent = motion.static ? 'Static mode · select and inspect without movement.' : motion.paused ? 'Motion paused · selection controls remain available.' : 'Motion on · automatically rests when out of view.';
  if (active && motion.cubeVisible && !animationFrame) animationFrame = requestAnimationFrame(animateCubes);
  if ((!active || !motion.cubeVisible) && animationFrame) {
    cancelAnimationFrame(animationFrame); animationFrame = null; previousFrame = 0;
  }
  if (motion.static) {
    field.phase = 0; field.pointer = null; field.x = 0; field.y = 0;
    field.expanded = field.layout === 'expanded' ? 1 : 0;
    drawCubes();
  }
  scheduleSequence();
}

$('motion-toggle').addEventListener('click', () => { motion.paused = !motion.paused; syncMotion(); });
$('static-mode').addEventListener('change', event => { motion.static = event.target.checked; syncMotion(); });
reduced.addEventListener('change', event => {
  // A system request for reduced motion always wins. Turning it off does not start motion unexpectedly.
  if (event.matches) { motion.static = true; syncMotion(); }
});
document.querySelectorAll('[data-layout]').forEach(button => {
  button.addEventListener('click', () => {
    field.layout = button.dataset.layout;
    document.querySelectorAll('[data-layout]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    $('cube-layout-label').textContent = `${field.layout === 'assembled' ? 'ASSEMBLED' : 'EXPANDED'} / 25 UNITS`;
    if (!canMove()) { field.expanded = field.layout === 'expanded' ? 1 : 0; drawCubes(); }
  });
});
$('inspect-cube').addEventListener('click', () => { field.pinned = true; selectCube((field.selected + 1) % cubeElements.length, 'PINNED'); });
$('cube-stage').addEventListener('pointermove', event => {
  if (!canMove() || !finePointer.matches || event.pointerType === 'touch') return;
  const bounds = $('cube-art').getBoundingClientRect();
  const view = $('cube-art').viewBox.baseVal;
  const scale = Math.min(bounds.width / view.width, bounds.height / view.height);
  field.pointer = {
    x: (event.clientX - bounds.left - (bounds.width - view.width * scale) / 2) / scale + view.x,
    y: (event.clientY - bounds.top - (bounds.height - view.height * scale) / 2) / scale + view.y,
  };
  if (!field.pinned) {
    let nearest = 0, best = Infinity;
    cubeElements.forEach((cube, i) => { const distance = Math.hypot(cube.x - field.pointer.x, cube.y - field.pointer.y); if (distance < best) { best = distance; nearest = i; } });
    selectCube(nearest, 'POINTER');
  }
});
$('cube-stage').addEventListener('pointerleave', () => { field.pointer = null; if (!field.pinned) selectCube(12, 'CENTER'); });
$('cube-stage').addEventListener('click', () => { field.pinned = !field.pinned; selectCube(field.selected, field.pinned ? 'PINNED' : 'SELECTED'); });

const stages = [
  ['Generate teacher examples', 'DeepSeek produces candidate mathematical solutions from the eligible training pool. Teacher output is an input to the experiment, not evidence of student improvement.'],
  ['Verify before selecting', 'Check the final numeric answer and required format. Examples that fail verification are excluded from the eligible pool; failed checks remain part of the research record.'],
  ['Select the training subset', 'BM25 ranks eligible examples by relevance. The random control draws from the same eligible pool. Comparable budgets make the selection strategy the question under study.'],
  ['Fine-tune the student', 'Train Granite on the selected teacher examples. Record the model revision, seed, training tokens, and cost. This illustration does not launch or monitor a Modal job.'],
  ['Compare measured outcomes', 'Evaluate on separate development questions, compare against the random control, and report limitations. Development results are not final-test results or proof of general improvement.'],
];
const nodes = [...document.querySelectorAll('[data-stage]')];

function renderStage() {
  nodes.forEach((button, index) => button.setAttribute('aria-pressed', String(index === selectedStage)));
  $('stage-index').textContent = `${String(selectedStage + 1).padStart(2, '0')} / 05`;
  $('stage-name').textContent = selectedStage === 2 ? (selectedMethod === 'ranked' ? 'Rank by BM25 relevance' : 'Draw the random control') : stages[selectedStage][0];
  $('stage-copy').textContent = selectedStage === 2 ? (selectedMethod === 'ranked' ? 'BM25 ranks verified candidates by relevance. Compare the selected subset with the random arm from the same eligible pool, and disclose training-token differences.' : 'Random selection draws from the same verified candidate pool. This is the control arm; the animation gives neither method a winning outcome.') : stages[selectedStage][1];
  $('pipeline-fill').style.width = `${selectedStage * 25}%`;
}

function scheduleSequence() {
  clearTimeout(sequenceTimer);
  sequenceTimer = null;
  const animate = canMove() && motion.pipelineVisible && !sequencePaused;
  document.body.dataset.sequence = String(animate);
  $('sequence-toggle').textContent = sequencePaused ? 'Play sequence' : 'Pause sequence';
  $('sequence-status').textContent = motion.static ? 'Static preview · choose a stage' : motion.paused ? 'Global motion paused' : sequencePaused ? 'Inspection pinned · sequence paused' : 'Automatic walkthrough';
  if (animate) sequenceTimer = setTimeout(() => { selectedStage = (selectedStage + 1) % stages.length; renderStage(); scheduleSequence(); }, selectedStage === 4 ? 3000 : 2200);
}

function inspectStage(index) { selectedStage = index; sequencePaused = true; renderStage(); scheduleSequence(); }
nodes.forEach((button, index) => {
  button.addEventListener('click', () => inspectStage(index));
  button.addEventListener('focus', () => inspectStage(index));
  button.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') inspectStage(index); });
  button.addEventListener('keydown', event => {
    let next = index;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % nodes.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + nodes.length - 1) % nodes.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = nodes.length - 1;
    else return;
    event.preventDefault(); nodes[next].focus();
  });
});
document.querySelectorAll('[data-method]').forEach(button => button.addEventListener('click', () => {
  selectedMethod = button.dataset.method;
  document.querySelectorAll('[data-method]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  inspectStage(2);
}));
$('sequence-toggle').addEventListener('click', () => { sequencePaused = !sequencePaused; scheduleSequence(); });
$('sequence-replay').addEventListener('click', () => { selectedStage = 0; sequencePaused = false; renderStage(); scheduleSequence(); });

const visibilityObserver = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (entry.target.id === 'cube-stage') motion.cubeVisible = entry.isIntersecting;
    else motion.pipelineVisible = entry.isIntersecting;
  }
  syncMotion();
}, { threshold: .08 });
visibilityObserver.observe($('cube-stage'));
visibilityObserver.observe($('pipeline-route'));

// Evidence is a read-only view of the existing published file. Demo states never alter it.
let snapshot = null;
let filter = 'all';
let selectedEventId = null;
let mode = 'published';
let fetchState = 'loading';
let fetchMessage = '';
let currentRequest = null;
let requestSerial = 0;
let eventSignature = '';

function text(id, value) { $(id).textContent = value; }
function prettyKind(kind) { return kind.replaceAll('_', ' '); }
function shownSnapshot() {
  if (mode === 'empty') return { generated: new Date().toISOString(), stage: 'No snapshot in this sample', next: 'Return to Published data to read the research record.', caveat: 'STATE SAMPLE · No project metrics or events are shown.', teacher: null, passes: null, events: [] };
  return snapshot;
}

function renderEventDetail(data) {
  const selected = data?.events.find(event => event.id === selectedEventId);
  $('event-detail').hidden = !selected;
  if (!selected) return;
  text('event-detail-kind', prettyKind(selected.kind));
  text('event-detail-title', selected.title);
  text('event-detail-copy', selected.detail || 'No further public detail was provided.');
  text('event-detail-time', dateFormat.format(new Date(selected.at)));
  $('event-detail-time').dateTime = selected.at;
}

function renderEvents(data) {
  const events = filterEvents(data?.events || [], filter);
  text('event-count', `${events.length} ${events.length === 1 ? 'event' : 'events'}`);
  // Keep event buttons, focus, and the scroll position stable across snapshot checks.
  const signature = JSON.stringify([mode, filter, events.map(event => [event.id, event.title, event.kind, event.at])]);
  if (signature !== eventSignature) {
    const list = $('event-list');
    const oldScroll = list.scrollTop;
    const focusedId = document.activeElement?.dataset?.eventId;
    list.replaceChildren();
    if (!events.length) {
      const empty = document.createElement('p'); empty.className = 'empty-state';
      empty.textContent = data ? 'No events in this view. Try another filter.' : 'The research record is unavailable. Try Refresh.';
      list.append(empty);
    }
    for (const event of events.slice(0, 20)) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'event-row';
      button.dataset.eventId = event.id; button.setAttribute('aria-controls', 'event-detail');
      const meta = document.createElement('span'); meta.className = 'event-meta';
      const kind = document.createElement('span'); kind.textContent = prettyKind(event.kind);
      const time = document.createElement('time'); time.dateTime = event.at; time.textContent = ageLabel(event.at);
      meta.append(kind, time);
      const title = document.createElement('strong'); title.textContent = event.title;
      button.append(meta, title);
      button.addEventListener('click', () => { selectedEventId = selectedEventId === event.id ? null : event.id; updateSelectedEvent(); });
      list.append(button);
    }
    eventSignature = signature;
    list.scrollTop = oldScroll;
    if (focusedId) [...list.querySelectorAll('button')].find(button => button.dataset.eventId === focusedId)?.focus({ preventScroll: true });
  }
  if (!events.some(event => event.id === selectedEventId)) selectedEventId = null;
  for (const button of $('event-list').querySelectorAll('[data-event-id]')) {
    const event = events.find(item => item.id === button.dataset.eventId);
    if (event) button.querySelector('time').textContent = ageLabel(event.at);
  }
  updateSelectedEvent();
}

function updateSelectedEvent() {
  document.querySelectorAll('[data-event-id]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.eventId === selectedEventId)));
  renderEventDetail(shownSnapshot());
}

function renderEvidence() {
  const sample = mode !== 'published';
  const data = shownSnapshot();
  text('source-label', sample ? 'State sample · not project status' : 'Published snapshot');
  const checking = !sample && fetchState === 'loading';
  const loading = mode === 'loading' || (checking && !data);
  const failure = mode === 'error' || (!sample && fetchState === 'error');
  const stale = mode === 'stale' || (data && isStale(data));
  const summary = $('snapshot-summary');
  summary.hidden = loading;
  $('event-list').hidden = loading;
  $('event-detail').hidden = loading;
  let message;
  if (loading) message = sample ? 'STATE SAMPLE · Loading the public snapshot…' : 'Checking the published snapshot…';
  else if (failure) message = `${sample ? 'STATE SAMPLE · ' : ''}Refresh failed. ${data ? 'Showing the last valid published snapshot.' : 'No snapshot is available yet.'} ${sample ? 'Use Published data to return.' : fetchMessage}`;
  else if (mode === 'empty') message = 'STATE SAMPLE · Empty state; no project data.';
  else if (stale) message = mode === 'stale' ? 'STATE SAMPLE · Stale display. The timestamp below is still the real snapshot time.' : 'Snapshot is over 30 minutes old. This is a published record, not a live stream.';
  else message = checking ? 'Checking for updates · previous snapshot remains available.' : 'Public data · checked successfully. Refreshes every 60 seconds.';
  text('fetch-status', message);
  $('fetch-status').dataset.warning = String(!!failure || !!stale);
  $('refresh-evidence').disabled = checking;
  if (data && !loading) {
    text('research-stage', data.stage);
    text('research-next', data.next || 'No next action was published.');
    text('teacher-count', data.teacher ?? 'Not measured');
    text('verification-count', data.passes === null || data.teacher === null ? 'Not measured' : `${data.passes} / ${data.teacher}`);
    text('research-caveat', data.caveat);
    text('snapshot-time', `Published ${dateFormat.format(new Date(data.generated))} · ${ageLabel(data.generated)}`);
  } else if (!loading) {
    text('research-stage', 'Snapshot unavailable'); text('research-next', 'Use Refresh to try again.');
    text('teacher-count', '—'); text('verification-count', '—'); text('snapshot-time', 'Snapshot time unavailable');
    text('research-caveat', 'No project metrics are inferred while data is unavailable.');
  }
  if (!loading) renderEvents(data);
}

async function refreshEvidence() {
  if (mode !== 'published' || document.hidden) return;
  currentRequest?.abort();
  const controller = new AbortController();
  currentRequest = controller;
  const serial = ++requestSerial;
  fetchState = 'loading'; renderEvidence();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(new URL('../status.json', location.href), { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const candidate = parseSnapshot(await response.json());
    if (serial !== requestSerial || mode !== 'published') return;
    if (snapshotIsOlder(candidate, snapshot)) throw new Error('An older snapshot was returned; the newer record was retained.');
    snapshot = candidate; fetchState = 'ready'; fetchMessage = '';
  } catch (error) {
    if (serial !== requestSerial || mode !== 'published') return;
    fetchState = 'error'; fetchMessage = error.name === 'AbortError' ? 'The request timed out or was interrupted.' : error.message;
  } finally {
    clearTimeout(timeout);
    if (serial === requestSerial) { currentRequest = null; renderEvidence(); }
  }
}

document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  renderEvents(shownSnapshot());
}));
$('evidence-mode').addEventListener('change', event => {
  mode = event.target.value;
  requestSerial++; currentRequest?.abort(); currentRequest = null;
  selectedEventId = null; eventSignature = '';
  if (mode === 'published') refreshEvidence(); else renderEvidence();
});
$('refresh-evidence').addEventListener('click', () => {
  mode = 'published'; $('evidence-mode').value = 'published'; refreshEvidence();
});
let refreshInterval = setInterval(() => {
  if (!document.hidden && mode === 'published') refreshEvidence();
}, 60000);
document.addEventListener('visibilitychange', () => {
  syncMotion();
  if (!document.hidden && mode === 'published') refreshEvidence();
  else if (document.hidden) { requestSerial++; currentRequest?.abort(); currentRequest = null; }
});

// Enable controls only after the module has initialized successfully.
document.querySelectorAll('button:disabled, input:disabled, select:disabled').forEach(control => control.disabled = false);
selectCube(12, 'CENTER'); renderStage(); syncMotion(); refreshEvidence();
addEventListener('pagehide', () => {
  clearTimeout(sequenceTimer); clearInterval(refreshInterval);
  if (animationFrame) cancelAnimationFrame(animationFrame);
  animationFrame = null; previousFrame = 0;
  requestSerial++;
  currentRequest?.abort(); visibilityObserver.disconnect();
});
addEventListener('pageshow', event => {
  if (!event.persisted) return;
  visibilityObserver.observe($('cube-stage')); visibilityObserver.observe($('pipeline-route'));
  refreshInterval = setInterval(() => { if (!document.hidden && mode === 'published') refreshEvidence(); }, 60000);
  syncMotion(); refreshEvidence();
});
