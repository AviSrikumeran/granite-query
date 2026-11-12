(() => {
  'use strict';

  document.querySelectorAll('.gq-site-header').forEach((header) => {
    const button = header.querySelector('.gq-menu-toggle');
    const nav = button && document.getElementById(button.getAttribute('aria-controls'));
    if (!button || !nav) return;

    const close = (restoreFocus = false) => {
      button.setAttribute('aria-expanded', 'false');
      nav.classList.remove('is-open');
      if (restoreFocus) button.focus();
    };

    button.addEventListener('click', () => {
      const expanded = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', String(expanded));
      nav.classList.toggle('is-open', expanded);
    });
    header.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') {
        event.preventDefault();
        close(true);
      }
    });
    nav.addEventListener('click', (event) => {
      if (event.target.closest('a')) close();
    });
    document.addEventListener('pointerdown', (event) => {
      if (!header.contains(event.target)) close();
    });
    document.addEventListener('focusin', (event) => {
      if (!header.contains(event.target)) close();
    });
    const desktop = window.matchMedia('(min-width: 651px)');
    desktop.addEventListener('change', () => close());
  });

  const main = document.getElementById('gq-content');
  if (!main || main.querySelector('.gq-contents')) return;
  const contents = document.createElement('details');
  contents.className = 'gq-contents';
  const summary = document.createElement('summary');
  summary.textContent = 'On this page';
  contents.append(summary);

  // Preserve the model note's existing section names and destinations.
  const existing = main.querySelector('nav[aria-label="Research sections"]');
  if (existing) {
    existing.before(contents);
    existing.classList.add('gq-contents-links');
    contents.append(existing);
    return;
  }

  // Read the document outline once. Generated event logs never become contents.
  const headings = Array.from(main.querySelectorAll('h2')).filter((heading) => {
    if (heading.closest('#timeline, #events, .timeline, .event, article')) return false;
    return heading.textContent.trim().length > 0;
  }).slice(0, 10);
  if (headings.length < 2) return;

  const nav = document.createElement('nav');
  nav.className = 'gq-contents-links';
  nav.setAttribute('aria-label', 'On this page');
  headings.forEach((heading, index) => {
    if (!heading.id) {
      let id = `gq-section-${index + 1}`;
      while (document.getElementById(id)) id += '-section';
      heading.id = id;
    }
    const link = document.createElement('a');
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent.replace(/\s+/g, ' ').trim();
    nav.append(link);
  });
  contents.append(nav);
  const intro = main.querySelector('h1')?.closest('section');
  if (intro && intro.parentElement === main) intro.after(contents);
  else {
    const firstSection = Array.from(main.children).find((child) => child.tagName === 'SECTION');
    if (firstSection) firstSection.before(contents);
    else main.append(contents);
  }
})();

// Shared identity for standalone reading pages; report text remains untouched.
import('./gq-navigation.js?v=20261111-1').catch(()=>{});
