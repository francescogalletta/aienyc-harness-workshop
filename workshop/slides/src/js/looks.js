/* Looks switcher (build.py --looks only). Every listed look's tokens are in the page,
   scoped by data-look on the root. T / Shift+T change look, D (deck.js) or the palette button
   toggles a look's primary and alternate palettes (data-palette on the root). Each look opens on
   the deck's palette setting, whatever the OS or a hosting page's data-theme says. The slide and
   step stay; visuals redraw (they watch the root). */
(function () {
  var root = document.documentElement, bar = document.querySelector('.looks-bar');
  if (!bar) return;
  var buttons = Array.prototype.slice.call(bar.querySelectorAll('[data-look-btn]'));
  var looks = buttons.map(function (b) { return b.getAttribute('data-look-btn'); });
  var mode = bar.querySelector('[data-mode-btn]');
  if (looks.indexOf(root.getAttribute('data-look')) < 0) root.setAttribute('data-look', looks[0]);

  function sync() {
    var cur = root.getAttribute('data-look'), alt = shown() === 'alternate';
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-look-btn') === cur)); });
    mode.setAttribute('aria-pressed', String(alt));
    mode.textContent = alt ? 'Alternate' : 'Primary';
    document.querySelectorAll('.look-name').forEach(function (e) { e.textContent = cur; });
  }
  function shown() { return getComputedStyle(root).getPropertyValue('--palette-shown').trim() || 'primary'; }
  function step(by) {
    var i = looks.indexOf(root.getAttribute('data-look'));
    root.setAttribute('data-look', looks[(i + by + looks.length) % looks.length]);
  }
  bar.addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    if (b.hasAttribute('data-look-btn')) root.setAttribute('data-look', b.getAttribute('data-look-btn'));
    else root.setAttribute('data-palette', shown() === 'alternate' ? 'primary' : 'alternate');
    b.blur();  /* keys go back to the deck */
  });
  /* Space or Enter on a focused button presses it; it must not also advance the slide. */
  window.addEventListener('keydown', function (e) {
    if ((e.key === ' ' || e.key === 'Enter') && e.target.closest && e.target.closest('.looks-bar')) e.stopPropagation();
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 't' || e.key === 'T') step(e.shiftKey ? -1 : 1);
  });
  new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ['data-look', 'data-palette', 'data-theme'] });
  sync();
})();
