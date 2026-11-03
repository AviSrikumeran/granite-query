const frame = document.querySelector('#hero-frame');
const viewport = document.querySelector('#frame-viewport');
const comparison = document.querySelector('#comparison');
const compareButton = document.querySelector('#compare-view');
const previewButton = document.querySelector('#preview-view');
const phoneButton = document.querySelector('#phone-view');
const pauseButton = document.querySelector('#pause-motion');
const message = document.querySelector('#motion-message');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let paused = reducedMotion.matches;
function resize() { frame.style.transform = comparison.classList.contains('preview') || comparison.classList.contains('phone') ? 'none' : `scale(${viewport.clientWidth / 1280})`; }
function send(action) { frame.contentWindow?.postMessage({type: 'modal-hero-study', action, paused}, location.origin); }
function updateMotion() {
  pauseButton.setAttribute('aria-pressed', String(paused));
  pauseButton.textContent = paused ? 'Resume animation' : 'Pause animation';
  message.textContent = paused ? 'Animation paused. Resume to try pointer displacement and click pulses.' : 'Move the pointer through the live field; click to send a pulse.';
  send('motion');
}
function changeView(mode) {
  comparison.classList.toggle('preview', mode === 'preview');
  comparison.classList.toggle('phone', mode === 'phone');
  compareButton.setAttribute('aria-pressed', String(mode === 'compare'));
  previewButton.setAttribute('aria-pressed', String(mode === 'preview'));
  phoneButton.setAttribute('aria-pressed', String(mode === 'phone'));
  resize();
}
compareButton.addEventListener('click', () => changeView('compare'));
previewButton.addEventListener('click', () => changeView('preview'));
phoneButton.addEventListener('click', () => changeView('phone'));
pauseButton.addEventListener('click', () => { paused = !paused; updateMotion(); });
document.querySelector('#reset-motion').addEventListener('click', () => send('reset'));
new ResizeObserver(resize).observe(viewport);
frame.addEventListener('load', () => { resize(); updateMotion(); });
window.addEventListener('message', event => {
  if(event.origin !== location.origin || event.source !== frame.contentWindow) return;
  if(event.data?.type === 'modal-hero-ready') updateMotion();
  if(event.data?.type === 'modal-hero-motion' && paused !== Boolean(event.data.paused)) {
    paused = Boolean(event.data.paused); updateMotion();
  }
});
reducedMotion.addEventListener('change', event => { if(event.matches) { paused = true; updateMotion(); } });
resize();
updateMotion();
