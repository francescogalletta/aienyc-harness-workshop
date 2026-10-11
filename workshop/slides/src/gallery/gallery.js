/* Gallery only: write each token's live value next to its swatch or specimen; again on a theme change. */
(function () {
  function probe(prop, value) {
    var p = document.createElement('span');
    p.style.position = 'absolute'; p.style.visibility = 'hidden'; p.style[prop] = value;
    stage.appendChild(p); var v = getComputedStyle(p)[prop]; p.remove(); return v;
  }
  function hex(rgb) {
    var m = rgb.match(/[\d.]+/g); if (!m) return rgb;
    var h = '#' + m.slice(0, 3).map(function (n) { return ('0' + Math.round(+n).toString(16)).slice(-2); }).join('');
    return m.length > 3 && +m[3] < 1 ? h + ' @' + m[3] : h;
  }
  function fill() {
    document.querySelectorAll('[data-token]').forEach(function (e) { e.textContent = hex(probe('backgroundColor', 'var(' + e.getAttribute('data-token') + ')')); });
    document.querySelectorAll('[data-size]').forEach(function (e) { e.textContent = '· ' + Math.round(parseFloat(probe('fontSize', 'var(' + e.getAttribute('data-size') + ')'))) + 'px'; });
  }
  new MutationObserver(fill).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (window.matchMedia) { var mq = matchMedia('(prefers-color-scheme: dark)'); if (mq.addEventListener) mq.addEventListener('change', fill); }
  fill();
})();
