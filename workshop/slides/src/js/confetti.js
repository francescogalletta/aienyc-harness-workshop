/* Confetti burst from an element (used when the framework reaches Trust).
   Colours come from the --confetti-colors token. Respects reduced motion.
   stillHere() says whether the slide that fired it is still the current one. */
function confetti(el, stage, stillHere) {
  if (!el || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  var W = 1920, H = 1080;
  var old = stage.querySelector('canvas.confetti'); if (old) old.remove();
  var c = document.createElement('canvas'); c.className = 'confetti'; c.width = W; c.height = H;
  stage.appendChild(c);
  var ctx = c.getContext('2d'), cs = getComputedStyle(document.documentElement);
  var cols = cs.getPropertyValue('--confetti-colors').split(',').map(function (v) { return v.trim(); }).filter(Boolean);
  if (!cols.length) cols = [cs.color];
  var sr = stage.getBoundingClientRect(), r = el.getBoundingClientRect(), k = W / sr.width;
  var ox = (r.left + r.width / 2 - sr.left) * k, oy = (r.top + r.height / 2 - sr.top) * k;
  var parts = [], i;
  for (i = 0; i < 220; i++) {
    var ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.5, sp = 9 + Math.random() * 24;
    parts.push({ x: ox + (Math.random() - 0.5) * r.width * k * 0.8, y: oy, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp - 4,
      w: 12 + Math.random() * 16, h: 8 + Math.random() * 10, rot: Math.random() * 6.28, vr: (Math.random() - 0.5) * 0.5,
      col: cols[i % cols.length], round: Math.random() < 0.25 });
  }
  var t0 = performance.now();
  (function frame(now) {
    var t = (now - t0) / 2600;
    ctx.clearRect(0, 0, W, H);
    if (t >= 1 || !stillHere() || !c.isConnected) { c.remove(); return; }
    parts.forEach(function (q) {
      q.vy += 0.55; q.vx *= 0.99; q.x += q.vx; q.y += q.vy; q.rot += q.vr;
      ctx.save(); ctx.globalAlpha = t < 0.7 ? 1 : (1 - t) / 0.3; ctx.translate(q.x, q.y); ctx.rotate(q.rot);
      ctx.fillStyle = q.col;
      if (q.round) { ctx.beginPath(); ctx.arc(0, 0, q.h * 0.7, 0, 6.3); ctx.fill(); }
      else ctx.fillRect(-q.w / 2, -q.h / 2 * Math.cos(q.rot * 2), q.w, q.h * Math.cos(q.rot * 2));
      ctx.restore();
    });
    requestAnimationFrame(frame);
  })(t0);
}
