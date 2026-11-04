const menu=document.querySelector('.menu-toggle'),nav=document.querySelector('#main-nav');
function closeMenu(focus=false){menu.setAttribute('aria-expanded','false');nav.classList.remove('is-open');if(focus)menu.focus();}
menu.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));nav.classList.toggle('is-open',open);});
nav.addEventListener('click',event=>{if(event.target.closest('a'))closeMenu();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.getAttribute('aria-expanded')==='true')closeMenu(true);});
matchMedia('(min-width:651px)').addEventListener('change',event=>{if(event.matches)closeMenu();});

// Previously published deep links keep reaching their detailed research section.
const detailAnchors=new Set(['#results','#method','#cost','#selected-evidence','#evidence']);
if(detailAnchors.has(location.hash))location.replace(new URL('results/'+location.hash,location.href).href);

// The artwork is isolated from research loading and has no testing toolbar.
const container=document.querySelector('#hero-material');
import('./hero.js?v=20261104-3').then(({initHero})=>initHero(container)).catch(()=>container.setAttribute('aria-label','Electric magenta material illustration.'));
