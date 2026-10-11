/* viz.js: the visuals kit. Draws <figure class="viz" data-viz="…" data-spec="{json}"> as inline SVG.
   No dependencies. Optional shelf libraries, inlined by the build only when a slide asks:
   window.rough (style = "rough"), window.echarts (viz = "echarts"), window.anime (choreo).

   - Colours are written as CSS classes reading --viz-* tokens, so light/dark/theme switches repaint
     with no JS. Rough.js and ECharts need concrete colours: they redraw on a theme change.
   - Build steps: drawn parts carry data-step, so the deck's own engine shows them (.shown) and
     counts them. Motion is CSS keyed on .shown; JS (Web Animations / rAF) only for the travel
     marker and count-up. Entering a slide (.instant) or prefers-reduced-motion shows end states. */
var viz = (function () {
  var NS = 'http://www.w3.org/2000/svg', doc = document, root = doc.documentElement;
  var STEP_ATTRS = ['data-step', 'data-step-out', 'data-step-fill', 'data-step-strike', 'data-step-mute'];
  var CLASSES = ['shown', 'gone', 'filled', 'struck', 'muted'];
  var KINDS = {};
  /* fills and the ink (stroke/text strength) used for the same role when drawn as lines */
  var INK = { '--viz-bar': '--viz-bar-ink', '--viz-highlight': '--viz-highlight-ink', '--viz-up': '--viz-up-ink',
    '--viz-down': '--viz-down-ink', '--viz-total': '--viz-total-ink' };

  /* ---------- helpers ---------- */
  function reduce() { return !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches); }
  function tok(name, scope) { return getComputedStyle(scope || root).getPropertyValue(name).trim(); }
  function num(name, fallback, scope) { var v = parseFloat(tok(name, scope)); return isNaN(v) ? fallback : v; }
  function ms(name, fallback) { var v = tok(name); var n = parseFloat(v); if (isNaN(n)) return fallback; return /ms$/.test(v) ? n : n * 1000; }
  function el(tag, attrs, parent) {
    var e = doc.createElementNS(NS, tag);
    for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, s, cls, anchor) {
    var t = el('text', { x: r1(x), y: r1(y), 'class': cls, 'text-anchor': anchor || 'middle' }, parent);
    t.textContent = s; return t;
  }
  function r1(v) { return Math.round(v * 10) / 10; }
  function fit(t, width) {  /* a label wider than its slot breaks onto two lines at the middle space */
    var s = t.textContent;
    if (!t.getComputedTextLength || t.getComputedTextLength() <= width || s.indexOf(' ') < 0) return t;
    var words = s.split(' '), best = 1, half = s.length / 2, pos = 0;
    words.forEach(function (w, i) { pos += w.length + 1; if (i < words.length - 1 && Math.abs(pos - half) < Math.abs(words.slice(0, best).join(' ').length - half)) best = i + 1; });
    var x = t.getAttribute('x'), lines = [words.slice(0, best).join(' '), words.slice(best).join(' ')];
    t.textContent = '';
    lines.forEach(function (l, i) { var ts = el('tspan', { x: x, dy: i ? '1.1em' : 0 }, t); ts.textContent = l; });
    return t;
  }
  function stepOn(node, n) { if (n) node.setAttribute('data-step', n); return node; }
  function fmt(v, spec) {
    spec = spec || {};
    var d = spec.decimals || 0, neg = v < 0, a = Math.abs(v);
    var s = a.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
    return (neg ? '−' : (spec.sign && v > 0 ? '+' : '')) + (spec.prefix || '') + s + (spec.suffix || '');
  }
  function compact(v) { return Math.abs(v) >= 1000 ? (v / 1000).toLocaleString('en-US', { maximumFractionDigits: 1 }) + 'k' : String(v); }
  function niceMax(v) { var p = Math.pow(10, Math.floor(Math.log10(v || 1))), m = v / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p; }
  /* resolve a CSS value (e.g. a size token holding calc()) by measuring a probe inside the figure */
  function cssPx(fig, prop, value) {
    var p = doc.createElement('span'); p.style.position = 'absolute'; p.style.visibility = 'hidden'; p.style[prop] = value;
    fig.appendChild(p); var v = parseFloat(getComputedStyle(p)[prop]); p.remove(); return v;
  }
  function svgFor(fig, w, h) {
    return el('svg', { 'class': 'viz-svg', viewBox: '0 0 ' + w + ' ' + h, width: w, height: h, 'aria-hidden': 'true', focusable: 'false' }, fig);
  }
  function isRough(spec) { return spec.style === 'rough' && !!window.rough; }
  function roughOpts(fig, extra) {
    var o = { roughness: 1.3, bowing: 1, strokeWidth: num('--viz-stroke', 3, fig) + 0.5, seed: 7 };
    for (var k in extra) o[k] = extra[k];
    return o;
  }
  function inkable(node) {  /* draw-on: every path under node strokes in (rough paths included) */
    node.querySelectorAll('path').forEach(function (p) { p.setAttribute('pathLength', '1'); p.classList.add('viz-ink'); });
    return node;
  }

  /* ---------- build-step bookkeeping ---------- */
  function slideOf(node) { return node.closest ? node.closest('.slide') : null; }
  function currentStep(slide) {
    var m = 0;
    STEP_ATTRS.forEach(function (a, i) {
      slide.querySelectorAll('[' + a + '].' + CLASSES[i]).forEach(function (e) { m = Math.max(m, +e.getAttribute(a) || 0); });
    });
    return m;
  }
  function restore(scope, s) {  /* after a redraw, give new parts the classes the deck gave the old ones */
    var slide = slideOf(scope); if (!slide || !slide.classList.contains('active')) return;
    if (s == null) s = currentStep(slide);
    STEP_ATTRS.forEach(function (a, i) {
      scope.querySelectorAll('[' + a + ']').forEach(function (e) { e.classList.toggle(CLASSES[i], (+e.getAttribute(a) || 0) <= s); });
    });
  }
  function instant(node) { var s = slideOf(node); return !!(s && s.classList.contains('instant')); }
  var observer = new MutationObserver(function (records) {
    records.forEach(function (r) {
      var t = r.target, on = t.classList.contains('shown');
      if (!t._play || on === t._on) return;
      t._on = on;
      t._play(on, !instant(t) && !reduce() && t._animate !== false);
    });
  });
  function anchor(fig, n, play) {  /* a hidden element whose .shown drives a JS-played effect */
    var a = doc.createElement('i'); a.className = 'viz-anchor'; a.setAttribute('aria-hidden', 'true');
    stepOn(a, n); fig.appendChild(a);
    a._play = play; a._on = false; a._animate = fig._spec.animate !== false;
    observer.observe(a, { attributes: true, attributeFilter: ['class'] });
    play(!n, false);
    return a;
  }

  /* ---------- chart frame: value axis + gridlines ---------- */
  function valueScale(spec, values) {
    var lo = Math.min(0, Math.min.apply(null, values)), hi = spec.max || niceMax(Math.max.apply(null, values));
    var tick = spec.ticks || hi / 4;
    return { lo: lo, hi: hi, tick: tick };
  }
  function gridY(svg, fig, spec, sc, box, rough) {
    var g = el('g', { 'class': 'viz-frame' }, svg), rc = rough ? window.rough.svg(svg) : null;
    for (var t = sc.lo; t <= sc.hi + 1e-9; t += sc.tick) {
      var y = box.y + box.h - (t - sc.lo) / (sc.hi - sc.lo) * box.h;
      if (spec.axis !== false) {
        if (rc) g.appendChild(rc.line(box.x, y, box.x + box.w, y, roughOpts(fig, { stroke: tok(t ? '--viz-grid' : '--viz-axis'), strokeWidth: t ? 1.5 : 3, roughness: 0.8, seed: 80 + t })));
        else el('line', { 'class': t ? 'viz-grid' : 'viz-axis', x1: box.x, x2: box.x + box.w, y1: r1(y), y2: r1(y) }, g);
        text(g, box.x - 18, y + 10, t ? (spec.prefix || '') + compact(t) : '0', 'viz-tick', 'end');
      } else if (!t) el('line', { 'class': 'viz-axis', x1: box.x, x2: box.x + box.w, y1: r1(y), y2: r1(y) }, g);
    }
    return function (v) { return box.y + box.h - (v - sc.lo) / (sc.hi - sc.lo) * box.h; };
  }
  function barShape(parent, x, y, w, h, rad, up, rc, fig, colorTok, seed) {
    if (h < 0.5) h = 0.5;
    if (rc) {
      var c = tok(INK[colorTok]);
      parent.appendChild(rc.rectangle(x, y, w, h, roughOpts(fig, { stroke: c, fill: c, fillStyle: 'hachure', hachureAngle: -45, hachureGap: 12, fillWeight: 2.5, seed: seed })));
      return;
    }
    var r = Math.max(0, Math.min(rad, w / 2, h));
    var d = up
      ? 'M' + x + ' ' + (y + h) + 'V' + (y + r) + 'Q' + x + ' ' + y + ' ' + (x + r) + ' ' + y + 'H' + (x + w - r) + 'Q' + (x + w) + ' ' + y + ' ' + (x + w) + ' ' + (y + r) + 'V' + (y + h) + 'Z'
      : 'M' + x + ' ' + y + 'V' + (y + h - r) + 'Q' + x + ' ' + (y + h) + ' ' + (x + r) + ' ' + (y + h) + 'H' + (x + w - r) + 'Q' + (x + w) + ' ' + (y + h) + ' ' + (x + w) + ' ' + (y + h - r) + 'V' + y + 'Z';
    el('path', { d: d.replace(/(\d+\.\d{2,})/g, function (m) { return (+m).toFixed(1); }) }, parent);
  }
  function hbarShape(parent, x, y, w, h, rad, rc, fig, colorTok, seed) {
    if (w < 0.5) w = 0.5;
    if (rc) { var c = tok(INK[colorTok]); parent.appendChild(rc.rectangle(x, y, w, h, roughOpts(fig, { stroke: c, fill: c, fillStyle: 'hachure', hachureAngle: -45, hachureGap: 12, fillWeight: 2.5, seed: seed }))); return; }
    var r = Math.max(0, Math.min(rad, h / 2, w));
    el('path', { d: 'M' + x + ' ' + y + 'H' + r1(x + w - r) + 'Q' + r1(x + w) + ' ' + y + ' ' + r1(x + w) + ' ' + r1(y + r) + 'V' + r1(y + h - r) + 'Q' + r1(x + w) + ' ' + r1(y + h) + ' ' + r1(x + w - r) + ' ' + r1(y + h) + 'H' + x + 'Z' }, parent);
  }
  function wantsValue(spec, label, i, n) {
    var v = spec.values;
    if (v === 'all') return true;
    if (v === 'none') return false;
    if (Array.isArray(v)) return v.indexOf(label) >= 0;
    return label === spec.highlight || i === n - 1;
  }

  /* ---------- bars ---------- */
  KINDS.bars = function (fig, spec) {
    var rows = spec.data, n = rows.length, horiz = spec.orient === 'horizontal';
    var W = spec.width || 1640, H = spec.height || (horiz ? Math.min(620, 90 * n + 40) : 560);
    var svg = svgFor(fig, W, H), rough = isRough(spec), rc = rough ? window.rough.svg(svg) : null;
    var rad = num('--viz-bar-radius', 6, fig), fill = num('--viz-bar-fill', 0.56, fig);
    var sc = valueScale(spec, rows.map(function (r) { return r[1]; }));
    var data = stepOn(el('g', { 'class': 'viz-data viz-grow' }, svg), spec.step);
    var hl = el('g', { 'class': 'viz-hl-layer' }, svg);
    if (!horiz) {
      var box = { x: spec.axis === false ? 20 : 120, y: 56, w: 0, h: H - 56 - 76 }; box.w = W - box.x - 20;
      var yOf = gridY(svg, fig, spec, sc, box, rough), band = box.w / n, bw = Math.min(band * fill, 160), base = yOf(0);
      rows.forEach(function (r, i) {
        var cx = box.x + band * i + band / 2, x = cx - bw / 2, y = yOf(r[1]);
        var g = el('g', { 'class': 'viz-bar', style: '--i:' + i }, data);
        barShape(g, x, y, bw, base - y, rad, true, rc, fig, '--viz-bar', 40 + i);
        if (r[0] === spec.highlight) {
          var h = stepOn(el('g', { 'class': 'viz-bar viz-hl', style: '--i:' + i }, hl), spec.highlight_step || spec.step);
          barShape(h, x, y, bw, base - y, rad, true, rc, fig, '--viz-highlight', 40 + i);
        }
        fit(text(svg, cx, base + 48, r[0], 'viz-label' + (r[0] === spec.highlight ? ' viz-strong' : '')), band * 0.96);
        if (wantsValue(spec, r[0], i, n)) stepOn(text(data, cx, y - 16, fmt(r[1], spec), 'viz-value'), spec.step);
      });
    } else {
      var lw = spec.label_width || 360, bx = { x: lw, y: 10, w: W - lw - 220, h: H - 20 }, rowH = bx.h / n, bh = Math.min(rowH * fill, 64);
      var xOf = function (v) { return bx.x + (v - sc.lo) / (sc.hi - sc.lo) * bx.w; };
      el('line', { 'class': 'viz-axis', x1: bx.x, x2: bx.x, y1: bx.y, y2: bx.y + bx.h }, svg);
      rows.forEach(function (r, i) {
        var cy = bx.y + rowH * i + rowH / 2, y = cy - bh / 2, w = xOf(r[1]) - bx.x;
        var g = el('g', { 'class': 'viz-bar viz-hbar', style: '--i:' + i }, data);
        hbarShape(g, bx.x, y, w, bh, rad, rc, fig, '--viz-bar', 40 + i);
        if (r[0] === spec.highlight) { var h = stepOn(el('g', { 'class': 'viz-bar viz-hbar viz-hl', style: '--i:' + i }, hl), spec.highlight_step || spec.step); hbarShape(h, bx.x, y, w, bh, rad, rc, fig, '--viz-highlight', 40 + i); }
        text(svg, bx.x - 24, cy + 11, r[0], 'viz-label' + (r[0] === spec.highlight ? ' viz-strong' : ''), 'end');
        if (wantsValue(spec, r[0], i, n)) stepOn(text(data, bx.x + w + 18, cy + 11, fmt(r[1], spec), 'viz-value', 'start'), spec.step);
      });
    }
    if (rough) inkable(data);
  };

  /* ---------- waterfall: start, signed changes, end ---------- */
  KINDS.waterfall = function (fig, spec) {
    var items = [{ label: spec.start[0], v: spec.start[1], kind: 'total', from: 0, to: spec.start[1] }], run = spec.start[1];
    spec.changes.forEach(function (c) { items.push({ label: c[0], v: c[1], kind: c[1] >= 0 ? 'up' : 'down', from: run, to: run + c[1] }); run += c[1]; });
    items.push({ label: spec.end || 'End', v: run, kind: 'total', from: 0, to: run });
    var W = spec.width || 1640, H = spec.height || 600, svg = svgFor(fig, W, H), rough = isRough(spec), rc = rough ? window.rough.svg(svg) : null;
    var all = []; items.forEach(function (it) { all.push(it.from, it.to); });
    var sc = valueScale(spec, all), box = { x: 120, y: 60, w: W - 140, h: H - 60 - 80 };
    var yOf = gridY(svg, fig, spec, sc, box, rough), n = items.length, band = box.w / n, bw = Math.min(band * num('--viz-bar-fill', 0.56, fig), 150);
    var rad = num('--viz-bar-radius', 6, fig), each = spec.reveal === 'each', s0 = spec.step || 0;
    var data = stepOn(el('g', { 'class': 'viz-data viz-grow' }, svg), each ? null : spec.step);
    items.forEach(function (it, i) {
      var cx = box.x + band * i + band / 2, x = cx - bw / 2, top = yOf(Math.max(it.from, it.to)), bot = yOf(Math.min(it.from, it.to));
      var g = stepOn(el('g', { 'class': 'viz-bar viz-' + it.kind, style: '--i:' + (each ? 0 : i) }, data), each ? (s0 + i || null) : null);
      barShape(g, x, top, bw, bot - top, rad, it.kind !== 'down', rc, fig, it.kind === 'total' ? '--viz-total' : it.kind === 'up' ? '--viz-up' : '--viz-down', 50 + i);
      var lab = it.kind === 'total' ? fmt(it.v, spec) : fmt(it.v, { prefix: spec.prefix, suffix: spec.suffix, sign: true, decimals: spec.decimals });
      var ly = it.kind === 'down' ? bot + 40 : top - 16;
      text(g, cx, ly, (it.kind === 'up' ? '▲ ' : it.kind === 'down' ? '▼ ' : '') + lab, 'viz-value');
      if (i < n - 1) {
        var lvl = yOf(it.to), nx = box.x + band * (i + 1) + band / 2 - bw / 2;
        el('line', { 'class': 'viz-connector', x1: r1(x + bw), x2: r1(nx), y1: r1(lvl), y2: r1(lvl) }, g);
      }
      fit(text(svg, cx, box.y + box.h + 50, it.label, 'viz-label' + (it.kind === 'total' ? ' viz-strong' : '')), band * 0.96);
    });
    if (rough) inkable(data);
  };

  /* ---------- line: one or two series ---------- */
  KINDS.line = function (fig, spec) {
    var xs = spec.x, series = spec.series, n = xs.length;
    var W = spec.width || 1640, H = spec.height || 560, svg = svgFor(fig, W, H), rough = isRough(spec), rc = rough ? window.rough.svg(svg) : null;
    var vals = []; series.forEach(function (s) { vals = vals.concat(s.values); });
    var legend = series.length > 1, endRoom = 260;
    var sc = valueScale(spec, vals), box = { x: 120, y: legend ? 90 : 40, w: W - 120 - endRoom, h: 0 }; box.h = H - box.y - 76;
    var yOf = gridY(svg, fig, spec, sc, box, rough), xOf = function (i) { return box.x + (n === 1 ? box.w / 2 : i * box.w / (n - 1)); };
    var every = Math.ceil(n / 12);
    xs.forEach(function (x, i) { if (i % every === 0 || i === n - 1) text(svg, xOf(i), box.y + box.h + 48, x, 'viz-label'); });
    var pr = num('--viz-point-r', 8, fig);
    series.forEach(function (s, k) {
      var cls = 'viz-s' + (k + 1), pts = s.values.map(function (v, i) { return [xOf(i), yOf(v)]; });
      var g = stepOn(el('g', { 'class': 'viz-series ' + cls }, svg), s.step || spec.step);
      var d = 'M' + pts.map(function (p) { return r1(p[0]) + ' ' + r1(p[1]); }).join('L');
      if (spec.area && !rough && k === 0) el('path', { 'class': 'viz-area', d: d + 'L' + r1(pts[n - 1][0]) + ' ' + r1(yOf(Math.max(sc.lo, 0))) + 'L' + r1(pts[0][0]) + ' ' + r1(yOf(Math.max(sc.lo, 0))) + 'Z' }, g);
      if (rc) g.appendChild(rc.linearPath(pts, roughOpts(fig, { stroke: tok('--viz-series-' + (k + 1) + '-ink'), strokeWidth: num('--viz-line-width', 3, fig) + 0.5, roughness: 1, seed: 20 + k })));
      else el('path', { 'class': 'viz-line', d: d }, g);
      inkable(g);
      if (spec.points !== false) pts.forEach(function (p, i) { el('circle', { 'class': 'viz-point', cx: r1(p[0]), cy: r1(p[1]), r: pr, style: '--i:' + i }, g); });
      var last = pts[n - 1], clash = series.some(function (o, j) { return j !== k && Math.abs(yOf(o.values[n - 1]) - last[1]) < 44; });
      if (!clash) text(g, last[0] + 24, last[1] + 10, (legend ? '' : s.name + ' ') + compactLabel(s.values[n - 1], spec), 'viz-value', 'start');
      if (legend) {
        var lx = box.x + k * 420;
        el('rect', { 'class': 'viz-key ' + cls, x: lx, y: 22, width: 44, height: 8, rx: 4 }, svg);
        text(svg, lx + 60, 36, s.name, 'viz-label', 'start');
      }
    });
    if (spec.note) {
      var nt = spec.note, si = (nt.series || 1) - 1, i = xs.indexOf(nt.at), v = series[si].values[i], p = [xOf(i), yOf(v)];
      var g2 = stepOn(el('g', { 'class': 'viz-note' }, svg), nt.step || spec.step);
      el('circle', { 'class': 'viz-note-ring', cx: r1(p[0]), cy: r1(p[1]), r: pr * 2.4 }, g2);
      var above = p[1] - box.y > 140, ty = above ? p[1] - 96 : p[1] + 110;
      el('line', { 'class': 'viz-leader', x1: r1(p[0]), y1: r1(p[1] + (above ? -pr * 2.4 : pr * 2.4)), x2: r1(p[0]), y2: r1(ty + (above ? 14 : -40)) }, g2);
      text(g2, p[0], ty, nt.text, 'viz-note-text', p[0] > box.x + box.w * 0.7 ? 'end' : p[0] < box.x + box.w * 0.3 ? 'start' : 'middle');
    }
  };
  function compactLabel(v, spec) { return (spec.prefix || '') + compact(v) + (spec.suffix || ''); }

  /* ---------- timeline: dated events on an axis ---------- */
  function day(s) { var p = String(s).split('-'); return Date.UTC(+p[0], (+p[1] || 1) - 1, +p[2] || 1); }
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  KINDS.timeline = function (fig, spec) {
    var ev = spec.events, W = spec.width || 1640, H = spec.height || 520, svg = svgFor(fig, W, H), rough = isRough(spec), rc = rough ? window.rough.svg(svg) : null;
    var t0 = day(spec.start || ev[0].date), t1 = day(spec.end || ev[ev.length - 1].date), x0 = 40, x1 = W - 40, mid = H / 2;
    var xOf = function (t) { return x0 + (t - t0) / (t1 - t0) * (x1 - x0); };
    var frame = el('g', { 'class': 'viz-frame' }, svg);
    if (rc) frame.appendChild(rc.line(x0, mid, x1, mid, roughOpts(fig, { stroke: tok('--viz-axis'), roughness: 0.8 })));
    else el('line', { 'class': 'viz-axis', x1: x0, x2: x1, y1: mid, y2: mid }, frame);
    function months(cb) {
      var d = new Date(t0); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + (d.getUTCDate() > 1 ? 1 : 0), 1));
      while (d.getTime() <= t1) { cb(d, xOf(d.getTime())); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)); }
    }
    months(function (d, x) { el('line', { 'class': 'viz-grid', x1: r1(x), x2: r1(x), y1: mid - 12, y2: mid + 12 }, frame); });
    if (spec.months !== false) months(function (d, x) { if (d.getUTCMonth() % (spec.every || 2) === 0) text(frame, x, H - 8, MONTHS[d.getUTCMonth()], 'viz-tick'); });
    var each = spec.reveal === 'each', s0 = spec.step || 0, pr = num('--viz-point-r', 8, fig);
    ev.forEach(function (e, i) {
      var x = xOf(day(e.date)), up = i % 2 === 0, g = stepOn(el('g', { 'class': 'viz-event', style: '--i:' + i }, svg), each ? (s0 + i || null) : (e.step || spec.step));
      var y2 = up ? mid - 70 : mid + 70;
      el('line', { 'class': 'viz-leader', x1: r1(x), x2: r1(x), y1: mid, y2: y2 }, g);
      if (rc) g.appendChild(rc.circle(x, mid, pr * 3, roughOpts(fig, { stroke: tok('--viz-series-1-ink'), fill: tok('--viz-series-1-ink'), fillStyle: 'solid', seed: 90 + i })));
      else el('circle', { 'class': 'viz-point viz-s1', cx: r1(x), cy: mid, r: pr * 1.5 }, g);
      var anchorPos = x < x0 + 160 ? 'start' : x > x1 - 160 ? 'end' : 'middle';
      var dt = new Date(day(e.date)), when = MONTHS[dt.getUTCMonth()] + ' ' + dt.getUTCDate();
      var lines = [when, e.text]; if (e.value) lines.push(e.value);
      lines.forEach(function (s, k) {
        var y = up ? y2 - 18 - (lines.length - 1 - k) * 40 : y2 + 40 + k * 40;
        text(g, x, y, s, k === 0 ? 'viz-label' : k === 2 ? 'viz-value' : 'viz-label viz-strong', anchorPos);
      });
    });
  };

  /* ---------- flow: nodes and arrows ---------- */
  KINDS.flow = function (fig, spec) {
    var nodes = spec.nodes.map(function (n) { return typeof n === 'string' ? { text: n } : n; }), N = nodes.length;
    var dir = spec.direction || 'row', cols = dir === 'row' ? N : dir === 'column' ? 1 : (spec.columns || 3);
    nodes.forEach(function (n, i) { if (!n.at) n.at = [i % cols + 1, Math.floor(i / cols) + 1]; });
    var ncol = Math.max.apply(null, nodes.map(function (n) { return n.at[0]; })), nrow = Math.max.apply(null, nodes.map(function (n) { return n.at[1]; }));
    var W = spec.width || 1640, gapX = spec.gap || 90, nw = spec.node_width || Math.min(360, (W - gapX * (ncol - 1)) / ncol);
    var nh = spec.node_height || (dir === 'column' ? 112 : 150), gapY = dir === 'column' ? 48 : 80;
    var H = spec.height || (nrow * nh + (nrow - 1) * gapY + 40), sx = ncol > 1 ? (W - nw) / (ncol - 1) : 0, sy = nh + gapY;
    var svg = svgFor(fig, W, H), rough = isRough(spec), rc = rough ? window.rough.svg(svg) : null;
    var rad = num('--viz-node-radius', 6, fig), sw = num('--viz-stroke', 3, fig);
    var box = function (n) { var x = (n.at[0] - 1) * sx, y = 20 + (n.at[1] - 1) * sy; return { x: x, y: y, cx: x + nw / 2, cy: y + nh / 2 }; };
    var links = spec.links || nodes.slice(1).map(function (_, i) { return [i + 1, i + 2]; });
    var linkG = el('g', { 'class': 'viz-links' }, svg), segs = [];
    links.forEach(function (lk, k) {
      var a = box(nodes[lk[0] - 1]), b = box(nodes[lk[1] - 1]), p, q;
      if (Math.abs(a.cy - b.cy) < 1) { var s = b.cx > a.cx ? 1 : -1; p = [a.cx + s * (nw / 2 + 14), a.cy]; q = [b.cx - s * (nw / 2 + 18), b.cy]; }
      else if (Math.abs(a.cx - b.cx) < 1) { var t = b.cy > a.cy ? 1 : -1; p = [a.cx, a.cy + t * (nh / 2 + 12)]; q = [b.cx, b.cy - t * (nh / 2 + 16)]; }
      else { var dx = b.cx - a.cx, dy = b.cy - a.cy, f = Math.min(Math.abs((nw / 2 + 14) / dx), Math.abs((nh / 2 + 12) / dy)); p = [a.cx + dx * f, a.cy + dy * f]; q = [b.cx - dx * f * 1.08, b.cy - dy * f * 1.08]; }
      var lstep = Math.max(nodes[lk[0] - 1].step || 0, nodes[lk[1] - 1].step || 0) || spec.step;
      var g = stepOn(el('g', { 'class': 'viz-link' }, linkG), lstep);
      var ang = Math.atan2(q[1] - p[1], q[0] - p[0]), L = 18, hw = 12;
      var h1 = [q[0] - L * Math.cos(ang) + hw * Math.sin(ang), q[1] - L * Math.sin(ang) - hw * Math.cos(ang)], h2 = [q[0] - L * Math.cos(ang) - hw * Math.sin(ang), q[1] - L * Math.sin(ang) + hw * Math.cos(ang)];
      if (rc) { var o = roughOpts(fig, { stroke: tok('--viz-link'), roughness: 1.1, seed: 60 + k }); g.appendChild(rc.line(p[0], p[1], q[0], q[1], o)); g.appendChild(rc.linearPath([h1, q, h2], o)); }
      else { el('path', { 'class': 'viz-arrow-line', d: 'M' + r1(p[0]) + ' ' + r1(p[1]) + 'L' + r1(q[0] - 10 * Math.cos(ang)) + ' ' + r1(q[1] - 10 * Math.sin(ang)) }, g); el('path', { 'class': 'viz-arrow-head', d: 'M' + r1(h1[0]) + ' ' + r1(h1[1]) + 'L' + r1(q[0]) + ' ' + r1(q[1]) + 'L' + r1(h2[0]) + ' ' + r1(h2[1]) + 'Z' }, g); }
      var dash = tok('--viz-link-dash');
      if (dash && dash !== 'none') g.querySelectorAll('path').forEach(function (pth) { if (!pth.classList.contains('viz-arrow-head')) pth.style.strokeDasharray = dash; });
      else inkable(g);
      segs.push({ p: p, q: q, from: lk[0] - 1, to: lk[1] - 1 });
    });
    var nodeG = el('g', { 'class': 'viz-nodes' }, svg), rings = [];
    nodes.forEach(function (n, i) {
      var b = box(n), fillTok = n.principle ? '--principle-' + n.principle : n.role === 'accent' ? '--viz-highlight' : null;
      var cls = 'viz-node' + (fillTok ? ' viz-filled' : n.role === 'muted' ? ' viz-muted' : '');
      var g = stepOn(el('g', { 'class': cls, style: fillTok ? '--c:var(' + fillTok + ')' : null }, nodeG), n.step || (spec.reveal === 'each' ? (spec.step || 0) + i || null : spec.step));
      if (rc) g.appendChild(rc.rectangle(b.x, b.y, nw, nh, roughOpts(fig, { stroke: tok('--viz-node-stroke'), strokeWidth: sw + 1, fill: fillTok ? tok(fillTok) : tok('--viz-node-fill'), fillStyle: 'solid', seed: i + 3 })));
      else el('rect', { x: r1(b.x), y: r1(b.y), width: r1(nw), height: nh, rx: rad, ry: rad }, g);
      var lines = String(n.text).split('\n'), hasNum = n.principle && spec.numbers !== false;
      var lineH = 40, numH = hasNum ? 58 : 0, top = b.cy - (numH + lines.length * lineH) / 2;
      if (hasNum) text(g, b.cx, top + 44, String(n.principle), 'viz-node-num');
      lines.forEach(function (s, k) { text(g, b.cx, top + numH + (k + 1) * lineH - 10, s, 'viz-node-text'); });
      var ring = el('rect', { 'class': 'viz-ring', x: r1(b.x - 10), y: r1(b.y - 10), width: r1(nw + 20), height: nh + 20, rx: rad + 8, ry: rad + 8 }, nodeG);
      rings.push(ring);
    });
    if (spec.travel) {
      var mk = el('circle', { 'class': 'viz-marker', r: num('--viz-marker-r', 16, fig), cx: 0, cy: 0 }, svg);
      var pts = [], arrive = [];   /* along the arrows: leave a node, arrive at the next */
      segs.forEach(function (sg) { pts.push(sg.p, sg.q); arrive.push({ at: pts.length - 1, node: sg.to }); });
      if (!pts.length) pts = [[box(nodes[0]).cx, box(nodes[0]).cy]];
      var lens = [0]; for (var i = 1; i < pts.length; i++) lens.push(lens[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
      var total = lens[lens.length - 1] || 1, T = ms('--viz-dur-travel', 2400), first = segs.length ? segs[0].from : 0;
      var frames = pts.map(function (p, i) { return { transform: 'translate(' + r1(p[0]) + 'px,' + r1(p[1]) + 'px)', offset: lens[i] / total }; });
      var timers = [], light = function (k) { rings.forEach(function (r) { r.classList.remove('on'); }); if (rings[k]) rings[k].classList.add('on'); };
      anchor(fig, spec.travel, function (on, animate) {
        mk.getAnimations().forEach(function (a) { a.cancel(); });
        timers.forEach(clearTimeout); timers = [];
        rings.forEach(function (r) { r.classList.remove('on'); });
        if (!on) { mk.style.opacity = 0; mk.style.transform = frames[0].transform; return; }
        mk.style.opacity = 1; mk.style.transform = frames[frames.length - 1].transform;
        var last = arrive.length ? arrive[arrive.length - 1].node : first;
        if (!animate) { light(last); return; }
        light(first);
        mk.animate(frames, { duration: T, easing: 'linear', fill: 'backwards' });
        arrive.forEach(function (a) { timers.push(setTimeout(function () { light(a.node); }, T * lens[a.at] / total)); });
      });
    }
  };

  /* ---------- count-up ---------- */
  KINDS.count = function (fig, spec) {
    var raf = 0, T = spec.duration || ms('--viz-dur-count', 1200);
    fig.textContent = fmt(spec.to, spec);
    fig._play = function (on, animate) {
      cancelAnimationFrame(raf);
      if (!on || !animate) { fig.textContent = fmt(spec.to, spec); return; }
      var t0 = performance.now(), from = spec.from || 0;
      (function f(now) {
        var k = Math.min(1, (now - t0) / T), e = 1 - Math.pow(1 - k, 3);
        fig.textContent = fmt(from + (spec.to - from) * e, spec);
        if (k < 1) raf = requestAnimationFrame(f);
      })(t0);
    };
    if (!fig._watched) { fig._watched = true; fig._on = fig.classList.contains('shown'); fig._animate = spec.animate !== false; observer.observe(fig, { attributes: true, attributeFilter: ['class'] }); }
  };

  /* ---------- draw-on for inline SVG: every [data-step] group strokes in at its step ---------- */
  KINDS.draw = function (fig) {
    fig.querySelectorAll('svg [data-step]').forEach(function (g) {
      g.querySelectorAll('path').forEach(function (p) {
        if (getComputedStyle(p).strokeDasharray !== 'none') return;  /* dashed lines keep their dashes and fade */
        p.setAttribute('pathLength', '1'); p.classList.add('viz-ink');
      });
      g.classList.add('viz-drawn');
    });
  };

  /* ---------- marks: underline / circle / bracket / box around an element on the slide ---------- */
  KINDS.mark = function (layer, spec) {
    var slide = slideOf(layer); if (!slide) return;
    while (layer.firstChild) layer.removeChild(layer.firstChild);
    var sr = slide.getBoundingClientRect(), k = sr.width / 1920 || 1;
    layer.setAttribute('viewBox', '0 0 1920 1080');
    var rc = null;
    spec.marks.forEach(function (m, i) {
      var t = slide.querySelector(m.target); if (!t) return;
      var kind = m.kind || 'circle', r = t.getBoundingClientRect(), pad = m.pad == null ? (kind === 'circle' ? 8 : 14) : m.pad;
      var x = (r.left - sr.left) / k - pad, y = (r.top - sr.top) / k - pad, w = r.width / k + pad * 2, h = r.height / k + pad * 2;
      var g = stepOn(el('g', { 'class': 'viz-mark viz-mark-' + (m.kind || 'circle') }, layer), m.step);
      var rough = m.style === 'rough' && window.rough;
      if (rough && !rc) rc = window.rough.svg(layer);
      var o = rough ? roughOpts(layer, { stroke: tok('--viz-annotate'), strokeWidth: num('--viz-annotate-width', 5), roughness: 1.6, seed: 30 + i }) : null;
      if (kind === 'circle') {
        if (rc && rough) g.appendChild(rc.ellipse(x + w / 2, y + h / 2, w + pad * 1.2, h + pad * 0.4, o));
        else el('ellipse', { cx: r1(x + w / 2), cy: r1(y + h / 2), rx: r1(w / 2 + pad * 2), ry: r1(h / 2 - pad * 0.5) }, g);
      } else if (kind === 'underline') {
        var uy = y + h - pad / 2;
        if (rc && rough) g.appendChild(rc.curve([[x + pad, uy], [x + w / 2, uy + 6], [x + w - pad, uy - 2]], o));
        else el('path', { d: 'M' + r1(x + pad) + ' ' + r1(uy) + 'Q' + r1(x + w / 2) + ' ' + r1(uy + 10) + ' ' + r1(x + w - pad) + ' ' + r1(uy - 2) }, g);
      } else if (kind === 'bracket') {
        var bx = x - 6, arm = Math.min(28, w / 4);
        if (rc && rough) g.appendChild(rc.linearPath([[bx + arm, y], [bx, y], [bx, y + h], [bx + arm, y + h]], o));
        else el('path', { d: 'M' + r1(bx + arm) + ' ' + r1(y) + 'H' + r1(bx) + 'V' + r1(y + h) + 'H' + r1(bx + arm) }, g);
      } else {
        if (rc && rough) g.appendChild(rc.rectangle(x, y, w, h, o));
        else el('rect', { x: r1(x), y: r1(y), width: r1(w), height: r1(h), rx: num('--viz-node-radius', 6), ry: num('--viz-node-radius', 6) }, g);
      }
      inkable(g);
      if (m.note) text(g, x + w / 2, y + h + 46, m.note, 'viz-mark-note');
    });
  };

  /* ---------- ECharts adapter (window.echarts, SVG renderer) ---------- */
  function merge(a, b) {
    if (Array.isArray(b) || typeof b !== 'object' || b === null) return b;
    var out = {}; var k;
    for (k in a) out[k] = a[k];
    for (k in b) out[k] = (k in out && typeof out[k] === 'object' && !Array.isArray(out[k])) ? merge(out[k], b[k]) : b[k];
    return out;
  }
  function echartsDefaults(fig) {
    var size = cssPx(fig, 'fontSize', 'var(--viz-label-size)'), fam = getComputedStyle(fig).fontFamily;
    var text = tok('--viz-text'), muted = tok('--viz-muted'), grid = tok('--viz-grid'), axis = tok('--viz-axis');
    var axisDef = { axisLine: { lineStyle: { color: axis, width: num('--viz-stroke', 3) } }, axisTick: { show: false }, axisLabel: { color: muted, fontSize: size, fontFamily: fam, margin: 18 },
      splitLine: { lineStyle: { color: grid, width: num('--viz-hair', 2) } }, nameTextStyle: { color: muted, fontSize: size, fontFamily: fam } };
    return {
      backgroundColor: 'transparent', animation: !reduce() && fig._spec.animate !== false, animationDuration: ms('--viz-dur-draw', 500) * 1.6,
      color: [1, 2, 3, 4, 5].map(function (i) { return tok('--viz-series-' + i); }),
      textStyle: { fontFamily: fam, fontSize: size, color: text },
      grid: { left: 130, right: 40, top: 70, bottom: 80 },
      legend: { textStyle: { color: text, fontSize: size, fontFamily: fam }, itemWidth: 44, itemHeight: 10, top: 0 },
      tooltip: { show: false },
      xAxis: axisDef, yAxis: merge(axisDef, { axisLine: { show: false } }),
      _axis: axisDef
    };
  }
  KINDS.echarts = function (fig, spec) {
    if (!window.echarts) return;
    var host = fig.querySelector('.viz-echarts-host');
    if (!host) { host = doc.createElement('div'); host.className = 'viz-echarts-host'; fig.appendChild(host); }
    var W = spec.width || 1640, H = spec.height || 560;
    host.style.width = W + 'px'; host.style.height = H + 'px';
    if (fig._chart) { fig._chart.dispose(); }
    var chart = window.echarts.init(host, null, { renderer: 'svg', width: W, height: H });
    fig._chart = chart;
    function option(shown, animate) {
      var d = echartsDefaults(fig), o = spec.option, axisDef = d._axis; delete d._axis;
      var m = merge(d, o);
      ['xAxis', 'yAxis'].forEach(function (ax) { if (Array.isArray(o[ax])) m[ax] = o[ax].map(function (a) { return merge(axisDef, a); }); });
      if (!animate) m.animation = false;
      if (!shown) m.series = (m.series || []).map(function (s) { return merge(s, { data: (s.data || []).map(function () { return null; }) }); });
      return m;
    }
    var state = { shown: !spec.step };
    chart.setOption(option(state.shown, false), true);
    fig._retheme = function () { chart.setOption(option(state.shown, false), true); };
    if (spec.step) anchor(fig, spec.step, function (on, animate) { state.shown = on; chart.setOption(option(on, animate), true); });
  };

  /* ---------- choreography (window.anime): run a timeline on a step, undo it stepping back ---------- */
  KINDS.choreo = function (node, spec) {
    var A = window.anime; if (!A) return;
    var slide = slideOf(node) || doc, parts = spec.parts || [spec], running = null;
    var targets = function (p) { return slide.querySelectorAll(p.targets); };
    function setAll(which) { parts.forEach(function (p) { var t = targets(p); if (t.length && p[which]) A.utils.set(t, p[which]); }); }
    setAll('from');
    node._play = function (on, animate) {
      if (running) { running.pause(); running = null; }
      if (!on) { setAll('from'); return; }
      if (!animate) { setAll('to'); return; }
      var tl = A.createTimeline({ defaults: { ease: spec.ease || 'outExpo' } });
      parts.forEach(function (p) {
        var props = {}, k;
        for (k in p.to) props[k] = [p.from && k in p.from ? p.from[k] : p.to[k], p.to[k]];
        props.duration = p.duration || spec.duration || ms('--viz-dur-draw', 500) * 1.4;
        if (p.stagger || spec.stagger) props.delay = A.stagger(p.stagger || spec.stagger);
        if (p.ease) props.ease = p.ease;
        tl.add(targets(p), props, p.at == null ? undefined : p.at);
      });
      running = tl;
    };
    if (!node._watched) { node._watched = true; node._on = false; node._animate = spec.animate !== false; observer.observe(node, { attributes: true, attributeFilter: ['class'] }); }
  };

  /* ---------- drawing everything ---------- */
  function drawOne(fig) {
    var kind = fig.getAttribute('data-viz'), fn = KINDS[kind]; if (!fn) return;
    var spec = fig._spec || (fig._spec = JSON.parse(fig.getAttribute('data-spec') || '{}'));
    var slide = slideOf(fig), step = slide && slide.classList.contains('active') ? currentStep(slide) : null;  /* before old parts go */
    if (spec.animate === false) fig.classList.add('viz-still');
    if (kind !== 'count' && kind !== 'draw' && kind !== 'echarts' && kind !== 'choreo' && kind !== 'mark') {
      fig.querySelectorAll('.viz-svg, .viz-anchor').forEach(function (n) { n.remove(); });
    }
    fn(fig, spec);
    restore(fig, step);
  }
  function draw(scope) { (scope || doc).querySelectorAll('[data-viz]').forEach(drawOne); }
  function retheme() {  /* concrete colours/geometry were read at draw time: redraw those */
    doc.querySelectorAll('[data-viz]').forEach(function (f) {
      var s = f._spec || {};
      if (f._retheme) { f._retheme(); return; }
      if (s.style === 'rough' || f.getAttribute('data-viz') === 'mark') drawOne(f);
    });
  }
  function remark() { doc.querySelectorAll('[data-viz="mark"]').forEach(drawOne); }
  new MutationObserver(retheme).observe(root, { attributes: true, attributeFilter: ['data-theme', 'data-look', 'class', 'style'] });
  if (window.matchMedia) { var mq = matchMedia('(prefers-color-scheme: dark)'); if (mq.addEventListener) mq.addEventListener('change', retheme); }
  if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(remark);
  window.addEventListener('resize', remark);
  draw(doc);
  return { draw: draw, redraw: function () { draw(doc); }, retheme: retheme };
})();
window.viz = viz;
