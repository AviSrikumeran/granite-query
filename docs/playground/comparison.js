const frame = document.querySelector('#hero-frame');
const viewport = document.querySelector('#frame-viewport');
const comparison = document.querySelector('#comparison');
const compareButton = document.querySelector('#compare-view');
const previewButton = document.querySelector('#preview-view');
const phoneButton = document.querySelector('#phone-view');
const pauseButton = document.querySelector('#pause-motion');
const message = document.querySelector('#motion-message');
const formControl = document.querySelector('#form-mode');
const referenceImage = document.querySelector('#reference-image');
const referenceState = document.querySelector('#reference-state');
const references = {box: './modal/modal-reference.jpg', layers: './modal/references/layers.jpg', stairs: './modal/references/stairs.jpg', cubes: './modal/references/cubes.jpg'};
for(const src of Object.values(references)) { const image = new Image(); image.src = src; }
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let paused = reducedMotion.matches;
function resize() { frame.style.transform = comparison.classList.contains('preview') || comparison.classList.contains('phone') ? 'none' : `scale(${viewport.clientWidth / 1280})`; }
function send(action) { frame.contentWindow?.postMessage({type: 'modal-hero-study', action, paused, form:formControl.value}, location.origin); }
function updateMotion() {
  pauseButton.setAttribute('aria-pressed', String(paused));
  pauseButton.textContent = paused ? 'Resume animation' : 'Pause animation';
  message.textContent = paused ? 'Animation paused. Choose a form to inspect it, or resume the sequence.' : 'Move the pointer to tilt and light the form; click the field to advance.';
  send('motion');
}
function changeView(mode) {
  comparison.classList.toggle('preview', mode === 'preview');
  comparison.classList.toggle('phone', mode === 'phone');
  compareButton.setAttribute('aria-pressed', String(mode === 'compare'));
  previewButton.setAttribute('aria-pressed', String(mode === 'preview'));
  phoneButton.setAttribute('aria-pressed', String(mode === 'phone'));
  resize();
  send('view');
}
compareButton.addEventListener('click', () => changeView('compare'));
previewButton.addEventListener('click', () => changeView('preview'));
phoneButton.addEventListener('click', () => changeView('phone'));
pauseButton.addEventListener('click', () => { paused = !paused; updateMotion(); });
document.querySelector('#reset-motion').addEventListener('click', () => send('reset'));
formControl.addEventListener('change', () => send('form'));
new ResizeObserver(resize).observe(viewport);
frame.addEventListener('load', () => { resize(); updateMotion(); });
window.addEventListener('message', event => {
  if(event.origin !== location.origin || event.source !== frame.contentWindow) return;
  if(event.data?.type === 'modal-hero-ready') updateMotion();
  if(event.data?.type === 'modal-hero-motion' && paused !== Boolean(event.data.paused)) {
    paused = Boolean(event.data.paused); updateMotion();
  }
  if(event.data?.type === 'modal-hero-state' && references[event.data.form]) {
    const {form,label,mode} = event.data;
    referenceImage.src = references[form];
    referenceImage.alt = `Captured Modal hero in the ${label.toLowerCase()} configuration.`;
    referenceState.textContent = `Captured state · ${label}`;
    formControl.value = mode;
  }
});
reducedMotion.addEventListener('change', event => { if(event.matches) { paused = true; updateMotion(); } });
resize();
updateMotion();
