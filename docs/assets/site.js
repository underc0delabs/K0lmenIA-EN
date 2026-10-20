// k0lmenIA · documentation site behavior (theme, navigation, copy code).
(function () {
  const root = document.documentElement;

  // ---------------------------------------------------------------- light / dark theme
  const save = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* no storage */ } };
  const read = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const savedTheme = read('k0lmenia-theme');
  if (savedTheme === 'light' || savedTheme === 'dark') root.setAttribute('data-theme', savedTheme);

  function currentTheme() {
    const t = root.getAttribute('data-theme');
    if (t) return t;
    return 'dark'; // like k0lmena.com: dark unless the person picks light
  }
  function renderButton() {
    const b = document.getElementById('toggle-theme');
    if (!b) return;
    const dark = currentTheme() === 'dark';
    b.setAttribute('aria-label', dark ? 'Use the light theme' : 'Use the dark theme');
    b.querySelector('.sun').style.display = dark ? 'block' : 'none';
    b.querySelector('.moon').style.display = dark ? 'none' : 'block';
  }

  document.addEventListener('DOMContentLoaded', () => {
    renderButton();
    document.getElementById('toggle-theme')?.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      save('k0lmenia-theme', next);
      renderButton();
    });

    // -------------------------------------------------------------- mobile navigation
    const body = document.body;
    document.getElementById('open-nav')?.addEventListener('click', () => body.classList.toggle('nav-open'));
    document.querySelectorAll('.sidebar a').forEach((a) => a.addEventListener('click', () => body.classList.remove('nav-open')));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') body.classList.remove('nav-open'); });
    document.addEventListener('click', (e) => {
      if (body.classList.contains('nav-open') && !e.target.closest('.sidebar') && !e.target.closest('#open-nav')) body.classList.remove('nav-open');
    });

    // -------------------------------------------------------------- active section in the menu
    const links = new Map();
    document.querySelectorAll('.sidebar a[href^="#"]').forEach((a) => links.set(a.getAttribute('href').slice(1), a));
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        links.forEach((a) => a.classList.remove('active'));
        links.get(en.target.id)?.classList.add('active');
      });
    }, { rootMargin: '-20% 0px -70% 0px' });
    document.querySelectorAll('.section[id]').forEach((s) => observer.observe(s));

    // -------------------------------------------------------------- search (Ctrl K or /)
    initSearch();

    // -------------------------------------------------------------- copy code blocks
    document.querySelectorAll('.code-block').forEach((block) => {
      const pre = block.querySelector('pre');
      if (!pre) return;
      const button = document.createElement('button');
      button.className = 'copy';
      button.type = 'button';
      button.textContent = 'Copy';
      button.addEventListener('click', async () => {
        const text = pre.innerText.replace(/\s+#.*$/gm, '').trim(); // without the comments
        try {
          await navigator.clipboard.writeText(text);
          button.textContent = 'Copied';
        } catch (e) {
          button.textContent = 'Could not copy';
        }
        setTimeout(() => { button.textContent = 'Copy'; }, 1600);
      });
      block.appendChild(button);
    });
  });

  // ---------------------------------------------------------------- search
  // Index built on the fly from the text of each section (headings, paragraphs, lists, tables and code);
  // no dependencies. Ignores case and accents ("resume" finds "Résumé").
  const TEXTS = {
    ph: 'Search the documentation…', empty: 'No results for', help: 'Type at least 2 letters.',
    footer: ['↑↓ to move', 'Enter to go', 'Esc to close'],
  };
  const normalize = (t) => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const escape = (t) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function initSearch() {
    const button = document.getElementById('open-search');
    if (!button) return;
    const T = TEXTS;
    const panel = document.createElement('div');
    panel.className = 'search';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.innerHTML = `<div class="box"><label class="field"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
      <input type="search" autocomplete="off" spellcheck="false" placeholder="${T.ph}" aria-label="${T.ph}"><kbd>Esc</kbd></label>
      <ul class="results" role="listbox"></ul><div class="footer-b">${T.footer.map((x) => `<span>${x}</span>`).join('')}</div></div>`;
    document.body.appendChild(panel);
    const field = panel.querySelector('input');
    const list = panel.querySelector('.results');
    let index = null;
    let current = [];
    let sel = 0;

    function buildIndex() {
      const items = [];
      document.querySelectorAll('.section[id]').forEach((sec) => {
        const title = (sec.querySelector('h2')?.textContent || '').trim();
        if (!title) return;
        items.push({ sec, title, el: sec.querySelector('h2'), text: title, weight: 3 });
        sec.querySelectorAll('h3, h4, p, li, td, .request, pre, figcaption').forEach((el) => {
          if (el.closest('td') && el.tagName !== 'TD') return;
          const text = el.textContent.replace(/\s+/g, ' ').trim();
          if (text.length < 3) return;
          items.push({ sec, title, el, text, weight: /^H[34]$/.test(el.tagName) ? 2 : 1 });
        });
      });
      items.forEach((it) => { it.norm = normalize(it.text); it.normTitle = normalize(it.title); });
      return items;
    }

    function snippet(text, terms) {
      const norm = normalize(text);
      const pos = Math.max(0, norm.indexOf(terms[0]));
      const start = Math.max(0, pos - 60);
      let piece = (start > 0 ? '…' : '') + text.slice(start, start + 180) + (text.length > start + 180 ? '…' : '');
      let html = escape(piece);
      terms.forEach((t) => {
        if (!t) return;
        // accent-insensitive highlighting: search the normalized version and mark the original
        const n = normalize(html);
        let out = '';
        let i = 0;
        let j;
        while ((j = n.indexOf(t, i)) >= 0) {
          out += html.slice(i, j) + '<mark>' + html.slice(j, j + t.length) + '</mark>';
          i = j + t.length;
        }
        html = out + html.slice(i);
      });
      return html;
    }

    function search(q) {
      index = index || buildIndex();
      const terms = normalize(q).split(/\s+/).filter((t) => t.length > 0);
      if (normalize(q).replace(/\s/g, '').length < 2) {
        current = [];
        list.innerHTML = `<li class="empty">${T.help}</li>`;
        return;
      }
      const seen = new Set();
      current = index
        .filter((it) => terms.every((t) => it.norm.includes(t) || it.normTitle.includes(t)) && terms.some((t) => it.norm.includes(t)))
        .map((it) => ({ it, score: it.weight * 10 + (it.normTitle.includes(terms[0]) ? 5 : 0) - Math.min(it.text.length / 400, 3) }))
        .sort((a, b) => b.score - a.score)
        .filter(({ it }) => {
          const key = it.sec.id + '|' + it.text.slice(0, 80);
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        })
        .slice(0, 30)
        .map((x) => x.it);
      sel = 0;
      if (!current.length) {
        list.innerHTML = `<li class="empty">${T.empty} “${escape(q)}”.</li>`;
        return;
      }
      list.innerHTML = current.map((it, i) => `<li><a href="#${it.sec.id}" data-i="${i}" role="option"${i === 0 ? ' class="sel" aria-selected="true"' : ''}>
        <span class="sec">${escape(it.title)}</span><span class="frag">${snippet(it.text, terms)}</span></a></li>`).join('');
    }

    function mark(i) {
      const links = list.querySelectorAll('a');
      if (!links.length) return;
      sel = (i + links.length) % links.length;
      links.forEach((a, k) => { a.classList.toggle('sel', k === sel); a.setAttribute('aria-selected', k === sel ? 'true' : 'false'); });
      links[sel].scrollIntoView({ block: 'nearest' });
    }

    function go(i) {
      const it = current[i];
      if (!it) return;
      close();
      it.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      history.replaceState(null, '', '#' + it.sec.id);
      it.el.classList.add('search-highlight');
      setTimeout(() => it.el.classList.remove('search-highlight'), 2200);
    }

    function open() {
      panel.classList.add('open');
      field.value = '';
      search('');
      setTimeout(() => field.focus(), 0);
    }
    function close() { panel.classList.remove('open'); }

    button.addEventListener('click', open);
    field.addEventListener('input', () => search(field.value));
    field.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); mark(sel + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); mark(sel - 1); }
      else if (e.key === 'Enter') { e.preventDefault(); go(sel); }
      else if (e.key === 'Escape') close();
    });
    list.addEventListener('click', (e) => {
      const a = e.target.closest('a[data-i]');
      if (!a) return;
      e.preventDefault();
      go(parseInt(a.dataset.i, 10));
    });
    panel.addEventListener('click', (e) => { if (e.target === panel) close(); });
    document.addEventListener('keydown', (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '');
      if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing)) { e.preventDefault(); open(); }
      else if (e.key === 'Escape' && panel.classList.contains('open')) close();
    });
  }
})();
