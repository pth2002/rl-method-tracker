(function () {
  "use strict";
  var D = window.TRACKER;
  if (!D) return;

  var NS = "http://www.w3.org/2000/svg";
  var REPO = D.repo;
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function $(id) { return document.getElementById(id); }
  function fmt(n) { return Number(n).toLocaleString("en-US"); }
  function monthName(m) { var p = m.split("-"); return MON[+p[1] - 1] + " " + p[0]; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function svgEl(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function listJoin(xs) {
    if (xs.length < 2) return xs.join("");
    return xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1];
  }

  /* ---------- counts in the headline ---------- */
  document.querySelectorAll("[data-count]").forEach(function (n) {
    n.textContent = fmt(D.counts[n.getAttribute("data-count")]);
  });
  $("fws").innerHTML = "Frameworks: " + D.frameworks.map(function (f, i) {
    return "<b>" + esc(f) + "</b>" + (i < D.frameworks.length - 1 ? "&nbsp;&middot;" : "");
  }).join(" ");

  var q = D.quarterly;
  if (q && q.length) {
    var inc = q.map(function (x) { return x.included_180; });
    $("cohort").innerHTML = "Counted in quarterly cohorts, the papers grew from <strong>" + fmt(q[0].general) +
      "</strong> to <strong>" + fmt(q[q.length - 1].general) + "</strong> a quarter. The number a framework included within 180 days stayed between <strong>" +
      Math.min.apply(null, inc) + "</strong> and <strong>" + Math.max.apply(null, inc) + "</strong>.";
  }

  /* ---------- the dot field ---------- */
  var field = $("field"), svg = $("dots"), tip = $("tip"), status = $("status");
  var months = Array.from(new Set(D.papers.map(function (p) { return p[1]; }))).sort();
  var cols = months.map(function (m) {
    return D.papers.filter(function (p) { return p[1] === m; }).sort(function (a, b) {
      return (b[3] - a[3]) || (a[0] < b[0] ? -1 : 1);
    });
  });
  var maxN = Math.max.apply(null, cols.map(function (c) { return c.length; }));
  var geo = null, played = false, pinned = null, ring = null, colhi = null;
  var defaultStatus = monthName(months[0]) + " to " + monthName(months[months.length - 1]) + ": " +
    fmt(D.counts.general) + " papers, " + D.counts.included + " reached a framework";

  function geometry(W) {
    var k = W >= 880 ? 6 : (W >= 640 ? 5 : (W >= 440 ? 4 : 3));
    var gap = W >= 640 ? 1.6 : 1.15;
    var pitch = W / (months.length * k + (months.length - 1) * gap);
    var H = Math.ceil(maxN / k) * pitch;
    return { W: W, k: k, pitch: pitch, colW: (k + gap) * pitch, H: H, axis: 36 };
  }
  function dotPos(g, c, j) {
    return [c * g.colW + (j % g.k + 0.5) * g.pitch, g.H - (Math.floor(j / g.k) + 0.5) * g.pitch];
  }
  function removals(p) {
    return p[6].map(function (x) { return "Removed from " + x[0] + " on " + x[1]; });
  }
  function paperLabel(p) {
    var parts = [p[2], "arXiv " + p[0] + ", " + monthName(p[1])];
    if (p[4].length) parts.push("In " + listJoin(p[4]));
    return parts.concat(removals(p)).join(". ") + ".";
  }

  function draw() {
    var W = Math.floor(field.clientWidth);
    if (!W) return;
    var g = geometry(W);
    geo = g;
    var Ht = g.H + g.axis;
    svg.setAttribute("viewBox", "0 0 " + W + " " + Ht);
    svg.setAttribute("height", Ht);
    svg.textContent = "";
    var r = Math.max(1.3, g.pitch * 0.36);
    var animate = !played && !reduceMotion;

    colhi = svgEl("rect", { "class": "colhi", x: 0, y: 0, width: g.k * g.pitch, height: g.H, rx: 2, visibility: "hidden" });
    svg.appendChild(colhi);
    var grey = svgEl("g", { "aria-hidden": "true" }), lit = svgEl("g", {});
    var litIndex = 0;
    cols.forEach(function (col, c) {
      col.forEach(function (p, j) {
        var xy = dotPos(g, c, j);
        var cls = p[3] ? (p[4].length ? "dot on" : "dot on gone") : "dot";
        var dot = svgEl("circle", { cx: xy[0].toFixed(2), cy: xy[1].toFixed(2), r: r.toFixed(2), "class": cls });
        if (animate) {
          dot.style.transitionDelay = (c * 34 + Math.floor(j / g.k) * 5) + "ms" +
            (p[3] ? ", " + (1150 + litIndex * 26) + "ms" : "");
        }
        if (p[3]) {
          litIndex += 1;
          var a = svgEl("a", { href: "https://arxiv.org/abs/" + p[0], target: "_blank", rel: "noopener", "aria-label": paperLabel(p), "data-c": c, "data-j": j });
          a.appendChild(dot);
          lit.appendChild(a);
        } else {
          grey.appendChild(dot);
        }
      });
    });
    svg.appendChild(grey);
    svg.appendChild(lit);

    var axis = svgEl("g", { "aria-hidden": "true" });
    axis.appendChild(svgEl("line", { "class": "base", x1: 0, x2: W, y1: g.H + 4.5, y2: g.H + 4.5 }));
    months.forEach(function (m, c) {
      var x = c * g.colW + g.k * g.pitch / 2;
      var t = svgEl("text", { "class": "ax", x: x.toFixed(1), y: g.H + 18, "text-anchor": "middle" });
      t.textContent = W >= 560 ? MON[+m.slice(5) - 1] : MON[+m.slice(5) - 1].charAt(0);
      axis.appendChild(t);
      if (c === 0 || m.slice(5) === "01") {
        var y = svgEl("text", { "class": "ax yr", x: (c * g.colW).toFixed(1), y: g.H + 33 });
        y.textContent = m.slice(0, 4);
        axis.appendChild(y);
      }
    });
    svg.appendChild(axis);
    ring = svgEl("circle", { "class": "ring", r: (r + 2.5).toFixed(2), visibility: "hidden" });
    svg.appendChild(ring);

    if (animate) {
      played = true;
      svg.classList.add("pre", "pre-lit");
      svg.getBoundingClientRect();
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { svg.classList.remove("pre", "pre-lit"); });
      });
    }
  }

  function hit(clientX, clientY) {
    var g = geo;
    if (!g) return null;
    var rect = svg.getBoundingClientRect();
    var x = clientX - rect.left, y = clientY - rect.top;
    var c = Math.floor(x / g.colW);
    if (c < 0 || c >= cols.length || y < 0 || y > g.H + g.axis) return null;
    var lx = x - c * g.colW;
    if (lx > g.k * g.pitch) return { c: c, j: -1 };
    var row = Math.floor((g.H - y) / g.pitch);
    if (row < 0) return { c: c, j: -1 };
    var j = row * g.k + Math.floor(lx / g.pitch);
    return { c: c, j: j < cols[c].length ? j : -1 };
  }

  function showColumn(c) {
    if (c == null) { colhi.setAttribute("visibility", "hidden"); status.textContent = defaultStatus; return; }
    var col = cols[c], n = col.filter(function (p) { return p[3]; }).length;
    colhi.setAttribute("x", (c * geo.colW - 2).toFixed(1));
    colhi.setAttribute("width", (geo.k * geo.pitch + 4).toFixed(1));
    colhi.setAttribute("visibility", "visible");
    status.textContent = monthName(months[c]) + ": " + fmt(col.length) + " papers, " + n + " reached a framework";
  }

  function showTip(c, j, withLink) {
    var p = cols[c][j], g = geo;
    var xy = dotPos(g, c, j);
    ring.setAttribute("cx", xy[0].toFixed(2));
    ring.setAttribute("cy", xy[1].toFixed(2));
    ring.setAttribute("visibility", "visible");
    var html = '<p class="t-meta">arXiv ' + esc(p[0]) + " &middot; " + monthName(p[1]) + "</p>" +
      '<p class="t-title">' + esc(p[2]) + "</p>";
    if (p[3]) {
      if (p[4].length) html += '<p class="t-in">' + (p[5].length ? esc(listJoin(p[5])) + " in " : "In ") + esc(listJoin(p[4])) + "</p>";
      else if (p[5].length) html += '<p class="t-in t-name">' + esc(listJoin(p[5])) + "</p>";
      removals(p).forEach(function (t) { html += '<p class="t-gone">' + esc(t) + "</p>"; });
    } else {
      html += '<p class="t-out">Not in any of the seven frameworks</p>';
    }
    if (withLink) html += '<a class="t-open" href="https://arxiv.org/abs/' + esc(p[0]) + '" target="_blank" rel="noopener">Open on arXiv</a>';
    tip.innerHTML = html;
    tip.hidden = false;
    tip.classList.toggle("pinned", !!withLink);
    var tw = tip.offsetWidth, th = tip.offsetHeight, W = field.clientWidth;
    var left = Math.min(Math.max(0, xy[0] - tw / 2), W - tw);
    var top = xy[1] - th - 14;
    if (top < -40) top = xy[1] + 16;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip() {
    tip.hidden = true;
    tip.classList.remove("pinned");
    if (ring) ring.setAttribute("visibility", "hidden");
  }

  svg.addEventListener("pointermove", function (e) {
    if (e.pointerType !== "mouse" || pinned) return;
    var h = hit(e.clientX, e.clientY);
    if (!h) { showColumn(null); hideTip(); svg.style.cursor = "default"; return; }
    showColumn(h.c);
    if (h.j >= 0) { showTip(h.c, h.j, false); svg.style.cursor = "pointer"; }
    else { hideTip(); svg.style.cursor = "default"; }
  });
  svg.addEventListener("pointerleave", function (e) {
    if (e.pointerType !== "mouse" || pinned) return;
    showColumn(null); hideTip();
  });
  svg.addEventListener("click", function (e) {
    var h = hit(e.clientX, e.clientY);
    var touch = e.pointerType ? e.pointerType !== "mouse" : matchMedia("(hover: none)").matches;
    if (touch) {
      e.preventDefault();
      if (h && h.j >= 0) { pinned = h; showColumn(h.c); showTip(h.c, h.j, true); }
      else { pinned = null; showColumn(null); hideTip(); }
      return;
    }
    if (h && h.j >= 0 && !e.target.closest("a")) {
      window.open("https://arxiv.org/abs/" + cols[h.c][h.j][0], "_blank", "noopener");
    }
  });
  document.addEventListener("click", function (e) {
    if (pinned && !field.contains(e.target)) { pinned = null; showColumn(null); hideTip(); }
  });
  svg.addEventListener("focusin", function (e) {
    var a = e.target.closest("a");
    if (!a) return;
    var c = +a.getAttribute("data-c"), j = +a.getAttribute("data-j");
    showColumn(c); showTip(c, j, false);
  });
  svg.addEventListener("focusout", function () { if (!pinned) { showColumn(null); hideTip(); } });

  status.textContent = defaultStatus;
  if (D.counts.removed) {
    $("legend-gone").hidden = false;
  }
  draw();
  var lastW = field.clientWidth, resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (Math.abs(field.clientWidth - lastW) < 1) return;
      lastW = field.clientWidth; pinned = null; hideTip(); draw();
    }, 120);
  });

  /* ---------- list of included papers ---------- */
  var incBtn = $("show-included"), incBox = $("included");
  incBtn.textContent = "List the " + D.counts.included + " included papers";
  incBtn.addEventListener("click", function () {
    var open = incBtn.getAttribute("aria-expanded") === "true";
    if (!open && !incBox.firstChild) {
      var rows = D.papers.filter(function (p) { return p[3]; }).map(function (p) {
        return "<tr><td class=\"m\">" + monthName(p[1]) + "</td><td class=\"t\"><a href=\"https://arxiv.org/abs/" + esc(p[0]) +
          "\">" + esc(p[2]) + "</a><span class=\"meth\">" + esc(p[5].join(", ")) + "</span></td><td class=\"f\">" + esc(p[4].join(", ")) +
          removals(p).map(function (t) { return "<span class=\"gone\">" + esc(t) + "</span>"; }).join("") + "</td></tr>";
      }).join("");
      incBox.innerHTML = "<div class=\"table-wrap\"><table class=\"inc-table\"><thead><tr><th>Month</th><th>Paper and method</th><th>Frameworks today</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
    }
    incBox.hidden = open;
    incBtn.setAttribute("aria-expanded", String(!open));
    incBtn.textContent = open ? "List the " + D.counts.included + " included papers" : "Hide the list";
  });

  /* ---------- methods by training failure ---------- */
  var TIERS = [
    ["default", "default", "on in a run that keeps every setting"],
    ["conditional_default", "cond. default", "on by default once a related feature is enabled"],
    ["core", "core", "a selectable algorithm in the main code path"],
    ["option", "option", "a switch that modifies the main algorithm"],
    ["experimental", "experimental", "lives in an experimental folder"],
    ["recipe", "recipe", "an example directory, often from the paper's authors"],
    ["removed", "removed", "was on the main branch and was taken out"]
  ];
  var TL = {};
  TIERS.forEach(function (t) { TL[t[0]] = t; });
  $("tiers").innerHTML = TIERS.map(function (t) {
    return "<div><dt><span class=\"chip t-" + t[0] + "\">" + t[1] + "</span></dt><dd>" + esc(t[2]) + "</dd></div>";
  }).join("");

  var list = $("fail-list"), select = $("fail-select"), panel = $("fail-panel");
  D.groups.forEach(function (gr, i) {
    var b = document.createElement("button");
    b.type = "button";
    b.id = "tab-" + gr.id;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-controls", "fail-panel");
    b.setAttribute("tabindex", "-1");
    b.innerHTML = "<span>" + esc(gr.name) + "</span><span class=\"n\">" + gr.methods.length + "</span>";
    b.addEventListener("click", function () { choose(i, true); });
    list.appendChild(b);
    var o = document.createElement("option");
    o.value = String(i);
    o.textContent = gr.name + " (" + gr.methods.length + ")";
    select.appendChild(o);
  });
  select.addEventListener("change", function () { choose(+select.value, true); });
  list.addEventListener("keydown", function (e) {
    var tabs = Array.from(list.children), i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    var next = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (next == null) return;
    e.preventDefault();
    next = (next + tabs.length) % tabs.length;
    choose(next, true);
    tabs[next].focus();
  });

  function cell(m, fk) {
    var c = m.cells[fk];
    var fw = esc(D.frameworks[D.frameworkKeys.indexOf(fk)]);
    if (!c) return "<td class=\"empty\"><span class=\"none\" aria-label=\"not in " + fw + "\">&middot;</span></td>";
    var t = TL[c.tier] || [c.tier, c.tier, ""];
    if (c.tier === "removed") {
      return "<td data-fw=\"" + fw + "\"><span class=\"chip t-removed\" title=\"Removed on " + esc(c.date) + "\">removed</span></td>";
    }
    var title = (c.setting ? c.setting + " · " : "") + t[2];
    if (c.url) return "<td data-fw=\"" + fw + "\"><a class=\"chip t-" + c.tier + "\" href=\"" + esc(c.url) + "\" title=\"" + esc(title) + "\">" + t[1] + "</a></td>";
    return "<td data-fw=\"" + fw + "\"><span class=\"chip t-" + c.tier + "\" title=\"" + esc(title) + "\">" + t[1] + "</span></td>";
  }

  function choose(i, user) {
    var gr = D.groups[i];
    Array.from(list.children).forEach(function (b, k) {
      b.setAttribute("aria-selected", String(k === i));
      b.setAttribute("tabindex", k === i ? "0" : "-1");
    });
    select.value = String(i);
    panel.setAttribute("aria-labelledby", "tab-" + gr.id);
    var head = "<th class=\"sticky\" scope=\"col\">Method</th>" + D.frameworks.map(function (f) { return "<th scope=\"col\">" + esc(f) + "</th>"; }).join("");
    var rows = gr.methods.map(function (id) {
      var m = D.methods[id];
      var cut = m.name.indexOf(" (");
      var nm = cut > 0 ? esc(m.name.slice(0, cut)) + " <span class=\"mdesc\">" + esc(m.name.slice(cut + 1)) + "</span>" : esc(m.name);
      var named = m.src ? "<a href=\"" + esc(m.src) + "\">" + nm + "</a>" : nm;
      var src = (m.arxiv ? "arXiv " + esc(m.arxiv) : "no arXiv source") + (m.date ? " · " + esc(m.date.slice(0, 7)) : "");
      return "<tr><th class=\"sticky\" scope=\"row\"><span class=\"mname\">" + named + "</span><span class=\"msrc\">" + src + "</span></th>" +
        D.frameworkKeys.map(function (fk) { return cell(m, fk); }).join("") + "</tr>";
    }).join("");
    panel.innerHTML = "<h3>" + esc(gr.name) + "</h3><p class=\"observe\">" + esc(gr.observe) + "</p>" +
      "<div class=\"table-wrap\"><table class=\"matrix\"><thead><tr>" + head + "</tr></thead><tbody>" + rows + "</tbody></table></div>";
    if (user && history.replaceState) history.replaceState(null, "", "#failure-" + gr.id);
  }
  function fromHash() {
    if (location.hash.indexOf("#failure-") !== 0) return -1;
    var want = location.hash.slice(9), found = -1;
    D.groups.forEach(function (gr, i) { if (gr.id === want) found = i; });
    return found;
  }
  var start = fromHash();
  choose(Math.max(start, 0), false);
  if (start >= 0) requestAnimationFrame(function () { $("failures").scrollIntoView(); });
  window.addEventListener("hashchange", function () {
    var i = fromHash();
    if (i >= 0) { choose(i, false); $("failures").scrollIntoView(); }
  });

  /* ---------- latest landings ---------- */
  $("log").innerHTML = D.landings.map(function (l) {
    var ref = /\/pull\/(\d+)/.exec(l.url);
    var refText = ref ? "PR #" + ref[1] : "commit " + l.url.split("/commit/")[1].slice(0, 7);
    var lag = l.days === 0 ? "same day as the source" : (l.days < 0 ? fmt(-l.days) + " days before the source" : fmt(l.days) + " days after the source");
    return "<li><span class=\"node\" aria-hidden=\"true\"></span><time datetime=\"" + esc(l.date) + "\">" + esc(l.date) + "</time>" +
      "<span class=\"fw\">" + esc(l.fw) + "</span><span class=\"what\">" + esc(l.method) + "</span>" +
      "<span class=\"lag\">" + lag + "</span><a class=\"ref\" href=\"" + esc(l.url) + "\">" + refText + "</a></li>";
  }).join("");

  /* ---------- framework ledger ---------- */
  var lhead = "<thead><tr><th></th><th colspan=\"3\">Methods</th><th class=\"grp\" colspan=\"2\">Landing pull requests</th><th class=\"grp\" colspan=\"4\">Proposals for other methods</th></tr>" +
    "<tr><th scope=\"col\">Framework</th><th scope=\"col\">Included</th><th scope=\"col\">First anywhere</th><th scope=\"col\">Median days</th>" +
    "<th scope=\"col\" class=\"grp\">By a prior merger</th><th scope=\"col\">Median days open</th>" +
    "<th scope=\"col\" class=\"grp\">All</th><th scope=\"col\">Open</th><th scope=\"col\">Declined</th><th scope=\"col\">Lapsed</th></tr></thead>";
  var lrows = D.ledger.map(function (x) {
    var noPR = !x.prs;
    var guide = REPO + "/blob/main/FRAMEWORKS.md#" + x.anchor;
    return "<tr><th scope=\"row\"><a href=\"" + esc(x.url) + "\">" + esc(x.fw) + "</a><a class=\"guide\" href=\"" + esc(guide) + "\">contribution guide</a></th>" +
      "<td class=\"big\">" + x.methods + "</td><td>" + x.first + "</td><td>" + (x.median == null ? "&ndash;" : x.median) + "</td>" +
      (noPR ? "<td class=\"grp dash\">&ndash;</td><td class=\"dash\">&ndash;</td>"
            : "<td class=\"grp\">" + x.by_merger + " of " + x.prs + "</td><td>" + (x.days_open == null ? "&ndash;" : x.days_open) + "</td>") +
      "<td class=\"grp\">" + x.proposals + "</td><td>" + x.open + "</td><td>" + x.declined + "</td><td>" + x.lapsed + "</td></tr>";
  }).join("");
  $("ledger").innerHTML = lhead + "<tbody>" + lrows + "</tbody>";

  /* ---------- footer and citation ---------- */
  $("snapshots").innerHTML = D.snapshots.map(function (s) {
    return "<li><span>" + esc(s[0]) + "</span> " + esc(s[1]) + " &middot; " + esc(s[2]) + "</li>";
  }).join("");
  $("copy-bib").addEventListener("click", function () {
    var text = $("bibtex").textContent, done = function () {
      $("copied").textContent = "Copied";
      setTimeout(function () { $("copied").textContent = ""; }, 2000);
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, function () {});
    else {
      var r = document.createRange(); r.selectNodeContents($("bibtex"));
      var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
      try { document.execCommand("copy"); done(); } catch (err) { /* selection stays for manual copy */ }
    }
  });
})();
