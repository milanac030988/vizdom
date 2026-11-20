/* Interactive diagrams of the docs site (system overview, component diagrams).
 *
 * Every <div class="vz-fig"> gets a toolbar: zoom out / in, the zoom step, and
 * "Full window". In the full window the diagram opens fitted to the window; a
 * click on a component that has its own diagram on this page switches to that
 * diagram, "Overview" returns to the first diagram of the page, Esc closes.
 * Without this script the figures still show at full width and their links work.
 */
(function () {
  "use strict";

  var STEPS = [1, 1.5, 2, 3];
  var figs = [];
  var open = null; // the figure shown in the full window

  function ratio(obj) {
    var m = /aspect-ratio:\s*([\d.]+)\s*\/\s*([\d.]+)/.exec(obj.getAttribute("style") || "");
    return m ? parseFloat(m[1]) / parseFloat(m[2]) : 1.5;
  }

  function headingBefore(el) {
    var hs = document.querySelectorAll(".rst-content h1, .rst-content h2, .rst-content h3, main h1, main h2, main h3");
    var found = null;
    for (var i = 0; i < hs.length; i++) {
      if (hs[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) found = hs[i];
    }
    return found;
  }

  function button(label, title, cls) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "vz-btn " + (cls || "");
    b.textContent = label;
    b.title = title;
    return b;
  }

  function layout(f) {
    var obj = f.obj;
    var k = STEPS[f.step];
    if (f.el.classList.contains("vz-full")) {
      var box = f.scroll.getBoundingClientRect();
      var fit = Math.min(box.width - 24, (box.height - 24) * f.ratio);
      obj.style.width = Math.max(200, Math.floor(fit * k)) + "px";
    } else {
      // fitted: as wide as the page allows, but never taller than the scroll
      // area (85vh), so the whole diagram is visible without a scrollbar
      var maxH = window.innerHeight * 0.85 - 4;
      var w = Math.min(f.scroll.clientWidth, maxH * f.ratio);
      obj.style.width = Math.max(200, Math.floor(w * k)) + "px";
    }
    f.pct.textContent = Math.round(100 * k) + "%";
  }

  function setFull(f, on, scrollBack) {
    if (on) {
      if (open && open !== f) setFull(open, false, false);
      f.el.classList.add("vz-full");
      document.documentElement.classList.add("vz-noscroll");
      f.step = 0;
      open = f;
      f.fullBtn.textContent = "Close";
      f.fullBtn.title = "Close the full window (Esc)";
      f.back.hidden = f === figs[0] || !f.overviewOnPage;
      f.fullBtn.focus({ preventScroll: true });
    } else {
      f.el.classList.remove("vz-full");
      document.documentElement.classList.remove("vz-noscroll");
      if (open === f) open = null;
      f.step = 0;
      f.fullBtn.textContent = "Full window";
      f.fullBtn.title = "Show the diagram in the whole window";
      if (scrollBack && f.heading) f.heading.scrollIntoView({ block: "start" });
    }
    layout(f);
  }

  function figureAfter(target) {
    // the first figure of the section that starts at this heading
    for (var i = 0; i < figs.length; i++) {
      if (figs[i].heading === target) return figs[i];
    }
    return null;
  }

  function onHash() {
    if (!open) return;
    var id = decodeURIComponent(location.hash.slice(1));
    var target = id && document.getElementById(id);
    var f = target && figureAfter(target);
    if (f && f !== open) setFull(f, true);
    else if (!f) setFull(open, false, false);
  }

  function init(el, index) {
    var scroll = el.querySelector(".vz-scroll");
    var obj = el.querySelector("object, img");
    if (!scroll || !obj) return;
    var heading = headingBefore(el);
    var bar = document.createElement("div");
    bar.className = "vz-bar";
    var title = document.createElement("span");
    title.className = "vz-title";
    title.textContent = heading ? heading.textContent.replace(/¶\s*$/, "").trim() : "Diagram";
    var back = button("← Overview", "Back to the overview diagram", "vz-back");
    var out = button("−", "Zoom out");
    var pct = document.createElement("span");
    pct.className = "vz-pct";
    var inn = button("+", "Zoom in");
    var fit = button("Fit", "Fit the whole diagram in the window", "vz-fit");
    var fullBtn = button("Full window", "Show the diagram in the whole window", "vz-primary");
    bar.append(title, back, out, pct, inn, fit, fullBtn);
    el.insertBefore(bar, scroll);

    var f = { el: el, scroll: scroll, obj: obj, ratio: ratio(obj), step: 0, pct: pct,
              fullBtn: fullBtn, back: back, heading: heading, overviewOnPage: index > 0 };
    back.hidden = true;
    out.addEventListener("click", function () { if (f.step > 0) { f.step--; layout(f); } });
    inn.addEventListener("click", function () { if (f.step < STEPS.length - 1) { f.step++; layout(f); } });
    fit.addEventListener("click", function () { f.step = 0; layout(f); });
    fullBtn.addEventListener("click", function () { setFull(f, !el.classList.contains("vz-full"), true); });
    back.addEventListener("click", function () { setFull(figs[0], true); });
    figs.push(f);
    layout(f);
  }

  function start() {
    var els = document.querySelectorAll(".vz-fig");
    for (var i = 0; i < els.length; i++) init(els[i], i);
    for (var j = 0; j < figs.length; j++) figs[j].overviewOnPage = figs.length > 1;
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && open) setFull(open, false, true);
    });
    window.addEventListener("resize", function () {
      for (var i = 0; i < figs.length; i++) layout(figs[i]);
    });
    window.addEventListener("hashchange", onHash);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
