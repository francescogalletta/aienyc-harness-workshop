/* Financial Advisor Harness: the page. Draws only from the plan state document
   (GET /api/state) and acts only through POST /api/act. Data is inserted as text. */
(function () {
  'use strict';
  var F = window.FAH;
  var TOKEN = '__HARNESS_TOKEN__';

  /* Geometry of the diagram (px). The step is 184 wide (design system); the page owns the rest. */
  var STEP_W = 184, STEP_H = 84, PILLS = 26, ROW = 156, CORRIDOR = 136;
  var MIN_GAP = 32, MAX_GAP = 72, LANE = 8, LANE_END = 14, PORT_GAP = 14, PORT_PAD = 14;

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var $ = function (id) { return document.getElementById(id); };
  var canvas = $('canvas'), scroller = $('scroll'), input = $('say'), sideBtn = $('sidebtn'), composer = $('composer');

  var S = null, drawnVersion = -1, first = true, timer = null, failing = false;
  var ui = { selected: null, selInput: null, attached: null, notice: null, side: false, pop: null, popRun: null, code: false,
             review: false, whole: false, openThread: null, knownThreads: null, wantNewThread: false,
             markNode: null, draft: null, replies: {}, branchOpen: {}, showEarlier: false, focusKey: null };
  var stepEls = {}, lineShown = {}, needShown = {}, lay = null, layKey = '', edgeSegs = {}, pillEls = [];
  var answerKey = null, animating = {}, animRun = 0, popEl = null;

  /* ---------- small helpers ---------- */
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = String(text); }
    return e;
  }
  function add(parent) { for (var i = 1; i < arguments.length; i++) { var c = arguments[i]; if (c == null) { continue; } parent.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); } return parent; }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function has(o, k) { return o != null && Object.prototype.hasOwnProperty.call(o, k); }
  function steps() { return S && Array.isArray(S.steps) ? S.steps : []; }
  function stepById(id) { var a = steps(); for (var i = 0; i < a.length; i++) { if (a[i].id === id) { return a[i]; } } return null; }
  function label(s) { return s ? ((s.number != null ? s.number + ' ' : '') + (s.name || s.id)) : ''; }
  function inputName(id) { var i = S && S.inputs && S.inputs[id]; return i && i.name ? i.name : String(id).replace(/^in:/, '').replace(/_/g, ' '); }
  function show(node, on) { node.hidden = !on; }
  function safeUrl(u) { return typeof u === 'string' && /^https?:\/\//i.test(u) ? u : null; }
  function link(title, url) {
    var u = safeUrl(url);
    if (!u) { return el('span', null, title || url || ''); }
    var a = el('a', null, title || u); a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer';
    return a;
  }
  function fmt(v) {
    if (v == null) { return ''; }
    if (typeof v === 'number') { return v.toLocaleString('en-US', { maximumFractionDigits: 10 }); }
    if (typeof v === 'string') { return v; }
    try { return JSON.stringify(v); } catch (e) { return String(v); }
  }
  /* A value as the harness wrote it for the eye (SPEC 2.4): `text`, and `rows` or `columns` and `table`. */
  function shownText(d, raw) { return d && typeof d === 'object' && d.text != null ? String(d.text) : fmt(raw); }
  function structured(d) { return !!(d && (Array.isArray(d.rows) || (Array.isArray(d.table) && Array.isArray(d.columns)))); }
  function shownNode(d) {
    if (d && Array.isArray(d.table) && Array.isArray(d.columns)) {
      var wrap = el('div', 'fa-tablewrap'), tb = el('table', 'fa-table'), hr = el('tr');
      d.columns.forEach(function (c) { hr.appendChild(el('th', null, c)); });
      add(tb, add(el('thead'), hr));
      var body = el('tbody');
      d.table.forEach(function (row) { var tr = el('tr'); arr(row).forEach(function (c) { tr.appendChild(el('td', null, c)); }); body.appendChild(tr); });
      tb.appendChild(body); wrap.appendChild(tb);
      return wrap;
    }
    var box = el('div', 'fa-rows');
    arr(d && d.rows).forEach(function (r) { box.appendChild(popRow(String(r[0]), String(r[1]))); });
    return box;
  }
  function exactValues(obj) {
    var dt = el('details', 'fa-exact'); dt.appendChild(el('summary', null, 'Exact values'));
    var txt; try { txt = JSON.stringify(obj, null, 1); } catch (e) { txt = String(obj); }
    dt.appendChild(el('pre', 'fa-code', txt));
    dt.addEventListener('click', function (ev) { ev.stopPropagation(); });
    return dt;
  }
  function when(ts) {
    if (!ts) { return ''; }
    var d = new Date(ts); if (isNaN(d)) { return String(ts); }
    return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
  function threads() { return S && Array.isArray(S.threads) ? S.threads : null; }
  function threadOfChallenge(cid) { var t = arr(threads()); for (var i = 0; i < t.length; i++) { if (t[i].challenge && t[i].challenge.id === cid) { return t[i]; } } return null; }
  function openChallenges(s) {
    var out = [];
    arr(s.challenges).forEach(function (cid) { var t = threadOfChallenge(cid); if (t && t.challenge.status === 'open') { out.push(t); } });
    out.sort(function (a, b) { return (a.challenge.rank || 99) - (b.challenge.rank || 99); });
    return out;
  }

  /* ---------- origins: quiet marks ---------- */
  var ORIGIN = { person: ['❝', 'Your words'], looked_up: ['↗', 'Looked up'], proposed: ['✎', 'Proposed by the assistant'] };
  function originTitle(o) {
    if (!o || !ORIGIN[o.kind]) { return ''; }
    if (o.kind === 'person' && o.quote) { return 'Your words: “' + o.quote + '”'; }
    if (o.kind === 'looked_up' && o.source) { return 'Looked up: ' + (typeof o.source === 'string' ? o.source : (o.source.title || o.source.url || '')); }
    return ORIGIN[o.kind][1];
  }
  function originMark(o) {
    if (!o || !ORIGIN[o.kind]) { return null; }
    var s = el('span', 'fa-orig', ORIGIN[o.kind][0]);
    s.title = originTitle(o); s.setAttribute('aria-label', s.title); s.setAttribute('role', 'img');
    return s;
  }
  function originLine(o) {
    if (!o || !ORIGIN[o.kind]) { return null; }
    var s = el('span', 'fa-sub');
    if (o.kind === 'person') { add(s, '❝ Your words: “' + (o.quote || '') + '”'); }
    else if (o.kind === 'looked_up') {
      var src = o.source || {};
      if (typeof src === 'string') { src = { url: src, title: src }; }
      add(s, '↗ Looked up: ', link(src.title || src.url, src.url));
    } else { add(s, '✎ Proposed by the assistant'); }
    return s;
  }

  /* ---------- talking to the harness ---------- */
  function request(path, body) {
    var opt = { headers: { 'X-Harness-Token': TOKEN }, cache: 'no-store' };
    if (body) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, body: j || {} }; });
    });
  }
  function busy() { var l = (S && S.lanes) || {}; return ['main', 'side', 'review'].some(function (k) { return l[k] && l[k] !== 'idle'; }); }
  function schedule() { clearTimeout(timer); timer = setTimeout(poll, busy() ? 1000 : 5000); }
  function poll() {
    clearTimeout(timer);
    return request('/api/state').then(function (r) {
      if (r.status === 200 && typeof r.body.version === 'number') {
        if (failing) { failing = false; hint(''); }
        if (r.body.version !== drawnVersion) { S = r.body; draw(); drawnVersion = S.version; }
      } else { failing = true; hint('The harness did not send the plan. Reload the page.'); }
    }).catch(function () { failing = true; hint('The harness is not answering. Is it still running?'); }).then(schedule);
  }
  function act(action, payload) {
    var body = { action: action }; Object.keys(payload || {}).forEach(function (k) { body[k] = payload[k]; });
    hint('');
    return request('/api/act', body).then(function (r) {
      if (!r.body.ok) { hint(r.body.error ? String(r.body.error) : 'That cannot be done right now.'); }
      poll();
      return !!r.body.ok;
    }).catch(function () { hint('The harness is not answering. Is it still running?'); return false; });
  }
  function hint(t) { $('hint').textContent = t || ''; }

  /* ================= the diagram ================= */

  /* Deterministic layered layout. Columns: longest path along edges; a step with no
     step before it sits one column before its first follower. Rows: in each column,
     steps take the median row of the steps feeding them, else the next free row.
     Lines: straight when the row is clear; otherwise one bend in the gap before the
     target (or after the source); a step blocked on its own row goes under, through
     the corridor between rows. Vertical runs use their own lane in the gap. */
  function computeLayout(list, edges, avail) {
    var ids = list.map(function (s) { return s.id; }), idx = {};
    ids.forEach(function (id, i) { idx[id] = i; });
    var E = arr(edges).filter(function (e) { return e && has(idx, e.from) && has(idx, e.to) && e.from !== e.to; });
    var seen = {}; E = E.filter(function (e) { var k = e.from + '>' + e.to; if (seen[k]) { return false; } seen[k] = 1; return true; });
    var preds = {}, succs = {}, col = {}, row = {};
    ids.forEach(function (id) { preds[id] = []; succs[id] = []; col[id] = 0; });
    E.forEach(function (e) { preds[e.to].push(e.from); succs[e.from].push(e.to); });
    for (var it = 0; it < ids.length; it++) {
      var changed = false;
      E.forEach(function (e) { if (col[e.to] < col[e.from] + 1 && col[e.from] + 1 < ids.length) { col[e.to] = col[e.from] + 1; changed = true; } });
      if (!changed) { break; }
    }
    ids.forEach(function (id) {
      if (!preds[id].length && succs[id].length) {
        var m = Math.min.apply(null, succs[id].map(function (t) { return col[t]; }));
        col[id] = Math.max(0, m - 1);
      }
    });
    /* a step nothing connects goes in the column of the step that asked for it, under it */
    list.forEach(function (s) { if (!preds[s.id].length && !succs[s.id].length && s.near && has(idx, s.near)) { col[s.id] = col[s.near]; } });
    var ncol = 1; ids.forEach(function (id) { ncol = Math.max(ncol, col[id] + 1); });
    for (var c = 0; c < ncol; c++) {
      var inCol = ids.filter(function (id) { return col[id] === c; });
      var want = {};
      inCol.forEach(function (id) {
        var p = preds[id].filter(function (q) { return row[q] != null && col[q] < c; }).map(function (q) { return row[q]; }).sort(function (a, b) { return a - b; });
        want[id] = p.length ? p[(p.length - 1) >> 1] : -1;
      });
      inCol.sort(function (a, b) {
        var wa = want[a] < 0 ? 1e6 : want[a], wb = want[b] < 0 ? 1e6 : want[b];
        return wa - wb || idx[a] - idx[b];
      });
      var r = -1;
      inCol.forEach(function (id) { r = Math.max(want[id], r + 1); row[id] = r; });
    }
    var nrow = 1; ids.forEach(function (id) { nrow = Math.max(nrow, row[id] + 1); });
    var at = {}; ids.forEach(function (id) { at[col[id] + ':' + row[id]] = id; });
    function rowFree(r, c1, c2) { for (var c = c1; c <= c2; c++) { if (at[c + ':' + r]) { return false; } } return true; }
    function stepTop(id) { return row[id] * ROW + PILLS; }
    function mid(id) { return stepTop(id) + STEP_H / 2; }

    /* 1. route kinds */
    var routes = E.filter(function (e) { return col[e.from] < col[e.to]; }).map(function (e) {
      var a = e.from, b = e.to, ca = col[a], cb = col[b], ra = row[a], rb = row[b], kind;
      var between = cb - ca > 1;
      if (ra === rb && (!between || rowFree(ra, ca + 1, cb - 1))) { kind = 'straight'; }
      else if (ra === rb) { kind = 'under'; }
      else if (!between || rowFree(ra, ca + 1, cb - 1)) { kind = 'bendB'; }
      else if (rowFree(rb, ca + 1, cb - 1)) { kind = 'bendA'; }
      else { kind = 'around'; }
      return { e: e, a: a, b: b, kind: kind, ay: mid(a) };
    });
    routes.sort(function (p, q) { return col[p.a] - col[q.a] || row[p.a] - row[q.a] || col[p.b] - col[q.b] || row[p.b] - row[q.b]; });

    /* 2. corridor rows for 'around' and 'under' */
    var corridorUse = {};
    routes.forEach(function (rt) {
      if (rt.kind === 'under') { rt.cr = row[rt.a]; }
      else if (rt.kind === 'around') { rt.cr = Math.min(row[rt.a], row[rt.b]); }
      if (rt.cr != null) {
        var k = corridorUse[rt.cr] = (corridorUse[rt.cr] || 0) + 1;
        rt.cy = rt.cr * ROW + CORRIDOR + (k - 1) * 6;
      }
    });

    /* 3. ports on the left side of each target */
    ids.forEach(function (id) {
      var ins = routes.filter(function (rt) { return rt.b === id && rt.kind !== 'under'; });
      if (!ins.length) { return; }
      var top = stepTop(id), lo = top + PORT_PAD, hi = top + STEP_H - PORT_PAD;
      ins.forEach(function (rt) { rt.ideal = rt.kind === 'around' ? rt.cy : rt.ay; });
      ins.sort(function (p, q) { return p.ideal - q.ideal || col[p.a] - col[q.a]; });
      var ys = ins.map(function (rt) { return Math.min(hi, Math.max(lo, rt.ideal)); });
      if (ins.length === 1) { ys[0] = ins[0].kind === 'straight' ? ins[0].ay : mid(id); }
      for (var i = 1; i < ys.length; i++) { ys[i] = Math.max(ys[i], ys[i - 1] + PORT_GAP); }
      for (var j = ys.length - 1; j >= 0; j--) { var cap = j === ys.length - 1 ? hi : ys[j + 1] - PORT_GAP; ys[j] = Math.min(ys[j], cap); }
      ins.forEach(function (rt, i) {
        rt.by = ys[i];
        if (Math.abs(rt.by - rt.ay) < 1 && (rt.kind === 'bendB' || rt.kind === 'bendA')) { rt.kind = 'straight'; rt.by = rt.ay; }
        else if (rt.kind === 'straight' && Math.abs(rt.by - rt.ay) >= 1) { rt.kind = 'bendB'; }
      });
    });
    /* bottom ports for 'under' */
    var outUnder = {}, inUnder = {};
    routes.forEach(function (rt) {
      if (rt.kind !== 'under') { return; }
      var ko = outUnder[rt.a] = (outUnder[rt.a] || 0) + 1, ki = inUnder[rt.b] = (inUnder[rt.b] || 0) + 1;
      rt.ox = 36 + (ko - 1) * 12; rt.ix = 52 + (ki - 1) * 12;
    });

    /* 4. lanes in the gaps (interval packing, deterministic) */
    var gapLanes = [];
    for (var g = 0; g < ncol - 1; g++) { gapLanes.push([]); }
    function lane(gap, y1, y2) {
      var lo2 = Math.min(y1, y2) - 6, hi2 = Math.max(y1, y2) + 6, lanes = gapLanes[gap];
      for (var k = 0; ; k++) {
        if (!lanes[k]) { lanes[k] = []; }
        var clash = lanes[k].some(function (iv) { return !(hi2 < iv[0] || lo2 > iv[1]); });
        if (!clash) { lanes[k].push([lo2, hi2]); return k; }
      }
    }
    routes.forEach(function (rt) {
      if (rt.kind === 'bendB') { rt.lb = lane(col[rt.b] - 1, rt.ay, rt.by); }
      else if (rt.kind === 'bendA') { rt.la = lane(col[rt.a], rt.ay, rt.by); }
      else if (rt.kind === 'around') { rt.la = lane(col[rt.a], rt.ay, rt.cy); rt.lb = lane(col[rt.b] - 1, rt.cy, rt.by); }
    });

    /* 5. gap widths, then spread to the room there is */
    var gaps = gapLanes.map(function (l) { return l.length ? Math.max(MIN_GAP, LANE_END + l.length * LANE + 12) : MIN_GAP; });
    var used = ncol * STEP_W + gaps.reduce(function (s, x) { return s + x; }, 0);
    if (gaps.length && avail > used) {
      var extra = (avail - used) / gaps.length;
      gaps = gaps.map(function (x) { return Math.floor(x + Math.min(extra, Math.max(0, MAX_GAP - x))); });
    }
    var colX = [0];
    for (var c2 = 1; c2 < ncol; c2++) { colX.push(colX[c2 - 1] + STEP_W + gaps[c2 - 1]); }
    function laneX(gap, k) { return colX[gap + 1] - LANE_END - k * LANE; }

    var pos = {};
    ids.forEach(function (id) { pos[id] = { x: colX[col[id]], y: stepTop(id), col: col[id], row: row[id] }; });

    /* 6. segments, in the order the value travels */
    var segs = {};
    routes.forEach(function (rt) {
      var A = pos[rt.a], B = pos[rt.b], ax = A.x + STEP_W, bx = B.x, s = [];
      if (rt.kind === 'straight') { s.push(['h', ax, rt.ay, bx]); }
      else if (rt.kind === 'bendB' || rt.kind === 'bendA') {
        var L = rt.kind === 'bendB' ? laneX(col[rt.b] - 1, rt.lb) : laneX(col[rt.a], rt.la);
        s.push(['h', ax, rt.ay, L], ['v', L, rt.ay, rt.by], ['h', L, rt.by, bx]);
      } else if (rt.kind === 'around') {
        var L1 = laneX(col[rt.a], rt.la), L2 = laneX(col[rt.b] - 1, rt.lb);
        s.push(['h', ax, rt.ay, L1], ['v', L1, rt.ay, rt.cy], ['h', L1, rt.cy, L2], ['v', L2, rt.cy, rt.by], ['h', L2, rt.by, bx]);
      } else {
        var ox = A.x + rt.ox, ix = B.x + rt.ix;
        s.push(['v', ox, A.y + STEP_H, rt.cy], ['h', ox, rt.cy, ix], ['v', ix, rt.cy, B.y + STEP_H]);
      }
      segs[rt.a + '>' + rt.b] = s.filter(function (q) { return q[0] === 'h' ? q[3] - q[1] >= 1 : Math.abs(q[3] - q[2]) >= 1; });
    });
    var width = colX[ncol - 1] + STEP_W;
    var height = nrow * ROW;
    return { pos: pos, segs: segs, width: width, height: height, ncol: ncol, edges: E };
  }

  var SVGNS = 'http://www.w3.org/2000/svg';
  function svgPath(svg, cls, d) { var p = document.createElementNS(SVGNS, 'path'); if (cls) { p.setAttribute('class', cls); } p.setAttribute('d', d); svg.appendChild(p); return p; }
  function segment(q, head) {
    var svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('class', 'fah-flow'); svg.setAttribute('aria-hidden', 'true');
    var line, hd, w, h, left, top;
    if (q[0] === 'h') {
      var len = q[3] - q[1]; w = len; h = 8; left = q[1]; top = q[2] - 4;
      var end = head ? len - 4 : len;
      line = 'M0 4H' + end; hd = 'M' + end + ' 1l4 3-4 3z';
    } else {
      var up = q[3] < q[2], l2 = Math.abs(q[3] - q[2]); w = 8; h = l2; left = q[1] - 4; top = Math.min(q[2], q[3]);
      if (!up) { var e2 = head ? l2 - 4 : l2; line = 'M4 0V' + e2; hd = 'M1 ' + e2 + 'l3 4 3-4z'; }
      else { var e3 = head ? 4 : 0; line = 'M4 ' + l2 + 'V' + e3; hd = 'M1 4l3-4 3 4z'; }
    }
    svg.setAttribute('width', w); svg.setAttribute('height', h); svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.style.left = left + 'px'; svg.style.top = top + 'px';
    svgPath(svg, null, line).setAttribute('pathLength', '100');
    if (head) { svgPath(svg, 'fah-flow__head', hd); }
    svgPath(svg, 'fah-flow__pulse', line).setAttribute('pathLength', '100');
    return svg;
  }

  function availWidth() {
    var cs = getComputedStyle(scroller);
    return scroller.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  }

  function makeStep(s) {
    var b = el('button', 'fah-step'); b.type = 'button'; b.setAttribute('data-step', s.id);
    b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false');
    add(b, el('span', 'fah-step__name'), el('span', 'fa-tag'));
    b.addEventListener('click', function (ev) { ev.stopPropagation(); clickStep(s.id); });
    return b;
  }

  function displayLine(s) {
    if (ui.review && hasReview()) {
      var ch = openChallenges(s);
      if (!ch.length) { return { text: '', kind: null }; }
      return { text: '▲ ' + (ch[0].title || ch[0].challenge.concern || '') + (ch.length > 1 ? ' +' + (ch.length - 1) : ''), kind: null };
    }
    var l = s.line;
    return l && l.text ? { text: String(l.text), kind: l.kind || null } : { text: '', kind: null };
  }
  function lastAnswerSteps() { return steps().filter(function (s) { return s.last_run && s.last_run.in_last_answer; }); }
  function hasAnswers() { return steps().some(function (s) { return has(s, 'last_run'); }); }
  function hasBuild() { return steps().some(function (s) { return has(s, 'build'); }); }
  function hasReview() { return !!(S && S.review && typeof S.review === 'object'); }
  /* A message keeps what a later layer stored with it; show it only while that layer is on (ARCHITECTURE 3.4). */
  function layerOn(n) { return !!(S && Array.isArray(S.layers) && S.layers.indexOf(n) >= 0); }

  function tagFor(s) {
    var parts = [];
    var o = s.origin && ORIGIN[s.origin.kind];
    if (s.in_plan === false) { parts.push(['not in the plan', 'Added while answering; not in the plan']); }
    var lineText = (s.line && s.line.text) || '';
    arr(s.marks).forEach(function (m) {
      if (!m || !m.symbol) { return; }
      if (m.symbol === '◌' && lineText.indexOf('◌') >= 0 && !ui.review) { return; }
      parts.push([m.symbol + (m.count ? ' ' + m.count : ''), m.title || '']);
    });
    if (o) { parts.push([o[0], originTitle(s.origin)]); }
    return parts;
  }

  function drawDiagram() {
    var list = steps();
    var answerSteps = lastAnswerSteps();
    var anyAnswer = answerSteps.length > 0;
    var pm = planMarks();
    ui.joinTags = [];
    var inAnswer = {}; answerSteps.forEach(function (s) { inAnswer[s.id] = true; });

    /* steps: create, update, remove (kept by id so motion plays on change only) */
    var live = {};
    list.forEach(function (s) {
      live[s.id] = true;
      var b = stepEls[s.id];
      if (!b) { b = stepEls[s.id] = makeStep(s); canvas.appendChild(b); }
      b.querySelector('.fah-step__name').textContent = label(s);
      b.title = label(s);
      b.classList.toggle('fah-step--from-you', s.kind === 'from_you');
      b.classList.toggle('fah-step--your-call', s.kind === 'your_call');
      var tag = b.querySelector('.fa-tag'); tag.textContent = '';
      tagFor(s).forEach(function (p) { var sp = el('span', null, p[0]); if (p[1]) { sp.title = p[1]; } tag.appendChild(sp); });
      if (pm.running[s.id]) {
        var rn = el('span', 'dg-tag'), wk = el('span', 'fah-working'); wk.setAttribute('aria-hidden', 'true');
        add(rn, wk, 'running again'); tag.appendChild(rn);
      } else if (pm.changed[s.id] && pm.word) {
        var tg = el('span', 'dg-tag dg-tag__new'); tg.appendChild(F.mark(pm.who, null, 9)); add(tg, pm.word);
        tg.title = pm.title; tag.appendChild(tg);
        if (joinAnim && pm.node === joinAnim) { tg.style.visibility = 'hidden'; ui.joinTags.push(tg); }
      }
      b.classList.toggle('dg-touch', !!pm.touch[s.id] || !!pm.running[s.id]);
      b.classList.toggle('dg-touch--far', !pm.touch[s.id] && !pm.running[s.id] && !!pm.far[s.id]);
      var nyou = !!s.needs_you;
      if (needShown[s.id] !== nyou) { F.needsYou(b, nyou); needShown[s.id] = nyou; }
      /* the Review view fades by challenges only; otherwise the last answer decides */
      var faded = !nyou && (ui.review && hasReview() ? !openChallenges(s).length : anyAnswer && !inAnswer[s.id]);
      F.fade(b, faded);
      b.classList.toggle('fah-step--selected', ui.selected === s.id || (!!ui.markNode && !!pm.changed[s.id]));
    });
    Object.keys(stepEls).forEach(function (id) {
      if (!live[id]) { stepEls[id].remove(); delete stepEls[id]; delete lineShown[id]; delete needShown[id]; if (ui.pop === id) { closePop(false); } if (ui.attached === id) { ui.attached = null; } }
    });
    if (ui.selected && !live[ui.selected]) { ui.selected = null; }

    /* layout (only when the shape or the room changes) */
    var avail = Math.max(0, availWidth());
    var key = JSON.stringify([list.map(function (s) { return s.id + (s.near ? '<' + s.near : ''); }), S.edges || [], Math.round(avail / 8)]);
    if (key !== layKey) {
      layKey = key;
      lay = computeLayout(list, S.edges, avail);
      canvas.querySelectorAll('.fah-flow').forEach(function (n) { n.remove(); });
      edgeSegs = {};
      var frag = document.createDocumentFragment();
      Object.keys(lay.segs).forEach(function (k) {
        var q = lay.segs[k];
        edgeSegs[k] = q.map(function (seg, i) { var svg = segment(seg, i === q.length - 1); frag.appendChild(svg); return svg; });
      });
      canvas.insertBefore(frag, canvas.firstChild);
      list.forEach(function (s) { var p = lay.pos[s.id], b = stepEls[s.id]; b.style.left = p.x + 'px'; b.style.top = p.y + 'px'; });
      canvas.style.width = lay.width + 'px';
      canvas.style.height = (list.length ? lay.height : 0) + 'px';
    }
    /* keep keyboard order = plan order */
    list.forEach(function (s) { canvas.appendChild(stepEls[s.id]); });

    /* pills: inputs above the step that uses them */
    pillEls.forEach(function (n) { n.remove(); }); pillEls = [];
    list.forEach(function (s) {
      if (s.kind === 'from_you') { return; }
      var ins = arr(s.inputs); if (!ins.length) { return; }
      var row = el('div', 'fah-pills'), p = lay.pos[s.id];
      row.style.left = p.x + 'px'; row.style.top = (p.y - PILLS) + 'px';
      row.setAttribute('aria-label', 'Inputs of ' + label(s));
      canvas.insertBefore(row, canvas.firstChild); pillEls.push(row);
      /* the design's rule: more than three inputs show two and "+N"; fewer if they do not fit the step's width */
      for (var n = ins.length > 3 ? 2 : ins.length; n >= 1; n--) {
        fillPills(row, ins, n, pm);
        if (row.scrollWidth <= STEP_W + 1) { break; }
      }
    });

    /* second lines: an answer plays along the arrows; a build staggers in plan order */
    var aKey = answerSteps.map(function (s) { return s.id + ':' + (s.last_run.run || ''); }).sort().join(',');
    var playAnswer = answerKey !== null && aKey && aKey !== answerKey && !first && !ui.review && !reduced.matches;
    answerKey = aKey;
    if (playAnswer) { runAnswer(answerSteps); }
    var changes = [];
    list.forEach(function (s) {
      if (animating[s.id]) { return; }
      var d = displayLine(s), sig = d.text + '|' + d.kind;
      if (lineShown[s.id] === sig) { return; }
      lineShown[s.id] = sig;
      changes.push([s, d]);
    });
    if (first || reduced.matches || changes.length < 2) {
      changes.forEach(function (c) { setLine(c[0].id, c[1], !first); });
    } else {
      changes.forEach(function (c, i) { setTimeout(function () { setLine(c[0].id, c[1], true); }, i * 150); });
    }
  }

  function fillPills(row, ins, n, pm) {
    row.textContent = '';
    function marks(pill, ids) {
      var any = function (o) { return ids.some(function (id) { return o[id]; }); };
      pill.setAttribute('data-inputs', ids.join(' '));
      pill.classList.toggle('dg-touch', any(pm.touch));
      pill.classList.toggle('dg-needs', any(pm.needs));
      pill.classList.toggle('dg-pill--changed', any(pm.changed));
      pill.classList.toggle('dg-pill--sel', ids.indexOf(ui.selInput) >= 0);
    }
    ins.slice(0, n).forEach(function (id) {
      var i = S.inputs && S.inputs[id];
      var pill = el('span', 'fah-pill' + (i && i.used ? ' fah-pill--used' : ''), inputName(id));
      if (pm.changed[id] && i && i.value != null && String(i.value).length <= 12) { pill.appendChild(el('span', 'dg-pill__v', fmt(i.value))); }
      pill.title = inputName(id) + (i && i.value != null ? ' ' + fmt(i.value) : '') + (i && i.description && i.description !== i.name ? ': ' + i.description : '') + (i && i.origin ? ' (' + originTitle(i.origin) + ')' : '');
      marks(pill, [id]);
      row.appendChild(pill);
    });
    if (ins.length > n) {
      var rest = ins.slice(n), used = rest.some(function (id) { return S.inputs && S.inputs[id] && S.inputs[id].used; });
      var more = el('span', 'fah-pill' + (used ? ' fah-pill--used' : ''), '+' + rest.length);
      more.title = rest.map(inputName).join(', '); more.setAttribute('aria-label', 'and ' + more.title);
      marks(more, rest);
      row.appendChild(more);
    }
  }
  /* The input pills of one input id (several when more than one step uses it). */
  function pillsOf(id) {
    return Array.prototype.filter.call(canvas.querySelectorAll('.fah-pill[data-inputs]'), function (p) { return p.getAttribute('data-inputs').split(' ').indexOf(id) >= 0; });
  }
  function markPills() {
    canvas.querySelectorAll('.fah-pill[data-inputs]').forEach(function (p) { p.classList.toggle('dg-pill--sel', !!ui.selInput && p.getAttribute('data-inputs').split(' ').indexOf(ui.selInput) >= 0); });
  }

  /* What the decision history marks on the plan right now (ARCHITECTURE 9, B3):
     a pending proposal's impact (touched; its inputs need you unless a call waits), a join that is running,
     and what the latest node (or the node the person selected) changed. */
  var TAG_WORD = { value: 're-ran', assumption_corrected: 're-ran', plan_revised: 'changed', challenge_used: 'changed',
                   built: 'rebuilt', call: 'decided', assumption_confirmed: 'confirmed' };
  function planMarks() {
    var pm = { touch: {}, far: {}, needs: {}, running: {}, changed: {}, word: '', who: 'you', node: null, title: '' };
    var calls = decisionWaits();
    arr(threads()).forEach(function (t) {
      var p = t.proposal, imp = p && p.impact;
      if (!imp) { return; }
      var live = p.status === 'pending' && outcome(t) === 'open';
      var joining = p.status === 'accepted' && outcome(t) !== 'joined';
      if (!live && !joining) { return; }
      arr(imp.inputs).forEach(function (id) { pm.touch[id] = true; if (live && !calls) { pm.needs[id] = true; } });
      arr(imp.steps).forEach(function (id) { pm.touch[id] = true; });
      if (live) { arr(imp.downstream).forEach(function (id) { pm.far[id] = true; }); }
    });
    arr(S.activity).forEach(function (a) { if (a.what === 'join' && a.step) { pm.running[a.step] = true; } });
    var n = nodeById(ui.markNode) || nodeById(history().latest);
    if (n && TAG_WORD[n.kind]) {
      pm.word = TAG_WORD[n.kind]; pm.who = n.who; pm.node = n.id; pm.title = (WHO[n.who] || '') + ': ' + n.text;
      if (ui.markNode) {
        arr(n.touched && n.touched.steps).concat(arr(n.touched && n.touched.inputs)).forEach(function (id) { pm.changed[id] = true; });
      } else {
        steps().forEach(function (s) { if (s.changed_by === n.id) { pm.changed[s.id] = true; } });
        Object.keys(S.inputs || {}).forEach(function (id) { if (S.inputs[id].changed_by === n.id) { pm.changed[id] = true; } });
      }
    }
    return pm;
  }

  function setLine(id, d, animate) {
    var b = stepEls[id]; if (!b) { return; }
    F.setLine(b, d.text, d.kind || undefined);
    if (!animate) { b.classList.remove('is-arriving'); }
  }

  function runAnswer(answerSteps) {
    var me = ++animRun, ids = {};
    answerSteps.forEach(function (s) { ids[s.id] = true; animating[s.id] = true; setLine(s.id, { text: '' }, false); lineShown[s.id] = '|'; });
    var cols = {};
    answerSteps.forEach(function (s) { var c = lay.pos[s.id] ? lay.pos[s.id].col : 0; (cols[c] = cols[c] || []).push(s.id); });
    var order = Object.keys(cols).map(Number).sort(function (a, b) { return a - b; });
    function land(id) {
      delete animating[id];
      var s = stepById(id); if (!s) { return; }
      var d = displayLine(s); lineShown[id] = d.text + '|' + d.kind; setLine(id, d, true);
    }
    var chain = Promise.resolve();
    order.forEach(function (c) {
      chain = chain.then(function () {
        if (me !== animRun) { return; }
        cols[c].forEach(land);
        var outs = [];
        (lay.edges || []).forEach(function (e) {
          if (ids[e.from] && ids[e.to] && cols[c].indexOf(e.from) >= 0 && edgeSegs[e.from + '>' + e.to]) {
            var segsOf = edgeSegs[e.from + '>' + e.to];
            outs.push(F.flow(segsOf, Math.round(500 / Math.max(1, segsOf.length))));
          }
        });
        return outs.length ? Promise.all(outs) : F.wait(150);
      });
    });
    chain.then(function () { Object.keys(ids).forEach(function (id) { if (animating[id]) { land(id); } }); });
  }

  function clickStep(id) {
    var wasOpen = ui.pop === id;
    ui.selected = id; ui.attached = id; ui.notice = null; ui.popRun = null; ui.selInput = null;
    if (ui.markNode) { ui.markNode = null; drawDiagram(); markNodeSel(); }
    F.select(stepEls[id], document); markPills();
    clearTraced();
    drawComposer();
    if (wasOpen) { closePop(true); } else { openPop(id); }
  }

  /* ---------- the step pop-up ---------- */
  function popRow(left, right, you) {
    var r = el('div', 'fah-pop__row' + (you ? ' fah-pop__row--you' : ''));
    add(r, typeof left === 'string' ? el('span', null, left) : left, typeof right === 'string' ? el('span', null, right) : right);
    return r;
  }
  function popHead(text) { return el('p', 'fa-sec-h', text); }
  function linkBtn(text, fn, aria) { var b = el('button', 'fah-link', text); b.type = 'button'; if (aria) { b.setAttribute('aria-label', aria); } b.addEventListener('click', function (ev) { ev.stopPropagation(); fn(); }); return b; }
  function btn(text, fn, primary) { var b = el('button', 'fah-btn' + (primary ? ' fah-btn--primary' : ''), text); b.type = 'button'; b.addEventListener('click', function (ev) { ev.stopPropagation(); fn(b); }); return b; }
  var CHECKED = { second_pass: 'checked by a second pass', you: 'confirmed by you' };

  function popContent(s) {
    var pop = el('div', 'fah-pop'); pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', label(s)); pop.id = 'pop';
    var head = el('div', 'fah-pop__head');
    add(head, el('span', null, label(s)), linkBtn('✕', function () { closePop(true); }, 'Close'));
    pop.appendChild(head);
    var kinds = { calculation: 'A calculation', from_you: 'A figure from you', your_call: 'Your call' };
    var kindLine = el('span', 'fa-sub', (kinds[s.kind] || '') + (s.in_plan === false ? ' · not in the plan' : ''));
    pop.appendChild(kindLine);
    var o = originLine(s.origin); if (o) { pop.appendChild(o); }

    if (s.formula || s.method || s.produces) {
      pop.appendChild(popHead('What it does'));
      if (s.formula) { pop.appendChild(el('p', 'fa-p', s.formula)); }
      else if (s.method) { pop.appendChild(el('p', 'fa-p', s.method)); }
      if (s.produces) { pop.appendChild(popRow('Gives', s.produces)); }
      if (s.cadence) { pop.appendChild(popRow('How often', s.cadence)); }
    }
    var ins = arr(s.inputs);
    if (ins.length) { pop.appendChild(popRow('Needs', ins.map(function (id) { var i = S.inputs && S.inputs[id]; return inputName(id) + (i && i.value != null ? ' ' + fmt(i.value) : ''); }).join(', '))); }

    if (arr(s.particulars).length) {
      pop.appendChild(popHead('Particulars'));
      var ul = el('ul', 'fa-list');
      s.particulars.forEach(function (p) { var li = add(el('li'), p.text || p.what || ''); var m = originMark(p.origin); if (m) { li.appendChild(m); } if (p.handling) { li.appendChild(el('span', 'fa-sub', p.handling)); } ul.appendChild(li); });
      pop.appendChild(ul);
    }
    if (arr(s.open_questions).length) {
      pop.appendChild(popHead('Open questions'));
      var uq = el('ul', 'fa-list');
      s.open_questions.forEach(function (q) { var li = add(el('li'), '● ' + (q.text || '')); var m = originMark(q.origin); if (m) { li.appendChild(m); } uq.appendChild(li); });
      pop.appendChild(uq);
    }

    var b = s.build;
    if (b) {
      pop.appendChild(popHead('Build'));
      var st = { none: 'Not built yet', building: 'Building now', built: 'Built and tested', not_built: 'Not built', stale: 'Stale: the step changed, so it must be built again' }[b.status] || '';
      pop.appendChild(el('p', 'fa-p', st + (b.reason && b.status !== 'stale' ? ': ' + b.reason : '')));
      if (b.status === 'stale' && b.reason) { pop.appendChild(el('span', 'fa-sub', b.reason)); }
      if (b.plan_check && arr(b.plan_check.departures).length) {
        var pc = el('div', 'fah-notice');
        pc.appendChild(el('div', null, 'How the calculation departs from the plan:'));
        var ud = el('ul', 'fa-list'); b.plan_check.departures.forEach(function (d) { ud.appendChild(el('li', null, d)); }); pc.appendChild(ud);
        if (!b.plan_check.confirmed) { pc.appendChild(add(el('div', 'fah-row'), btn('These are fine', function () { act('confirm_plan_check', { step: s.id }); }, true))); }
        pop.appendChild(pc);
      }
      arr(b.example_list).forEach(function (ex) {
        var box = el('div', 'fa-ex');
        box.appendChild(popRow('Example ' + ex.n, ex.checked_by ? CHECKED[ex.checked_by] || ex.checked_by : 'left out: the passes disagreed', ex.checked_by === 'you'));
        var sh = ex.shown || {};
        var io = sh.inputs ? sh.inputs.map(function (q) { return q[0] + ' ' + shownText(q[1]); }).join(', ')
          : Object.keys(ex.inputs || {}).map(function (k) { return k.replace(/_/g, ' ') + ' ' + fmt(ex.inputs[k]); }).join(', ');
        var sub = el('span', 'fa-sub', io + ' → ' + shownText(sh.expected, ex.expected) + (ex.second_pass != null && ex.checked_by == null ? ' (second pass: ' + shownText(sh.second_pass, ex.second_pass) + ')' : ''));
        if (ex.checked_by !== 'you') { sub.appendChild(linkBtn('Confirm', function () { act('confirm_example', { step: s.id, n: ex.n }); }, 'Confirm example ' + ex.n)); }
        box.appendChild(sub);
        if (structured(sh.expected)) { box.appendChild(shownNode(sh.expected)); }
        if (sh.inputs && (structured(sh.expected) || sh.inputs.some(function (q) { return structured(q[1]); }))) {
          box.appendChild(exactValues({ inputs: ex.inputs, expected: ex.expected }));
        }
        pop.appendChild(box);
      });
      arr(b.disagreement).forEach(function (d) {
        var dsh = d.shown || {};
        pop.appendChild(el('p', 'fa-p', 'Example ' + d.n + ': expected ' + shownText(dsh.expected, d.expected) + ', the code gives ' + shownText(dsh.code_gives, d.code_gives) + '.'));
      });
      if (b.status !== 'none' || b.module) {
        var foot = el('div', 'fah-pop__foot');
        if (b.tests) { foot.appendChild(el('span', null, b.tests + ' tests, ' + (b.passing === b.tests ? 'all passing' : b.passing + ' passing'))); }
        if (b.code && b.code.module_py) { foot.appendChild(linkBtn(ui.code ? 'Hide code' : (b.code.tests_py ? 'Code and tests' : 'Code'), function () { ui.code = !ui.code; refreshPop(); })); }
        if (b.module) { foot.appendChild(linkBtn('Run tests now', function () { act('run_tests', { step: s.id }); })); }
        if (foot.childNodes.length) { pop.appendChild(foot); }
        if (b.tested_at) { pop.appendChild(el('span', 'fa-sub', 'Last tested ' + when(b.tested_at))); }
        if (ui.code && b.code && b.code.module_py) {
          pop.appendChild(el('pre', 'fa-code', b.code.module_py));
          if (b.code.tests_py) { pop.appendChild(popHead('Tests')); pop.appendChild(el('pre', 'fa-code', b.code.tests_py)); }
        }
      }
    }

    var r = runShown(s), lr = s.last_run;
    if (r) {
      var inAnswer = !!(lr && lr.in_last_answer && (r.run === lr.run || (r.message && r.message === lr.message)));
      var runHead = popHead(inAnswer ? 'In the last answer' : (lr && r.run === lr.run ? 'Last run' : 'Run'));
      runHead.classList.add('fa-runhead'); pop.appendChild(runHead);
      var others = arr(s.runs);
      if (others.length > 1) {
        var picker = el('div', 'fa-runs'); picker.setAttribute('aria-label', 'Recent runs');
        others.forEach(function (o) {
          var b = linkBtn(shownText(o.shown && o.shown.output, o.output), function () { ui.popRun = o.run; refreshPop(); }, 'Show run ' + o.run);
          b.title = 'Run ' + o.run + (o.ts ? ', ' + when(o.ts) : '');
          if (o.run === r.run) { b.setAttribute('aria-current', 'true'); }
          picker.appendChild(b);
        });
        pop.appendChild(picker);
      }
      var rc = el('div', 'fa-receipt'), rs = r.shown || {};
      if (rs.inputs) {
        rs.inputs.forEach(function (q) { rc.appendChild(popRow(q[0], shownText(q[1]))); if (structured(q[1])) { rc.appendChild(shownNode(q[1])); } });
      } else {
        Object.keys(r.inputs || {}).forEach(function (k) { rc.appendChild(popRow(k.replace(/_/g, ' '), fmt(r.inputs[k]))); });
      }
      var out = popRow('Came out', shownText(rs.output, r.output)); out.classList.add('fa-receipt__out'); rc.appendChild(out);
      if (structured(rs.output)) { rc.appendChild(shownNode(rs.output)); }
      arr(r.assumptions).forEach(function (a) { rc.appendChild(el('span', 'fa-sub', '◌ ' + a)); });
      rc.appendChild(exactValues({ inputs: r.inputs, output: r.output }));
      rc.appendChild(el('span', 'fa-sub', 'Run ' + (r.run || '') + (r.test_run != null ? ', after test run ' + r.test_run : '') + (r.ts ? ', ' + when(r.ts) : '')));
      pop.appendChild(rc);
    }

    if (arr(s.unconfirmed).length) {
      pop.appendChild(popHead('Not confirmed yet'));
      s.unconfirmed.forEach(function (a) { pop.appendChild(el('p', 'fa-p', '◌ ' + a.text)); });
      var nm = openNoticeFor(s.id);
      if (nm) {
        pop.appendChild(add(el('div', 'fah-row'),
          btn('Confirm', function () { act('confirm_assumptions', { message: nm.id }); }, true),
          btn('Change it', function () { changeIt(nm); })));
      }
    }

    if (s.calls) {
      if (s.calls.open) { pop.appendChild(popHead('Your call')); pop.appendChild(el('p', 'fa-p', 'Waiting for your answer in the chat.')); }
      if (arr(s.calls.records).length) {
        pop.appendChild(popHead('What you decided'));
        s.calls.records.forEach(function (rec) {
          var li = el('div', 'fa-receipt');
          li.appendChild(el('span', 'fa-sub', rec.question || ''));
          var n = parseInt(rec.choice, 10);
          var chosen = !isNaN(n) && rec.options && rec.options[n - 1] ? rec.options[n - 1] : null;
          li.appendChild(el('span', null, chosen ? 'You chose: ' + chosen : 'In your words: ' + (rec.words || '')));
          if (chosen && rec.words) { li.appendChild(el('span', 'fa-sub', '“' + rec.words + '”')); }
          if (rec.ts) { li.appendChild(el('span', 'fa-sub', when(rec.ts))); }
          pop.appendChild(li);
        });
      }
    }

    var chs = arr(s.challenges).map(threadOfChallenge).filter(Boolean);
    if (chs.length) {
      pop.appendChild(popHead('Reviewer'));
      chs.forEach(function (t) { pop.appendChild(challengeBlock(t, true)); });
    }
    pop.addEventListener('click', function (ev) { ev.stopPropagation(); });
    return pop;
  }

  /* The run the pop-up shows: the one a clicked figure named, else the step's run of the last answer or latest. */
  function runShown(s) {
    if (ui.popRun) {
      var all = arr(s.runs).concat(s.last_run ? [s.last_run] : []);
      for (var i = 0; i < all.length; i++) { if (all[i].run === ui.popRun) { return all[i]; } }
    }
    return s.last_run || arr(s.runs)[0] || null;
  }

  function challengeBlock(t, inPop) {
    var c = t.challenge, wrap = el('div', inPop ? 'fa-receipt' : 'fa-rv');
    var text = el('div', 'fa-rv__text');
    add(text, el('span', null, '▲ ' + (t.title || '')));
    if (inPop && c.concern) { text.appendChild(el('span', 'fa-sub', c.concern)); }
    if (inPop && c.proposal) { text.appendChild(el('span', 'fa-sub', 'Proposed: ' + c.proposal)); }
    if (c.status !== 'open') { text.appendChild(el('span', 'fa-sub', c.status === 'used' ? 'Used' : 'Dismissed')); }
    wrap.appendChild(text);
    var row = el('div', 'fah-row');
    if (c.status === 'open') {
      if (c.kind !== 'question') { row.appendChild(btn('Use this', function () { act('use_challenge', { challenge: c.id }); }, true)); }
      row.appendChild(btn('Dismiss', function () { act('dismiss_challenge', { challenge: c.id }); }));
    }
    row.appendChild(linkBtn('Open branch', function () { closePop(false); openBranch(t.id, false); }));
    wrap.appendChild(row);
    return wrap;
  }

  function placePop() {
    if (!popEl || !ui.pop || !lay || !lay.pos[ui.pop]) { return; }
    var p = lay.pos[ui.pop], w = popEl.offsetWidth, h = popEl.offsetHeight;
    var cs = getComputedStyle(scroller), pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    var visRight = scroller.scrollLeft + scroller.clientWidth - pad;
    var x = Math.max(0, Math.min(p.x, Math.max(lay.width, visRight) - w, visRight - w));
    var below = p.y + STEP_H + 22, above = p.y - PILLS - 8 - h;
    var y = (below + h > lay.height && above >= 0) ? above : below;
    popEl.style.left = x + 'px'; popEl.style.top = y + 'px';
    canvas.style.height = Math.max(lay.height, y + h + 16) + 'px';
  }
  function openPop(id) {
    closePop(false);
    var s = stepById(id); if (!s) { return; }
    ui.pop = id; ui.code = false;
    popEl = popContent(s);
    stepEls[id].after(popEl);
    stepEls[id].setAttribute('aria-expanded', 'true');
    placePop();
    if (popEl.scrollIntoView) { popEl.scrollIntoView({ block: 'nearest', behavior: reduced.matches ? 'auto' : 'smooth' }); }
  }
  function refreshPop() {
    if (!ui.pop) { return; }
    var s = stepById(ui.pop); if (!s) { closePop(false); return; }
    var scrollTop = popEl ? popEl.scrollTop : 0;
    var fresh = popContent(s); fresh.style.animation = 'none';
    popEl.replaceWith(fresh); popEl = fresh; popEl.scrollTop = scrollTop;
    placePop();
  }
  function closePop(focusStep) {
    if (!ui.pop) { return; }
    var id = ui.pop; ui.pop = null;
    if (popEl) { popEl.remove(); popEl = null; }
    if (lay) { canvas.style.height = lay.height + 'px'; }
    var b = stepEls[id];
    if (b) { b.setAttribute('aria-expanded', 'false'); if (focusStep) { b.focus(); } }
  }

  /* ---------- top bar: goal, Build, Whole plan, Review ---------- */
  function drawTop() {
    var g = S.goal, goal = $('goal'), meta = $('goalmeta');
    show(goal, !!(g && g.text));
    if (g && g.text) { goal.textContent = g.text; goal.title = g.text; var m = originMark(g.origin); if (m) { goal.appendChild(m); } }
    var bits = [];
    if (S.phase === 'proposed') { bits.push('Proposed plan, not accepted yet'); }
    if (S.phase === 'interview') { bits.push('The plan is being worked out'); }
    if (g && g.mode) { bits.push(g.mode === 'ongoing' ? 'Kept up to date' : 'A one-off answer'); }
    meta.textContent = bits.join(' · '); show(meta, bits.length > 0);

    var tools = $('tools'); tools.textContent = '';
    if (S.phase === 'accepted' && hasBuild()) { tools.appendChild(buildButton()); }
    if (S.context) {
      var w = linkBtn('Whole plan', function () { ui.whole = !ui.whole; drawWhole(); if (ui.whole) { $('whole').scrollIntoView({ block: 'start', behavior: reduced.matches ? 'auto' : 'smooth' }); } });
      w.setAttribute('aria-expanded', String(ui.whole)); w.setAttribute('aria-controls', 'whole');
      tools.appendChild(w);
    }
    if (hasReview() && S.phase === 'accepted') {
      if (S.review.running) {      /* a bar alone says nothing to a first-time user: name it */
        var rw = el('span', 'fa-building fa-quiet fa-reviewing'); rw.setAttribute('role', 'status'); rw.title = 'The reviewer is looking at the plan';
        var wk = el('span', 'fah-working'); wk.setAttribute('aria-hidden', 'true'); add(rw, wk, 'Reviewing'); tools.appendChild(rw);
      }
      var open = S.review.open || 0;
      var rv = el('button', 'fah-btn', 'Review' + (open ? ' · ' + open : '')); rv.type = 'button';
      rv.setAttribute('aria-pressed', String(ui.review));
      rv.addEventListener('click', function () { ui.review = !ui.review; drawDiagram(); drawReviewList(); rv.setAttribute('aria-pressed', String(ui.review)); });
      tools.appendChild(rv);
    } else if (ui.review) { ui.review = false; }
  }

  function buildButton() {
    var calc = steps().filter(function (s) { return s.build; });
    var acts = arr(S.activity);
    var running = acts.some(function (a) { return a.what === 'build'; }) || calc.some(function (s) { return s.build.status === 'building'; });
    var built = calc.filter(function (s) { return s.build.status === 'built'; }).length;
    var todo = calc.filter(function (s) { return ['none', 'not_built', 'stale'].indexOf(s.build.status) >= 0; });
    var b = el('button', 'fah-btn'); b.type = 'button'; b.id = 'build';
    if (running) {
      var a = acts.filter(function (x) { return x.what === 'build'; })[0];
      var at = a && a.step ? stepById(a.step) : null;
      var span = el('span', 'fa-building');
      var wk = el('span', 'fah-working'); wk.setAttribute('aria-hidden', 'true');
      add(span, wk, 'Building ' + Math.min(built + 1, calc.length) + ' of ' + calc.length);
      b.appendChild(span); b.setAttribute('aria-disabled', 'true');
      b.title = at ? label(at) + (a.text ? ': ' + a.text : '') : (a && a.text) || '';
    } else if (!todo.length) {
      b.textContent = 'All ' + calc.length + ' built'; b.setAttribute('aria-disabled', 'true');
    } else {
      b.classList.add('fah-btn--primary');
      var fresh = todo.every(function (s) { return s.build.status === 'none'; });
      b.textContent = built === 0 && fresh ? 'Build the calculations' : (fresh ? 'Build ' + todo.length + ' more' : 'Rebuild ' + todo.length + (todo.length === 1 ? ' step' : ' steps'));
      b.addEventListener('click', function () { b.setAttribute('aria-disabled', 'true'); act('build'); });
    }
    return b;
  }

  /* ---------- whole-plan context (off screen until asked for) ---------- */
  function itemLi(it, extra) {
    var li = add(el('li'), it.text || it.what || it.term || '');
    var m = originMark(it.origin); if (m) { li.appendChild(m); }
    if (extra) { li.appendChild(el('span', 'fa-sub', extra)); }
    return li;
  }
  function drawWhole() {
    var w = $('whole');
    var link = document.querySelector('#tools .fah-link'); if (link) { link.setAttribute('aria-expanded', String(ui.whole)); }
    show(w, !!(ui.whole && S.context)); w.textContent = '';
    if (!ui.whole || !S.context) { return; }
    var c = S.context;
    var head = el('div', 'fa-section__head');
    add(head, el('h2', 'fah-question', 'Whole plan'), linkBtn('Close', function () { ui.whole = false; drawWhole(); }));
    w.appendChild(head);
    if (S.goal && S.goal.text) { w.appendChild(add(el('p', 'fa-p'), S.goal.text, originMark(S.goal.origin))); }
    function part(title, items, fn) {
      if (!arr(items).length) { return; }
      w.appendChild(el('h3', null, title));
      var ul = el('ul'); items.forEach(function (it) { ul.appendChild(fn ? fn(it) : itemLi(it)); }); w.appendChild(ul);
    }
    part('In scope', c.scope_in);
    part('Not in scope', c.scope_out);
    part('Assumptions', c.assumptions, function (it) { return itemLi(it, it.handling); });
    part('Done when', c.done);
    part('Open questions', c.open_questions, function (it) { return itemLi({ text: '● ' + (it.text || ''), origin: it.origin }); });
    part('Terms', c.glossary, function (g) {
      var li = add(el('li'), el('b', null, g.term || ''), ': ' + (g.definition || ''));
      var m = originMark(g.origin); if (m) { li.appendChild(m); }
      if (g.person_says) { li.appendChild(el('span', 'fa-sub', 'You say “' + g.person_says + '”')); }
      return li;
    });
    part('Changes', c.revisions, function (r) {
      var s = r.step ? stepById(r.step) : null;
      return add(el('li'), (r.by === 'reviewer' ? 'From the reviewer' : 'You') + (s ? ', on ' + label(s) : '') + ': “' + (r.words || '') + '”', el('span', 'fa-sub', when(r.ts)));
    });
  }

  /* ---------- Review view: one line per challenged step ---------- */
  function drawReviewList() {
    var box = $('reviewlist'); box.textContent = '';
    var on = ui.review && hasReview() && S.phase === 'accepted';
    show(box, on); if (!on) { return; }
    var head = el('div', 'fa-section__head'); head.appendChild(el('h2', 'fah-question', 'Review'));
    box.appendChild(head);
    var any = false;
    steps().forEach(function (s) {
      openChallenges(s).forEach(function (t) {
        any = true;
        var row = challengeBlock(t, false);
        var chip = linkBtn(label(s), function () { clickStep(s.id); });
        chip.className = 'fah-chip'; chip.style.marginRight = '8px';
        row.firstChild.insertBefore(chip, row.firstChild.firstChild);
        box.appendChild(row);
      });
    });
    if (!any) { box.appendChild(el('p', 'fa-p fa-quiet', S.review.running ? 'The reviewer is looking at the plan.' : 'Nothing is challenged.')); }
  }

  /* ================= the panel: the decision history, the latest exchange ================= */
  /* Before the plan is accepted the panel is a plain conversation. From "Plan accepted" on, the trunk
     holds the decisions and the branches fork from it; the main chat's latest exchange sits at the foot. */
  var WHO = { you: 'You', assistant: 'The assistant', harness: 'The harness', reviewer: 'The reviewer' };
  var CHIP_CLASS = { value: 'given', assumption: 'assumed', result: 'result', decision: 'decision' };
  var CHIP_WORDS = { value: 'a value that went in', assumption: 'an assumption', result: 'worked out by a step', decision: 'a decision' };
  var panelSig = '', seenMsgs = null, prevOutcome = {}, joinAnim = null, graphRows = [], graphRO = null;

  function history() { return S && S.history && typeof S.history === 'object' ? S.history : { trunk: [], latest: null }; }
  function trunk() { return arr(history().trunk); }
  function nodeById(id) { var t = trunk(); for (var i = 0; i < t.length; i++) { if (t[i].id === id) { return t[i]; } } return null; }
  function outcome(t) { return t.outcome || (t.status === 'used' ? 'joined' : t.status === 'dismissed' ? 'dead' : 'open'); }
  function opener(t) { return t.origin || (t.kind === 'review' ? 'reviewer' : t.kind === 'harness' ? 'harness' : 'you'); }
  function subjectOf(t) { return t.subject && t.subject.kind ? t.subject : (t.step ? { kind: 'step', step: t.step } : { kind: 'plan' }); }
  function pendingOf(t) { return t.proposal && t.proposal.status === 'pending' && outcome(t) === 'open' ? t.proposal : null; }
  function decisionWaits() { return !!(S && S.waiting && S.waiting.kind === 'decision'); }
  function threadById(id) { return arr(threads()).filter(function (t) { return t.id === id; })[0] || null; }
  /* Runs a join replaced (node.change.runs: old run -> new run), each with the input the join changed.
     What those runs produced is no longer current; of what went in, only the changed value is. */
  function staleRuns() {
    var out = {};
    trunk().forEach(function (n) {
      var c = n.change || {}, r = c.runs;
      if (r && typeof r === 'object') { Object.keys(r).forEach(function (k) { out[k] = { key: c.input || null }; }); }
    });
    return out;
  }
  function chipStale(c, stale) {
    var sub = c.subject || {}, hit = sub.run && stale[sub.run];
    if (!hit) { return false; }
    if (c.kind === 'result') { return true; }
    if (c.kind === 'value') { return !!hit.key && sub.key === hit.key; }
    return false;
  }
  function plainNum(v) { var t = String(v == null ? '' : v); return /^-?\d+(\.\d+)?$/.test(t) ? Number(t).toLocaleString('en-US', { maximumFractionDigits: 2 }) : t; }
  function keyWords(k) { k = String(k || '').replace(/_/g, ' '); return k.charAt(0).toUpperCase() + k.slice(1); }
  function subjKey(sub) { sub = sub || {}; return [sub.kind, sub.run, sub.key, sub.step, sub.input, sub.node, sub.text].join('|'); }
  function svgEl(tag, attrs) { var e = document.createElementNS(SVGNS, tag); Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] != null) { e.setAttribute(k, attrs[k]); } }); return e; }
  function icon(name) {
    var svg = svgEl('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true' });
    if (name === 'see') { svg.appendChild(svgEl('path', { d: 'M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8s-2.4 4.5-6.5 4.5S1.5 8 1.5 8z' })); svg.appendChild(svgEl('circle', { cx: 8, cy: 8, r: 2 })); }
    else if (name === 'fix') { svg.appendChild(svgEl('path', { d: 'M2 6h12' })); svg.appendChild(svgEl('path', { d: 'M5 13.5l3-4.5 3 4.5' })); }
    else { svg.appendChild(svgEl('path', { d: 'M4.5 1.8v12.4' })); svg.appendChild(svgEl('path', { d: 'M4.5 10.5c0-4 6.5-3 6.5-6.2' })); svg.appendChild(svgEl('circle', { cx: 11, cy: 3, r: 1.4 })); }
    return svg;
  }
  function smooth() { return reduced.matches ? 'auto' : 'smooth'; }
  function clearTraced() { document.querySelectorAll('.dg-chip.is-traced, .fah-num.is-traced').forEach(function (n) { n.classList.remove('is-traced'); }); }

  /* ---------- see it in the graph ---------- */
  function seeStep(id, run, openIt) {
    var b = stepEls[id]; if (!b) { return; }
    ui.selInput = null; ui.selected = id;
    if (ui.markNode) { ui.markNode = null; drawDiagram(); markNodeSel(); }
    F.select(b, document); markPills();
    if (openIt) {
      ui.popRun = run || null; openPop(id);
      var rh = popEl && popEl.querySelector('.fa-runhead');
      if (rh) { popEl.scrollTop = Math.max(0, rh.offsetTop - 12); }
    } else { closePop(false); b.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: smooth() }); }
  }
  function seeInput(id) {
    closePop(false); ui.selected = null; F.select(null, document);
    if (ui.markNode) { ui.markNode = null; drawDiagram(); markNodeSel(); }
    ui.selInput = id; markPills();
    var p = pillsOf(id)[0]; if (p) { p.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: smooth() }); }
  }
  function seeNode(id) {
    closePop(false); ui.selInput = null; ui.selected = null; F.select(null, document); markPills();
    ui.markNode = ui.markNode === id ? null : id;
    drawDiagram(); markNodeSel();
    var card = document.querySelector('[data-node="' + id + '"]');
    if (card) { card.scrollIntoView({ block: 'nearest', behavior: smooth() }); }
  }
  /* A chip's subject is enough to find its place (3.5): the input, else the step and its run. */
  function seeSubject(sub, host) {
    clearTraced(); if (host) { host.classList.add('is-traced'); }
    sub = sub || {};
    if (sub.kind === 'decision') { if (nodeById(sub.node)) { seeNode(sub.node); } return; }
    if (sub.input && S.inputs && S.inputs[sub.input] && pillsOf(sub.input).length) { seeInput(sub.input); return; }
    if (sub.step && stepEls[sub.step]) { seeStep(sub.step, sub.run || null, !!sub.run); }
  }

  /* ---------- refs, chips, figures, and their menu ---------- */
  function refStep(id) {
    var s = stepById(id); if (!s) { return null; }
    var b = el('button', 'dg-ref' + (s.kind === 'from_you' ? ' dg-ref--you' : s.kind === 'your_call' ? ' dg-ref--call' : ''), s.number != null ? s.number : s.name);
    b.type = 'button'; b.title = label(s); b.setAttribute('aria-label', 'Step ' + label(s) + ': show in the plan');
    b.addEventListener('click', function (ev) { ev.stopPropagation(); seeStep(id, null, false); });
    return b;
  }
  function refInput(id) {
    var name = inputName(id);
    if (!(S.inputs && S.inputs[id])) { return el('span', null, name); }
    var b = el('button', 'dg-ref dg-ref--input', name); b.type = 'button'; b.title = name;
    b.setAttribute('aria-label', name + ': show in the plan');
    b.addEventListener('click', function (ev) { ev.stopPropagation(); seeInput(id); });
    return b;
  }
  function refs(ids) { return arr(ids).map(function (id) { return /^in:/.test(id) || (S.inputs && S.inputs[id]) ? refInput(id) : refStep(id); }).filter(Boolean); }

  function withMenu(host, name, sub, see, focusBack) {
    var lab = el('span', 'dg-menu__label', 'See in graph'); lab.setAttribute('aria-hidden', 'true');
    var row = el('span', 'dg-menu__row');
    var acts = [['see', 'See in graph', see]];
    if (layerOn(4) && sub) {
      acts.push(['fix', 'Challenge or correct', function () { startBranch(sub, 'fix', name); }],
                ['branch', 'Talk about it', function () { startBranch(sub, 'talk', name); }]);
    }
    acts.forEach(function (a) {
      var b = el('button', 'dg-menu__btn'); b.type = 'button'; b.title = a[1];
      b.setAttribute('aria-label', a[1] + ': ' + name); b.appendChild(icon(a[0]));
      b.addEventListener('click', function (ev) { ev.preventDefault(); ev.stopPropagation(); host.classList.add('is-shut'); a[2](); });
      b.addEventListener('mouseenter', function () { lab.textContent = a[1]; });
      b.addEventListener('focus', function () { lab.textContent = a[1]; });
      row.appendChild(b);
    });
    var menu = el('span', 'dg-menu'); menu.setAttribute('role', 'group'); menu.setAttribute('aria-label', 'Actions for ' + name);
    add(menu, row, lab); host.appendChild(menu);
    function place() {
      var r = host.getBoundingClientRect(), log = $('log');
      var scrolls = log.scrollHeight > log.clientHeight + 1 && getComputedStyle(log).overflowY !== 'visible';
      var lr = scrolls ? log.getBoundingClientRect() : { top: 0, right: window.innerWidth };
      host.classList.toggle('dg-below', r.top - lr.top < 72);
      host.classList.toggle('dg-end', r.left + 150 > Math.min(lr.right, window.innerWidth));
    }
    function reset() { host.classList.remove('is-shut'); lab.textContent = 'See in graph'; }
    host.addEventListener('mouseenter', place);
    host.addEventListener('focusin', place);
    host.addEventListener('mouseleave', reset);
    host.addEventListener('focusout', function (e) { if (!host.contains(e.relatedTarget)) { reset(); } });
    host.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); host.classList.add('is-shut'); focusBack.focus(); } });
  }

  function chipEl(c, o) {
    o = o || {};
    var kind = CHIP_CLASS[c.kind] || 'given', stale = !!o.stale || c.status === 'corrected';
    var wrap = el('span', 'dg-chip dg-chip--' + kind + (c.kind === 'assumption' ? ' dg-chip--wrap' : '') +
      (c.status === 'confirmed' ? ' dg-chip--confirmed' : '') + (stale ? ' dg-chip--stale' : ''));
    var btn = el('button', 'dg-chip__btn'); btn.type = 'button';
    if (o.label && c.label && kind !== 'decision' && kind !== 'assumed') { btn.appendChild(el('span', 'dg-chip__k', c.label)); }
    if (kind === 'assumed') { var g = el('span', 'dg-chip__g', c.status === 'confirmed' ? '✓' : '◌'); g.setAttribute('aria-hidden', 'true'); btn.appendChild(g); }
    if (kind === 'result') { var g2 = el('span', 'dg-chip__g', '→'); g2.setAttribute('aria-hidden', 'true'); btn.appendChild(g2); }
    if (kind === 'decision') { var nd = nodeById(c.subject && c.subject.node); var g3 = el('span', 'dg-chip__g'); g3.appendChild(F.mark(nd ? nd.who : 'you', null, 10)); btn.appendChild(g3); }
    btn.appendChild(el('span', 'dg-chip__v', c.text));
    var name = (c.label && kind !== 'decision' ? c.label + ' ' : '') + c.text;
    btn.setAttribute('aria-label', name + ', ' + CHIP_WORDS[c.kind] + (c.status ? ', ' + c.status : '') + (stale ? ', no longer current' : '') + '. Show in the plan');
    btn.addEventListener('click', function (ev) { ev.stopPropagation(); seeSubject(c.subject, wrap); });
    wrap.appendChild(btn);
    withMenu(wrap, name, c.subject, function () { seeSubject(c.subject, wrap); }, btn);
    return wrap;
  }

  /* The figures in a message stay underlined and clickable, and get the same menu with the subject 3.5 derives. */
  function withFigures(p, m) {
    var text = String(m.text || ''), figs = arr(layerOn(3) ? m.figures : null).filter(function (f) { return f && f.step && stepById(f.step); }), pos = 0, spans = [];
    var stale = staleRuns();
    figs.forEach(function (f) {
      var s = f.start, e = f.end;
      if (!(typeof s === 'number' && typeof e === 'number' && text.slice(s, e) === f.text)) { s = text.indexOf(f.text, pos); e = s + String(f.text).length; }
      if (s >= 0) { spans.push([s, e, f]); }
    });
    spans.sort(function (a, b) { return a[0] - b[0]; });
    spans.forEach(function (sp) {
      if (sp[0] < pos) { return; }
      p.appendChild(document.createTextNode(text.slice(pos, sp[0])));
      var f = sp[2], sid = f.step, word = text.slice(sp[0], sp[1]), old = !!(f.run && stale[f.run]);
      var host = el('span', 'dg-fig');
      var n = el('span', 'fah-num' + (old ? ' dg-num--stale' : ''), word);
      n.tabIndex = 0; n.setAttribute('role', 'button');
      n.setAttribute('aria-label', word + ', from step ' + label(stepById(sid)) + (old ? ', no longer current' : ''));
      function go(ev) { if (ev) { ev.preventDefault(); ev.stopPropagation(); } clearTraced(); n.classList.add('is-traced'); seeStep(sid, f.run || null, true); }
      n.addEventListener('click', go);
      n.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { go(ev); } });
      host.appendChild(n);
      var sub = f.run ? { kind: 'result', run: f.run, step: sid, value: word } : f.input ? { kind: 'input', input: f.input, step: null } : { kind: 'step', step: sid };
      withMenu(host, word, sub, function () { go(null); }, n);
      p.appendChild(host); pos = sp[1];
    });
    p.appendChild(document.createTextNode(text.slice(pos)));
    return p;
  }
  function chip(stepId) { var s = stepById(stepId); return s ? el('span', 'fah-chip', label(s)) : null; }

  /* An answer's chips as facts: results with their labels, then what they rest on and assume. */
  function factsOf(m, skipAssumptions) {
    var list = layerOn(3) ? arr(m.chips).filter(function (c) { return c && c.text != null; }) : [];
    if (!list.length) { return null; }
    var stale = staleRuns(), dl = el('dl', 'dg-facts'), any = false;
    function old(c) { return chipStale(c, stale); }
    function row(t, kids) { if (!kids.length) { return; } any = true; var dd = el('dd'); kids.forEach(function (k) { dd.appendChild(k); }); dl.appendChild(el('dt', null, t)); dl.appendChild(dd); }
    function of(kind) { return list.filter(function (c) { return c.kind === kind; }); }
    of('decision').forEach(function (c) { row('Decided', [chipEl(c)]); });
    of('result').forEach(function (c) { row(c.label || 'Result', [chipEl(c, { stale: old(c) })]); });
    row('Rests on', of('value').map(function (c) { return chipEl(c, { label: true, stale: old(c) }); }));
    if (!skipAssumptions) { row('Assumes', of('assumption').map(function (c) { return chipEl(c, { stale: old(c) }); })); }
    return any ? dl : null;
  }

  /* ---------- messages of the main chat ---------- */
  function openNoticeFor(stepId) {
    var c = arr(S.chat);
    for (var i = c.length - 1; i >= 0; i--) { var n = c[i].notice; if (n && n.status === 'open' && arr(n.steps).indexOf(stepId) >= 0) { return c[i]; } }
    return null;
  }
  function changeIt(m) {
    ui.notice = m.id; ui.attached = arr(m.notice.steps)[0] || null; setSide(false);
    drawComposer(); input.focus();
  }
  function messageNodes(m, ctx) {
    var nodes = [], kind = m.kind || 'text';
    var noticeOpen = !!(m.notice && m.notice.status === 'open' && layerOn(4));
    if (kind === 'decision' && m.decision && layerOn(4)) {
      var d = m.decision;
      if (d.status === 'open') {
        var box = el('div', 'fah-decision'); box.setAttribute('role', 'group'); box.setAttribute('aria-label', 'Your call');
        var c = chip(d.step || m.step); if (c) { box.appendChild(add(el('div'), c)); }
        box.appendChild(withFigures(el('p', 'fah-decision__q'), { text: d.question || m.text || '', figures: m.figures }));
        arr(d.options).forEach(function (o, i) {
          var sug = d.suggested === i + 1;
          var b = btn(o + (sug ? ' · suggested' : ''), function () { act('choose', { decision: d.id, option: i + 1 }); }, sug);
          b.classList.add('fah-btn--block'); box.appendChild(b);
        });
        if (d.why) { box.appendChild(el('p', 'fah-decision__why', d.why)); }
        nodes.push(box);
      }
    } else if (m.who === 'you') {
      var py = el('p', 'fah-msg fah-msg--you'); var c2 = chip(m.step); if (c2) { py.appendChild(c2); }
      add(py, m.text || '');
      if (m.queued) { py.appendChild(el('span', 'fa-meta', 'Waiting its turn')); }
      nodes.push(py);
    } else {
      var quiet = kind === 'withheld' || m.who === 'harness';
      var facts = factsOf(m, noticeOpen);
      var lead = withFigures(el('p', facts ? 'fa-ans-lead' + (quiet ? ' fa-muted' : '') : 'fah-msg' + (quiet ? ' fa-muted' : '')), m);
      if (m.step) { var c3 = chip(m.step); if (c3) { lead.insertBefore(el('br'), lead.firstChild); lead.insertBefore(c3, lead.firstChild); } }
      if (facts) { var ans = el('div', 'fah-msg dg-answer'); add(ans, lead, facts); nodes.push(ans); } else { nodes.push(lead); }
      if (kind === 'plan' && ctx.acceptHere) {
        nodes.push(add(el('div', 'fah-row'), btn('Accept plan', function (b) { b.setAttribute('aria-disabled', 'true'); act('accept_plan'); }, true)));
      }
    }
    if (noticeOpen) {
      var nt = el('div', 'fah-notice'), as = arr(m.notice.assumptions);
      var achips = arr(layerOn(3) ? m.chips : null).filter(function (c) { return c && c.kind === 'assumption'; });
      nt.appendChild(el('div', null, '◌ This rests on ' + (as.length === 1 ? 'one thing' : as.length + ' things') + ' you haven\'t confirmed' + (achips.length ? ':' : (as.length === 1 ? ': ' + lower(as[0] && as[0].text) : ':'))));
      if (achips.length) {
        var dl = el('dl', 'dg-facts'), dd = el('dd'); achips.forEach(function (c) { dd.appendChild(chipEl(c)); });
        dl.appendChild(el('dt', null, 'Assumes')); dl.appendChild(dd); nt.appendChild(dl);
      } else if (as.length > 1) {
        var ul = el('ul', 'fa-list'); as.forEach(function (a) { ul.appendChild(el('li', null, a.text)); }); nt.appendChild(ul);
      }
      nt.appendChild(add(el('div', 'fah-row'),
        btn('Confirm', function () { act('confirm_assumptions', { message: m.id }); }, true),
        btn('Change it', function () { changeIt(m); })));
      nodes.push(nt);
    }
    return nodes;
  }
  function lower(t) { t = String(t || ''); return t && /^[A-Z][a-z]/.test(t) ? t.charAt(0).toLowerCase() + t.slice(1) : t; }

  /* ---------- trunk nodes ---------- */
  function joinMessageOf(nodeId) {
    var c = arr(S.chat);
    for (var i = c.length - 1; i >= 0; i--) {
      if (arr(c[i].chips).some(function (x) { return x && x.kind === 'decision' && x.subject && x.subject.node === nodeId; })) { return c[i]; }
    }
    return null;
  }
  function nodeMeta(n) {
    var t = n.touched || {}, ins = arr(t.inputs), sts = arr(t.steps), meta = el('p', 'dg-node__meta');
    function words(w) { meta.appendChild(el('span', null, w)); }
    function put(list) { refs(list).forEach(function (r) { meta.appendChild(r); }); }
    switch (n.kind) {
      case 'plan_accepted':
        var nIn = Object.keys(S.inputs || {}).length;
        words(steps().filter(function (s) { return s.in_plan !== false; }).length + ' steps' + (nIn ? ', ' + nIn + ' inputs' : '')); break;
      case 'value': case 'assumption_corrected':
        if (ins.length) { words('Changed'); put(ins); }
        if (sts.length) { words(ins.length ? 're-ran' : 'Re-ran'); put(sts); } break;
      case 'built': if (sts.length) { words(n.who === 'harness' ? 'By itself, built' : 'Built'); put(sts); } break;
      case 'call': if (sts.length) { words('Your call on'); put(sts); } break;
      case 'challenge_used': if (sts.length || ins.length) { words('On a challenge, changed'); put(ins.concat(sts)); } break;
      case 'assumption_confirmed': if (sts.length) { words('Confirmed, on'); put(sts); } break;
      default: if (sts.length || ins.length) { words('Changed'); put(ins.concat(sts)); }
    }
    return meta.childNodes.length ? meta : null;
  }
  function nodeEl(n, isNew) {
    var card = el('div', 'dg-node' + (isNew ? ' is-new' : '')); card.setAttribute('data-node', n.id);
    var title = el('button', 'dg-node__title'); title.type = 'button'; title.setAttribute('data-anchor', '');
    add(title, el('span', 'dg-sr', (WHO[n.who] || 'You') + ', decided: '), n.text || '');
    title.setAttribute('aria-pressed', String(ui.markNode === n.id));
    title.title = 'Show what this changed in the plan';
    title.addEventListener('click', function (ev) { ev.stopPropagation(); seeNode(n.id); });
    card.appendChild(title);
    var meta = nodeMeta(n); if (meta) { card.appendChild(meta); }
    var jm = joinMessageOf(n.id), results = jm ? arr(jm.chips).filter(function (c) { return c.kind === 'result'; }) : [];
    if (results.length && layerOn(3)) {
      var rs = el('div', 'dg-node__results'), stale = staleRuns();
      results.forEach(function (c) { var ce = chipEl(c, { stale: chipStale(c, stale) }); ce.title = c.label || ''; rs.appendChild(ce); });
      card.appendChild(rs);
    }
    arr(n.change && n.change.failed).forEach(function (f) {
      var s = stepById(f.step); card.appendChild(el('p', 'dg-node__fail', (s ? 'Step ' + s.number : 'A step') + ' could not run again: ' + (f.reason || '')));
    });
    return card;
  }
  function markNodeSel() {
    document.querySelectorAll('.dg-node__title').forEach(function (b) { b.setAttribute('aria-pressed', String(b.parentNode.getAttribute('data-node') === ui.markNode)); });
    drawGraph(null);
  }

  /* ---------- branches ---------- */
  function subjectChip(sub) {
    if (sub.kind === 'value') { return { kind: 'value', label: sub.input && S.inputs && S.inputs[sub.input] ? inputName(sub.input) : keyWords(sub.key), text: plainNum(sub.value), status: null, subject: sub }; }
    if (sub.kind === 'result') {
      var s = stepById(sub.step), shown = null;
      if (s) { arr(s.runs).concat(s.last_run ? [s.last_run] : []).forEach(function (r) { if (r.run === sub.run && r.shown && r.shown.output) { shown = r.shown.output.text; } }); }
      return { kind: 'result', label: s ? s.name : '', text: shown || plainNum(sub.value), status: null, subject: sub };
    }
    if (sub.kind === 'assumption') { return { kind: 'assumption', label: '', text: sub.text || '', status: null, subject: sub }; }
    if (sub.kind === 'decision') { var n = nodeById(sub.node); return { kind: 'decision', label: 'Decided', text: n ? n.text : String(sub.node), status: null, subject: sub }; }
    return null;
  }
  function subjectLine(sub) {
    var p = el('p', 'dg-branch__on'), c = subjectChip(sub);
    if (c) { add(p, 'From', chipEl(c, { label: true })); return p; }
    if (sub.kind === 'step' && stepById(sub.step)) { add(p, 'On', refStep(sub.step), el('span', null, stepById(sub.step).name)); return p; }
    if (sub.kind === 'input') { add(p, 'On', refInput(sub.input)); return p; }
    add(p, 'On the whole plan');
    return p;
  }
  function subjectName(sub) {
    var c = subjectChip(sub); if (c) { return (c.label && c.kind !== 'decision' ? c.label + ' ' : '') + c.text; }
    if (sub.kind === 'step' && stepById(sub.step)) { return label(stepById(sub.step)); }
    if (sub.kind === 'input') { return inputName(sub.input); }
    return 'the plan';
  }
  function sayLine(m, dead) {
    var who = m.who || 'assistant', p = el('p', 'dg-say' + (who === 'you' ? ' dg-say--you' : ''));
    p.appendChild(F.mark(who, dead ? 'dead' : 'open', 10));
    var body = add(el('span'), el('span', 'dg-sr', (WHO[who] || '') + ': '), m.text || '');
    var srcs = arr(m.sources).filter(function (x) { return x && safeUrl(x.url); });
    if (srcs.length) {
      var sp = el('span', 'dg-say__src'); add(sp, ' ');
      srcs.forEach(function (x, i) { if (i) { add(sp, ', '); } add(sp, '↗ ', link(x.title || x.url, x.url)); });
      body.appendChild(sp);
    }
    p.appendChild(body);
    return p;
  }
  function replyBox(key, ph, send) {
    var w = el('div', 'dg-reply'), i = el('input');
    i.type = 'text'; i.autocomplete = 'off'; i.placeholder = ph; i.setAttribute('data-key', key);
    i.setAttribute('aria-label', ph.replace('…', ''));
    i.value = ui.replies[key] || '';
    i.addEventListener('input', function () { ui.replies[key] = i.value; });
    i.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && !ev.isComposing) {
        ev.preventDefault();
        var text = i.value.trim(); if (!text) { return; }
        i.value = ''; ui.replies[key] = '';
        send(text).then(function (ok) { if (!ok && !ui.replies[key]) { ui.replies[key] = text; var j = document.querySelector('[data-key="' + key + '"]'); if (j) { j.value = text; } } });
      }
      if (ev.key === 'Escape' && key === 'draft') { ev.preventDefault(); ui.draft = null; drawPanel(true); input.focus(); }
    });
    w.appendChild(i);
    return w;
  }
  function proposeEl(t, p, needs) {
    var ch = p.change || {}, imp = p.impact || {};
    var box = el('div', 'dg-propose'); box.setAttribute('role', 'group'); box.setAttribute('aria-label', 'Proposed change');
    var q = el('p', 'dg-propose__q'); q.appendChild(F.mark('harness', needs ? 'needs' : 'open', 12));
    var target = ch.input && S.inputs && S.inputs['in:' + ch.input] ? 'in:' + ch.input : null;
    if (ch.kind === 'value') { add(q, 'Change ' + lower(ch.label || keyWords(ch.input)) + ' to ' + plainNum(ch.to) + '?'); }
    else { add(q, ch.step && stepById(ch.step) ? 'Change step ' + stepById(ch.step).number + ' of the plan?' : 'Change the plan?'); }
    box.appendChild(q);
    var r1 = el('p', 'dg-propose__row');
    if (ch.kind === 'value') {
      r1.appendChild(target ? refInput(target) : el('span', null, ch.label || keyWords(ch.input)));
      if (ch.from != null) { r1.appendChild(el('s', null, plainNum(ch.from))); add(r1, '→'); }
      r1.appendChild(el('b', null, plainNum(ch.to)));
    } else { add(r1, '“' + (ch.words || p.words || '') + '”'); }
    box.appendChild(r1);
    if (arr(imp.steps).length) { var rr = add(el('p', 'dg-propose__row'), el('span', 'dg-propose__k', 'Re-runs')); refs(imp.steps).forEach(function (r) { rr.appendChild(r); }); box.appendChild(rr); }
    if (arr(imp.downstream).length) { var rd = add(el('p', 'dg-propose__row'), el('span', 'dg-propose__k', 'Further on')); refs(imp.downstream).forEach(function (r) { rd.appendChild(r); }); box.appendChild(rd); }
    var no = ch.kind === 'value' && ch.from != null ? 'Keep ' + plainNum(ch.from) : 'No, keep it';
    box.appendChild(add(el('div', 'fah-row'),
      btn('Yes, change it', function (b) { b.setAttribute('aria-disabled', 'true'); act('accept_proposal', { proposal: p.id }); }, true),
      btn(no, function () { act('decline_proposal', { proposal: p.id }); })));
    if (decisionWaits()) { box.appendChild(el('span', 'fa-meta', 'Answer your call first; then this can join.')); }
    return box;
  }
  function branchState(t, ctx) {
    var oc = outcome(t), c = t.challenge;
    if (ctx.needs) { return 'needs you'; }
    if (ctx.joining) { return 'joining'; }
    if (ctx.working) { return 'answering'; }
    if (oc === 'joined') { return 'joined'; }
    if (oc === 'dead') { return c && c.status === 'dismissed' ? 'dismissed' : 'no change'; }
    if (t.kind === 'review' && c) { return c.kind === 'question' ? 'question' : 'challenge'; }
    return 'open';
  }
  function branchEl(t, ctx) {
    var oc = outcome(t), who = opener(t), prop = pendingOf(t), dead = oc === 'dead';
    ctx.needs = !!prop && !decisionWaits();
    ctx.joining = !!(t.proposal && t.proposal.status === 'accepted' && oc !== 'joined');
    var d = el('details', 'dg-branch dg-branch--' + (dead ? 'dead' : oc === 'joined' ? 'joined' : 'open') + (ctx.needs ? ' dg-branch--needs' : ''));
    d.id = 'thread-' + t.id; d.setAttribute('data-branch', t.id);
    var isOpen = has(ui.branchOpen, t.id) ? ui.branchOpen[t.id] : ctx.defaultOpen;
    if (isOpen) { d.open = true; }
    var sum = el('summary'), title = el('span', 'dg-branch__title');
    title.setAttribute('data-anchor', '');
    add(title, el('span', 'dg-sr', (WHO[who] || 'You') + ' opened: '), t.title || subjectName(subjectOf(t)));
    add(sum, title, el('span', 'dg-branch__state', branchState(t, ctx)));
    d.appendChild(sum);
    var body = el('div', 'dg-branch__body');
    body.appendChild(subjectLine(subjectOf(t)));
    arr(t.messages).forEach(function (m, i) {
      if (i === 0 && m.who === 'you' && t.title && String(m.text || '').trim() === String(t.title).trim()) { return; }   /* the title says it */
      body.appendChild(sayLine(m, dead));
    });
    if (ctx.working) {
      var w = el('div', 'fa-working'), bar = el('div', 'fah-working'); bar.setAttribute('role', 'status'); bar.setAttribute('aria-label', 'Answering in the branch');
      add(w, bar, 'Answering'); body.appendChild(w);
    }
    var c = t.challenge;
    if (c && c.status === 'open') {
      var last = arr(t.messages).slice(-1)[0];
      if (c.proposal && !(last && String(last.text || '').indexOf(c.proposal) >= 0)) { body.appendChild(el('p', 'dg-say', 'Proposed: ' + c.proposal)); }
      var row = el('div', 'fah-row');
      if (c.kind !== 'question') { row.appendChild(btn('Use this', function () { act('use_challenge', { challenge: c.id }); }, true)); }
      row.appendChild(btn('Dismiss', function () { act('dismiss_challenge', { challenge: c.id }); }));
      body.appendChild(row);
    }
    if (prop) { body.appendChild(proposeEl(t, prop, ctx.needs)); }
    if (ctx.joining) {
      var jw = el('div', 'fa-working'), jb = el('div', 'fah-working'); jb.setAttribute('role', 'status'); jb.setAttribute('aria-label', 'Running the steps again');
      add(jw, jb, 'Yes. Running the steps again'); body.appendChild(jw);
    }
    if (t.proposal && t.proposal.status === 'failed' && oc === 'open') { body.appendChild(el('p', 'dg-branch__end', 'It could not join: ' + (t.proposal.reason || 'the change failed') + '.')); }
    if (oc === 'joined') {
      body.appendChild(el('p', 'dg-branch__end', who === 'harness' ? 'Joined by itself: tests are the harness’s own.' : t.kind === 'review' ? 'Joined when you used it.' : 'Joined when you said yes.'));
    } else if (dead) {
      var pr = t.proposal, ch = pr && pr.change;
      var kept = pr && pr.status === 'declined' && ch && ch.kind === 'value' && ch.from != null ? 'You kept ' + plainNum(ch.from) + '. ' : '';
      body.appendChild(el('p', 'dg-branch__end', kept + 'Nothing in the plan changed.'));
    }
    if (oc === 'open' && layerOn(4) && !ctx.joining) {
      body.appendChild(replyBox('reply:' + t.id, t.kind === 'review' ? 'Reply to the reviewer…' : 'Reply…', function (text) { return act('side', { text: text, thread: t.id }); }));
      if (t.kind === 'side') { body.appendChild(add(el('div', 'dg-branch__acts'), linkBtn('Close branch', function () { act('close_branch', { thread: t.id }); }))); }
    }
    d.appendChild(body);
    d.addEventListener('toggle', function () { ui.branchOpen[t.id] = d.open; if (d.open) { ui.openThread = t.id; } drawGraph(null); });
    return d;
  }
  function draftEl() {
    var dr = ui.draft, fix = dr.mode === 'fix';
    var d = el('details', 'dg-branch dg-branch--open'); d.open = true; d.id = 'thread-draft';
    var sum = el('summary'), title = el('span', 'dg-branch__title'); title.setAttribute('data-anchor', '');
    add(title, el('span', 'dg-sr', 'You, a new branch: '), (fix ? 'Correct ' : 'About ') + dr.name);
    add(sum, title, el('span', 'dg-branch__state', 'new'));
    d.appendChild(sum);
    var body = el('div', 'dg-branch__body');
    body.appendChild(subjectLine(dr.subject));
    body.appendChild(replyBox('draft', fix ? 'Say what should change…' : 'Start a branch about this…', function (text) {
      return act('side', { text: text, subject: dr.subject }).then(function (ok) { if (ok) { ui.draft = null; ui.wantNewThread = true; ui.replies.draft = ''; } return ok; });
    }));
    body.appendChild(add(el('div', 'dg-branch__acts'), linkBtn('Cancel', function () { ui.draft = null; drawPanel(true); input.focus(); })));
    d.appendChild(body);
    d.addEventListener('toggle', function () { if (!d.open) { ui.draft = null; drawPanel(true); } });
    return d;
  }
  /* Challenge or talk: a branch starts with the person's first message, so the page opens a draft until then.
     "Talk" opens the branch already about this subject, when there is one. */
  function startBranch(sub, mode, name) {
    if (!layerOn(4)) { return; }
    if (mode === 'talk') {
      var same = arr(threads()).filter(function (t) { return outcome(t) === 'open' && subjKey(subjectOf(t)) === subjKey(sub); })[0];
      if (same) { openBranch(same.id, true); return; }
    }
    ui.draft = { subject: sub, mode: mode, name: name };
    ui.focusKey = 'draft';
    drawPanel(true);
    var d = $('thread-draft'); if (d) { d.scrollIntoView({ block: 'nearest', behavior: smooth() }); }
  }
  function openBranch(id, focusReply) {
    ui.branchOpen[id] = true; ui.openThread = id;
    if (focusReply) { ui.focusKey = 'reply:' + id; }
    drawPanel(true);
    var n = $('thread-' + id);
    if (n) {
      n.open = true; n.scrollIntoView({ block: 'nearest', behavior: smooth() });
      if (!focusReply) { var s = n.querySelector('summary'); if (s) { s.focus({ preventScroll: true }); } }
    }
  }
  function openThread(id) { openBranch(id, false); }

  /* ---------- the graph: rows on a spine, lines drawn from measured positions ---------- */
  function rowEl(box, kind) {
    var r = el('div', 'dg-row dg-row--' + kind);
    add(r, el('div', 'dg-row__l'), el('div', 'dg-row__s'), el('div', 'dg-row__r'));
    box.appendChild(r);
    return r;
  }
  function buildGraph(box, T, list, ctxOf) {
    box.textContent = '';
    box.appendChild(svgEl('svg', { class: 'dg-svg', 'aria-hidden': 'true' }));
    graphRows = [];
    var placed = {}, onTrunk = {};
    T.forEach(function (n) { onTrunk[n.id] = true; });
    function branchRow(t) {
      if (placed[t.id]) { return; }
      placed[t.id] = true;
      var r = rowEl(box, 'branch');
      r.querySelector('.dg-row__r').appendChild(branchEl(t, ctxOf(t)));
      graphRows.push({ kind: 'branch', id: t.id, t: t, el: r, anchor: r.querySelector('[data-anchor]') });
    }
    T.forEach(function (n, i) {
      list.forEach(function (t) { if (outcome(t) === 'joined' && t.node === n.id) { branchRow(t); } });
      var r = rowEl(box, 'trunk');
      r.querySelector('.dg-row__l').appendChild(nodeEl(n, joinAnim === n.id));
      graphRows.push({ kind: 'trunk', id: n.id, n: n, el: r, anchor: r.querySelector('[data-anchor]') });
      list.forEach(function (t) {
        var joinedHere = outcome(t) === 'joined' && onTrunk[t.node];
        if (!joinedHere && (t.from === n.id || (i === 0 && (!t.from || !onTrunk[t.from])))) { branchRow(t); }
      });
    });
    list.forEach(branchRow);
    if (ui.draft) {
      var dr = rowEl(box, 'branch'); dr.querySelector('.dg-row__r').appendChild(draftEl());
      graphRows.push({ kind: 'draft', id: 'draft', el: dr, anchor: dr.querySelector('[data-anchor]') });
    }
    var now = rowEl(box, 'now'), nw = el('span', 'dg-now', 'Now'); nw.setAttribute('data-anchor', '');
    now.querySelector('.dg-row__l').appendChild(nw);
    graphRows.push({ kind: 'now', el: now, anchor: nw });
  }
  function rel(a, base) { var r = a.getBoundingClientRect(), b = base.getBoundingClientRect(); return { x: r.left - b.left, y: r.top - b.top, w: r.width, h: r.height }; }
  function drawGraph(anim) {
    var box = $('graph');
    if (box.hidden || !graphRows.length || !box.isConnected) { return {}; }
    box.classList.toggle('dg-graph--narrow', box.clientWidth < 440);
    var svg = box.querySelector('.dg-svg'); svg.textContent = '';
    var W = box.clientWidth, H = box.scrollHeight;
    svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    function path(d, cls, draw) { var p = svgEl('path', { d: d, class: 'dg-l ' + cls, pathLength: draw ? 100 : null }); svg.appendChild(p); return p; }
    var sp = rel(graphRows[0].el.querySelector('.dg-row__s'), box), X = Math.round(sp.x + sp.w / 2);
    var trunkY = {}, firstY = null, nowY = 0, marks = [], out = {};
    graphRows.forEach(function (r) {
      if (r.kind === 'trunk') { trunkY[r.id] = rel(r.anchor, box).y + 10; if (firstY == null) { firstY = trunkY[r.id]; } }
      if (r.kind === 'now') { nowY = rel(r.anchor, box).y + 8; }
    });
    if (firstY == null) { firstY = 12; }
    path('M' + X + ' ' + firstY + 'V' + nowY, 'dg-l--trunk');
    path('M' + (X - 6) + ' ' + nowY + 'H' + (X + 6), 'dg-l--trunk');
    graphRows.forEach(function (r) {
      if (r.kind === 'trunk') { marks.push([r.n.who, X, trunkY[r.id], null, 7, anim === r.id]); return; }
      if (r.kind !== 'branch' && r.kind !== 'draft') { return; }
      var t = r.t, oc = t ? outcome(t) : 'open', dead = oc === 'dead';
      var det = r.el.querySelector('details'), card = rel(det, box);
      var x1 = Math.round(card.x - 11), by = rel(r.anchor, box).y + 10, line = dead ? 'dg-l--dead' : 'dg-l--branch';
      path('M' + X + ' ' + (by - 18) + 'C' + X + ' ' + (by - 6) + ' ' + x1 + ' ' + (by - 14) + ' ' + x1 + ' ' + (by - 5), line);
      var ey = by, prop = null;
      if (det.open) {
        prop = r.el.querySelector('.dg-propose');
        var last = prop || r.el.querySelector('.dg-branch__body > :last-child');
        if (last) { ey = rel(last, box).y + (prop ? 20 : 9); }
      }
      if (ey > by + 6) { path('M' + x1 + ' ' + (by + 5) + 'V' + ey, line); }
      if (oc === 'joined' && trunkY[t.node] != null && trunkY[t.node] > ey) {
        var jy = trunkY[t.node];
        var jl = path('M' + x1 + ' ' + ey + 'V' + Math.max(ey, jy - 24) + 'C' + x1 + ' ' + (jy - 10) + ' ' + X + ' ' + (jy - 18) + ' ' + X + ' ' + (jy - 8), 'dg-l--branch', anim === t.node);
        if (anim === t.node) { out.line = jl; }
      }
      if (dead) { path('M' + x1 + ' ' + (ey + 6) + 'V' + (ey + 16), 'dg-l--dead'); path('M' + (x1 - 5) + ' ' + (ey + 17) + 'H' + (x1 + 5), 'dg-l--cap'); }
      marks.push([t ? opener(t) : 'you', x1, by, dead ? 'dead' : 'open', 5.5]);
      if (t && prop && pendingOf(t)) { marks.push(['harness', x1, ey, decisionWaits() ? 'open' : 'needs', 6]); }
    });
    if (ui.markNode && trunkY[ui.markNode] != null) { svg.appendChild(svgEl('circle', { class: 'dg-l dg-l--sel', cx: X, cy: trunkY[ui.markNode], r: 12 })); }
    marks.forEach(function (m) {
      var p = svgEl('path', { d: F.shape(m[0], m[1], m[2], m[4]), class: 'dg-shape' + (m[3] ? ' dg-shape--' + m[3] : '') });
      svg.appendChild(p);
      if (m[5]) { out.mark = p; }
    });
    return out;
  }

  /* ---------- the whole panel, drawn from the state ---------- */
  function workingThread(list) {
    if (!(S.lanes && S.lanes.side === 'working')) { return null; }
    var a = arr(S.activity).filter(function (x) { return x.lane === 'side' && x.thread; })[0];
    if (a) { return a.thread; }
    var w = null;
    list.forEach(function (t) { var ms = arr(t.messages); if (ms.length && ms[ms.length - 1].who === 'you') { w = t.id; } });
    return w;
  }
  function tailNodes() {
    var out = [];
    if (S.lanes && S.lanes.main === 'working') {
      var a = arr(S.activity).filter(function (x) { return x.lane === 'main'; })[0];
      var s = a && a.step ? stepById(a.step) : null;
      var w = el('div', 'fa-working'), bar = el('div', 'fah-working');
      var text = (s ? label(s) + ': ' : '') + ((a && a.text) || 'Working');
      bar.setAttribute('role', 'status'); bar.setAttribute('aria-label', text);
      add(w, bar, text); out.push(w);
    }
    if (S.phase === 'interview' && S.waiting && S.waiting.kind === 'message') {
      out.push(add(el('div'), linkBtn('Propose the plan now', function () { act('wrap'); })));
    }
    if (S.error) { out.push(el('p', 'fah-msg fa-muted fa-noanim', 'That did not finish: ' + S.error)); }
    return out;
  }
  function drawPanel(force) {
    var T = trunk(), chat = arr(S.chat), list = arr(threads());
    var sig = JSON.stringify([S.chat, S.history, S.threads, S.activity, S.lanes, S.waiting, S.phase, S.layers, S.error, S.inputs,
      steps().map(function (s) { return [s.id, s.number, s.name, s.kind, (s.runs || []).length]; }), ui.draft, ui.showEarlier]);
    if (sig === panelSig && !force) { return; }
    panelSig = sig;
    var log = $('log'), stick = first || nearBottom(), top = log.scrollTop;
    var ae = document.activeElement, focusKey = ui.focusKey || (ae && ae.getAttribute && ae.getAttribute('data-key')), caret = ae && ae.selectionStart;
    ui.focusKey = null;

    /* a side message that opened a new branch: open it and keep typing there */
    if (ui.knownThreads && ui.wantNewThread) {
      list.forEach(function (t) { if (!ui.knownThreads[t.id]) { ui.branchOpen[t.id] = true; ui.openThread = t.id; ui.wantNewThread = false; focusKey = 'reply:' + t.id; } });
    }
    ui.knownThreads = {}; list.forEach(function (t) { ui.knownThreads[t.id] = true; });

    var lastPlan = -1; chat.forEach(function (m, i) { if (m.kind === 'plan') { lastPlan = i; } });
    var waitingPlan = S.waiting && S.waiting.kind === 'plan';
    var fresh = [], firstDraw = seenMsgs === null; seenMsgs = seenMsgs || {};
    function render(m, holder) {
      var i = chat.indexOf(m);
      messageNodes(m, { acceptHere: i === lastPlan && waitingPlan }).forEach(function (n) {
        if (firstDraw || seenMsgs[m.id]) { n.classList.add('fa-noanim'); }
        holder.appendChild(n);
      });
      if (!seenMsgs[m.id] && !firstDraw) { fresh.push(m); }
      seenMsgs[m.id] = true;
    }
    var workingIn = workingThread(list), lastOpenSide = null;
    list.forEach(function (t) { if (t.kind === 'side' && outcome(t) === 'open') { lastOpenSide = t.id; } });
    function ctxOf(t) {
      var oc = outcome(t);
      return { working: workingIn === t.id, defaultOpen: oc === 'open' && (!!pendingOf(t) || workingIn === t.id || t.id === ui.openThread || t.id === lastOpenSide) };
    }

    var before = $('before'), bmsgs = $('beforemsgs'), graph = $('graph'), convo = $('convo'), foot = $('foot');
    bmsgs.textContent = ''; convo.textContent = ''; foot.textContent = '';
    if (graphRO) { graphRO.disconnect(); graphRO = null; }

    if (!T.length) {
      /* no decision yet (before "Plan accepted", or a layer that records none): a plain conversation,
         with any branch right after the message it follows */
      show(before, false); show(graph, false); graphRows = []; graph.textContent = '';
      var lastAt = {};
      chat.forEach(function (m) { var h = el('div', 'fah-chat'); render(m, h); convo.appendChild(h); lastAt[m.id] = h; });
      list.forEach(function (t) {
        var b = add(el('div', 'fa-loose'), branchEl(t, ctxOf(t)));
        var host = t.after && lastAt[t.after];
        if (host) { host.after(b); lastAt[t.after] = b; } else { convo.appendChild(b); }
      });
      if (ui.draft) { convo.appendChild(add(el('div', 'fa-loose'), draftEl())); }
      var tl = tailNodes(); if (tl.length) { var tw = el('div', 'fah-chat'); tl.forEach(function (n) { tw.appendChild(n); }); convo.appendChild(tw); }
      Array.prototype.forEach.call(convo.children, function (c, i) { if (i) { c.style.marginTop = '14px'; } });
    } else {
      var cut = T[0].after ? chat.map(function (m) { return m.id; }).indexOf(T[0].after) : -1;
      var pre = chat.slice(0, cut + 1);
      var joinMsgs = {};
      T.forEach(function (n) { var jm = joinMessageOf(n.id); if (jm && jm.who === 'harness') { joinMsgs[jm.id] = true; } });
      var post = chat.slice(cut + 1).filter(function (m) { return !joinMsgs[m.id]; });
      /* the interview, folded: the trunk starts at "Plan accepted" */
      show(before, pre.length > 0);
      $('beforesum').textContent = 'How the plan was made · ' + pre.length + (pre.length === 1 ? ' message' : ' messages');
      pre.forEach(function (m) { render(m, bmsgs); });
      /* the graph */
      show(graph, true);
      buildGraph(graph, T, list, ctxOf);
      /* the foot: the latest exchange; anything still waiting on the person stays in it */
      var start = -1;
      post.forEach(function (m, i) { if (m.who === 'you') { start = i; } });
      if (start < 0) { start = 0; }
      post.forEach(function (m, i) {
        var waits = (m.decision && m.decision.status === 'open') || (m.notice && m.notice.status === 'open');
        if (i < start && waits && layerOn(4)) { start = i; }
      });
      if (start <= 2) { start = 0; }      /* fold only when there is something to fold */
      var earlier = post.slice(0, start), latest = post.slice(start);
      if (earlier.length) {
        var lk = linkBtn(ui.showEarlier ? 'Hide earlier messages' : 'Earlier in the chat · ' + earlier.length, function () { ui.showEarlier = !ui.showEarlier; drawPanel(true); });
        lk.classList.add('fa-earlier'); lk.setAttribute('aria-expanded', String(ui.showEarlier)); foot.appendChild(lk);
        if (ui.showEarlier) { earlier.forEach(function (m) { render(m, foot); }); }
        else { earlier.forEach(function (m) { seenMsgs[m.id] = true; }); }
      }
      latest.forEach(function (m) { render(m, foot); });
      tailNodes().forEach(function (n) { foot.appendChild(n); });
    }
    if (fresh.length) { var lm = fresh[fresh.length - 1]; $('live').textContent = (WHO[lm.who] || '') + ': ' + (lm.text || ''); }

    /* keep what the person was doing */
    if (focusKey) {
      var f = document.querySelector('[data-key="' + focusKey + '"]');
      if (f) { f.focus({ preventScroll: true }); if (typeof caret === 'number' && f.value) { try { f.setSelectionRange(caret, caret); } catch (e) { /* not a text field */ } } }
    }
    if (stick) { toBottom(); } else { log.scrollTop = top; }
    var j = joinAnim; joinAnim = null;
    var drawn = drawGraph(j);
    if (j) {
      var card = graph.querySelector('[data-node="' + j + '"]');
      var focusIt = !ae || ae === document.body || log.contains(ae) || !document.contains(ae);
      if (card) { card.scrollIntoView({ block: 'nearest', behavior: smooth() }); }
      F.join({ line: drawn.line, mark: drawn.mark, card: card, tags: ui.joinTags || [], focus: focusIt && card ? card.querySelector('.dg-node__title') : null });
      ui.joinTags = [];
    } else { graph.classList.add('dg-still'); }
    if (j) { graph.classList.remove('dg-still'); }
    if (!graph.hidden && window.ResizeObserver) {
      var firstObs = true;
      graphRO = new ResizeObserver(function () { if (firstObs) { firstObs = false; return; } drawGraph(null); });
      graphRO.observe(graph);
    }
  }
  function nearBottom() { var l = $('log'); return l.scrollHeight - l.scrollTop - l.clientHeight < 80; }
  function toBottom() { var l = $('log'); if (l.scrollHeight > l.clientHeight) { l.scrollTop = l.scrollHeight; } }
  /* A branch that was open is joined now: the next draw plays the join (motion.md). */
  function detectJoin() {
    arr(threads()).forEach(function (t) {
      var oc = outcome(t);
      if (!first && prevOutcome[t.id] && prevOutcome[t.id] !== 'joined' && oc === 'joined' && t.node) { joinAnim = t.node; }
      if (prevOutcome[t.id] === 'open' && oc !== 'open') { delete ui.branchOpen[t.id]; if (ui.openThread === t.id) { ui.openThread = null; } }   /* ended: fold it */
      prevOutcome[t.id] = oc;
    });
  }

  /* ---------- the composer at the foot: the main conversation, or a new branch ---------- */
  function setSide(on) {
    ui.side = !!on;
    sideBtn.setAttribute('aria-pressed', String(ui.side));
    composer.classList.toggle('fah-composer--side', ui.side);
  }
  function drawComposer() {
    var canSide = !!S && layerOn(4);
    show(sideBtn, canSide);
    if (!canSide && ui.side) { setSide(false); }
    var old = composer.querySelector('.fa-chiprow'); if (old) { old.remove(); }
    var text = null, aria = '';
    if (ui.attached && stepById(ui.attached)) { text = label(stepById(ui.attached)); aria = 'Remove step ' + text; }
    else { ui.attached = null; ui.notice = null; }
    if (text) {
      var c = el('button', 'fah-chip', text + ' ✕'); c.type = 'button'; c.setAttribute('aria-label', aria);
      c.addEventListener('click', function () { ui.attached = null; ui.notice = null; drawComposer(); input.focus(); });
      composer.insertBefore(add(el('div', 'fa-chiprow'), c), input);
    }
    composer.classList.toggle('fa-has-chip', !!text);
    var ph, decisionOpen = S && S.waiting && S.waiting.kind === 'decision';
    if (ui.notice) { ph = 'Say what is different…'; }
    else if (ui.side) { ph = ui.attached ? 'Start a branch about this…' : 'Start a branch…'; }
    else if (decisionOpen) { ph = '…or answer in your own words'; }
    else if (ui.attached) { ph = 'Say what should change…'; }
    else if (!S || S.phase === 'empty' || !steps().length) { ph = S && S.phase === 'interview' ? 'Answer, or add anything…' : 'Say what you want to plan…'; }
    else { ph = 'Ask, or click a step…'; }
    input.placeholder = ph;
    input.setAttribute('aria-label', ui.side ? 'Start a branch' : ui.attached ? 'Message about step ' + label(stepById(ui.attached)) : 'Message');
  }
  function send() {
    var text = input.value.trim(); if (!text) { return; }
    var p;
    if (ui.side) {
      var body = { text: text, subject: ui.attached ? { kind: 'step', step: ui.attached } : { kind: 'plan' } };
      if (ui.attached) { body.step = ui.attached; }
      ui.wantNewThread = true; p = act('side', body);
    } else {
      var b2 = { text: text }; if (ui.attached) { b2.step = ui.attached; } if (ui.notice) { b2.notice = ui.notice; }
      p = act('say', b2);
    }
    input.value = '';
    p.then(function (ok) {
      if (!ok) { if (!input.value) { input.value = text; } return; }
      ui.attached = null; ui.notice = null; setSide(false); drawComposer();
      if (ui.selected && !ui.pop) { F.select(null, document); ui.selected = null; }   /* the step went with the message */
    });
  }
  input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); send(); } });
  sideBtn.addEventListener('click', function () { var on = F.sideToggle(sideBtn); ui.side = on; drawComposer(); input.focus(); });

  /* ---------- empty plan ---------- */
  function drawEmpty() {
    var e = $('empty'), none = !steps().length;
    show(e, none); show(scroller, !none); e.textContent = '';
    if (!none) { return; }
    if (S.phase === 'interview') { e.appendChild(el('p', null, 'The assistant is asking what it needs. The plan appears here as steps once it has enough.')); }
    else if (S.phase === 'proposed' || S.phase === 'accepted') { e.appendChild(el('p', null, 'The plan has no steps yet.')); }
    else { e.appendChild(el('p', null, 'Say in the chat what you want to plan. The plan appears here as steps you can check, build and ask about.')); }
  }

  /* ---------- one draw from the state document ---------- */
  function draw() {
    try {
      detectJoin();
      drawTop();
      drawEmpty();
      drawDiagram();
      drawWhole();
      drawReviewList();
      drawPanel();
      drawComposer();
      if (ui.pop) { refreshPop(); }
      if (first) {
        var ny = steps().filter(function (s) { return s.needs_you; })[0];
        if (ny && stepEls[ny.id]) { scroller.scrollLeft = Math.max(0, lay.pos[ny.id].x - 40); }
      }
    } catch (err) {
      if (window.console) { console.error(err); }
    }
    first = false;
  }

  /* ---------- page-level keys and clicks ---------- */
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && ui.pop) { ev.preventDefault(); closePop(true); }
    else if (ev.key === 'Escape' && (ui.selInput || ui.markNode)) { ui.selInput = null; ui.markNode = null; markPills(); drawDiagram(); markNodeSel(); }
  });
  document.addEventListener('click', function (ev) {
    if (ui.pop && popEl && !popEl.contains(ev.target)) { closePop(false); }
  });
  var resizeTimer = null;
  window.addEventListener('resize', function () { clearTimeout(resizeTimer); resizeTimer = setTimeout(function () { if (S) { drawDiagram(); placePop(); drawGraph(null); } }, 120); });

  drawComposer();
  poll();
})();
