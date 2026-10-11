/* Navigation and build steps. Keys: arrows/Space/Enter/PageUp/PageDown/Home/End,
   F fullscreen, D light/dark. Click right two-thirds = next, left third = back.
   Swipe on touch. #n in the address opens slide n and is kept up to date. */
var doc = document, root = doc.documentElement;
var viewport = doc.getElementById('viewport');
var stage = doc.getElementById('stage');
var bar = doc.getElementById('progress');
var counter = doc.getElementById('counter');
var slides = Array.prototype.slice.call(stage.querySelectorAll('.slide'));
var railCells = Array.prototype.slice.call(stage.querySelectorAll('.rail-cell'));
var N = slides.length;
var idx = 0, step = 0;
var STEP_ATTRS = ['data-step', 'data-step-out', 'data-step-fill', 'data-step-strike', 'data-step-mute'];

function stepsOf(s) {
  var m = 0;
  STEP_ATTRS.forEach(function (a) {
    s.querySelectorAll('[' + a + ']').forEach(function (el) { m = Math.max(m, +el.getAttribute(a) || 0); });
  });
  var reel = s.querySelector('.emoji-reel');
  if (reel) m = Math.max(m, reel.children.length + 1);
  return m;
}
var steps = slides.map(stepsOf);

function fit() {
  var s = Math.min(viewport.clientWidth / 1920, viewport.clientHeight / 1080);
  stage.style.transform = 'scale(' + s + ')';
}

function setHash(n) {
  var h = '#' + n;
  if (location.hash === h) return;
  try { history.replaceState(null, '', h); }
  catch (e) { try { location.replace(h); } catch (e2) {} }
}

function toggleBy(s, attr, cls) {
  s.querySelectorAll('[' + attr + ']').forEach(function (el) {
    el.classList.toggle(cls, (+el.getAttribute(attr) || 0) <= step);
  });
}

/* Rail: cells before the active slide's principle are done, its own is now. */
function markRail(s) {
  var p = s.getAttribute('data-principle'), at = +p;
  railCells.forEach(function (c) {
    var n = +c.getAttribute('data-n');
    c.classList.toggle('done', p === 'wrap' || n < at);
    c.classList.toggle('now', n === at);
  });
}

function render(entering) {
  var s = slides[idx];
  if (entering) {
    s.classList.add('instant');
    requestAnimationFrame(function () { requestAnimationFrame(function () { s.classList.remove('instant'); }); });
  }
  slides.forEach(function (el, i) { el.classList.toggle('active', i === idx); });
  toggleBy(s, 'data-step', 'shown');
  toggleBy(s, 'data-step-out', 'gone');
  toggleBy(s, 'data-step-fill', 'filled');
  toggleBy(s, 'data-step-strike', 'struck');
  toggleBy(s, 'data-step-mute', 'muted');
  var reel = s.querySelector('.emoji-reel');
  if (reel) {
    Array.prototype.forEach.call(reel.children, function (li, i) {
      li.classList.toggle('spot', i === step - 1);
      li.classList.toggle('out', i < step - 1);
    });
  }
  markRail(s);
  bar.style.width = ((idx + 1) / N * 100) + '%';
  counter.textContent = (idx + 1) + ' / ' + N;
  setHash(idx + 1);
}

function next() {
  if (step < steps[idx]) {
    step++; render(false);
    var s = slides[idx];
    if (s.querySelector('[data-confetti][data-step="' + step + '"]')) {
      confetti(s.querySelector('.trust'), stage, function () { return slides[idx] === s; });
    }
  }
  else if (idx < N - 1) { idx++; step = 0; render(true); }
}

function prev() {
  if (step > 0) { step--; render(false); }
  else if (idx > 0) { idx--; step = steps[idx]; render(true); }
}
function goTo(i) {
  idx = Math.max(0, Math.min(N - 1, i)); step = 0;
  render(true);
}
function fromHash() {
  var n = parseInt((location.hash || '').replace('#', ''), 10);
  return isNaN(n) ? null : n - 1;
}

function toggleFullscreen() {
  try {
    if (!doc.fullscreenElement) {
      var p = root.requestFullscreen && root.requestFullscreen();
      if (p && p.catch) p.catch(function () {});
    } else {
      var q = doc.exitFullscreen && doc.exitFullscreen();
      if (q && q.catch) q.catch(function () {});
    }
  } catch (e) {}
}
function toggleTheme() {
  var cur = root.getAttribute('data-theme');
  if (!cur) cur = (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  root.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
}

doc.addEventListener('keydown', function (e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  var k = e.key;
  var onLink = e.target && e.target.closest && e.target.closest('a, button');
  if (k === 'ArrowRight' || k === 'PageDown' || k === ' ' || k === 'Spacebar' || (k === 'Enter' && !onLink)) { e.preventDefault(); next(); }
  else if (k === 'ArrowLeft' || k === 'PageUp' || k === 'Backspace') { e.preventDefault(); prev(); }
  else if (k === 'Home') { e.preventDefault(); goTo(0); }
  else if (k === 'End') { e.preventDefault(); goTo(N - 1); }
  else if (k === 'f' || k === 'F') { toggleFullscreen(); }
  else if (k === 'd' || k === 'D') { toggleTheme(); }
});

var swipedAt = 0, tx = 0, ty = 0, tracking = false;
viewport.addEventListener('touchstart', function (e) {
  if (e.touches.length !== 1) { tracking = false; return; }
  tracking = true; tx = e.touches[0].clientX; ty = e.touches[0].clientY;
}, { passive: true });
viewport.addEventListener('touchend', function (e) {
  if (!tracking) return; tracking = false;
  var t = e.changedTouches[0], dx = t.clientX - tx, dy = t.clientY - ty;
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.2) {
    swipedAt = Date.now();
    if (dx < 0) next(); else prev();
  }
}, { passive: true });
viewport.addEventListener('click', function (e) {
  if (Date.now() - swipedAt < 500) return;
  if (e.target.closest && e.target.closest('a, button')) return;
  var r = stage.getBoundingClientRect();
  if (e.clientX < r.left + r.width / 3) prev(); else next();
});

window.addEventListener('resize', fit);
doc.addEventListener('fullscreenchange', fit);
window.addEventListener('hashchange', function () {
  var i = fromHash();
  if (i !== null && i !== idx && i >= 0 && i < N) goTo(i);
});

var start = fromHash();
if (start !== null && start >= 0 && start < N) idx = start;
fit();
render(true);
