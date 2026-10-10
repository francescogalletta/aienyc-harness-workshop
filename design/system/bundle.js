/* @ds-bundle: {"format":4,"namespace":"FAH","components":[{"name":"Screen"},{"name":"Step"},{"name":"Pill"},{"name":"Flow"},{"name":"Message"},{"name":"Thread"},{"name":"Decision"},{"name":"Notice"},{"name":"Composer"},{"name":"Button"},{"name":"Popover"}]} */
/* Financial Advisor Harness: motion and state helpers. Plain script, no dependencies.
   Everything here only adds or removes classes from bundle.css; the markup is yours. */
(function () {
  'use strict';
  var SVG = 'http://www.w3.org/2000/svg';

  function restart(el, cls) {
    el.classList.remove(cls);
    void el.getBoundingClientRect();
    el.classList.add(cls);
  }

  function wait(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  /* The tick drawn in front of a "tested" line. */
  function tick() {
    var svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('class', 'fah-step__tick');
    svg.setAttribute('viewBox', '0 0 12 12');
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(SVG, 'path');
    path.setAttribute('d', 'M2 6.5l2.5 2.5L10 3.5');
    svg.appendChild(path);
    return svg;
  }

  /* Set or replace a step's second line and play its arrival.
     kind: undefined | 'tested' | 'result' | 'strong'. text is put in as text, never HTML. */
  function setLine(step, text, kind) {
    var line = step.querySelector('.fah-step__line');
    if (!text) {
      if (line) { line.remove(); }
      return null;
    }
    if (!line) {
      line = document.createElement('span');
      step.appendChild(line);
    }
    line.className = 'fah-step__line' + (kind === 'result' ? ' fah-step__line--result' : kind === 'strong' ? ' fah-step__line--strong' : '');
    line.textContent = '';
    if (kind === 'tested') { line.appendChild(tick()); }
    line.appendChild(document.createTextNode(text));
    restart(step, 'is-arriving');
    return line;
  }

  /* Mark the one step that is waiting on the person. The ring plays once each time it is set. */
  function needsYou(step, on) {
    step.classList.toggle('fah-step--needs-you', on !== false);
  }

  /* Select one step; every other step under root loses the selection. */
  function select(step, root) {
    var all = (root || document).querySelectorAll('.fah-step--selected');
    for (var i = 0; i < all.length; i++) { all[i].classList.remove('fah-step--selected'); }
    if (step) { step.classList.add('fah-step--selected'); }
  }

  function fade(step, on) {
    step.classList.toggle('fah-step--faded', on !== false);
  }

  /* Send one pulse along each line in turn. lines: .fah-flow elements in the order the value travels.
     Returns a promise that resolves when the last pulse has landed. */
  function flow(lines, gapMs) {
    var gap = gapMs == null ? 380 : gapMs;
    var chain = Promise.resolve();
    Array.prototype.forEach.call(lines, function (line) {
      chain = chain.then(function () { restart(line, 'is-flowing'); return wait(gap); });
    });
    return chain;
  }

  /* A number in the chat was clicked: mark it and select the step that produced it. */
  function trace(num, step, root) {
    var marked = (root || document).querySelectorAll('.fah-num.is-traced');
    for (var i = 0; i < marked.length; i++) { marked[i].classList.remove('is-traced'); }
    if (num) { num.classList.add('is-traced'); }
    select(step, root);
    if (step && step.scrollIntoView) { step.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
  }

  /* Flip the "On the side" toggle inside a composer. Returns true when side mode is on. */
  function sideToggle(button) {
    var on = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(on));
    var box = button.closest('.fah-composer');
    if (box) { box.classList.toggle('fah-composer--side', on); }
    return on;
  }

  window.FAH = {
    tick: tick, setLine: setLine, needsYou: needsYou, select: select, fade: fade,
    flow: flow, trace: trace, sideToggle: sideToggle, restart: restart, wait: wait
  };
})();
