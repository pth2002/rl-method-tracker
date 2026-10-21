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
          var a = svgEl("a", { href: "#paper-" + p[0], "aria-label": paperLabel(p), "data-c": c, "data-j": j });
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
    if (withLink) html += '<a class="t-open" href="#paper-' + esc(p[0]) + '">Open the paper page</a>';
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
    if (h && h.j >= 0 && !e.target.closest("a")) location.hash = "#paper-" + cols[h.c][h.j][0];
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
        var meths = p[5].map(function (n, i) {
          return p[7] && p[7][i] ? "<a href=\"#method-" + esc(p[7][i]) + "\">" + esc(n) + "</a>" : esc(n);
        }).join(", ");
        return "<tr><td class=\"m\">" + monthName(p[1]) + "</td><td class=\"t\"><a href=\"#paper-" + esc(p[0]) +
          "\">" + esc(p[2]) + "</a><span class=\"meth\">" + meths + "</span></td><td class=\"f\">" + esc(p[4].join(", ")) +
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
      var named = "<a href=\"#method-" + esc(id) + "\">" + nm + "</a>";
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

  /* ---------- latest landings ---------- */
  $("log").innerHTML = D.landings.map(function (l) {
    var ref = /\/pull\/(\d+)/.exec(l.url);
    var refText = ref ? "PR #" + ref[1] : "commit " + l.url.split("/commit/")[1].slice(0, 7);
    var lag = l.days === 0 ? "same day as the source" : (l.days < 0 ? fmt(-l.days) + " days before the source" : fmt(l.days) + " days after the source");
    return "<li><span class=\"node\" aria-hidden=\"true\"></span><time datetime=\"" + esc(l.date) + "\">" + esc(l.date) + "</time>" +
      "<span class=\"fw\">" + esc(l.fw) + "</span><span class=\"what\">" +
      (l.id ? "<a href=\"#method-" + esc(l.id) + "\">" + esc(l.method) + "</a>" : esc(l.method)) + "</span>" +
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

  /* ---------- method and paper pages ---------- */
  var FWK = D.frameworkKeys, FWN = D.frameworks;
  var SYMPTOM = {};
  D.groups.forEach(function (g) { SYMPTOM[g.id] = g.name; });
  var PAPER = {};
  D.papers.forEach(function (p) { PAPER[p[0]] = p; });
  var detail = $("detail"), detailBody = $("detail-body"), pageTitle = document.title, lastFocus = null;

  function splitName(name) {
    var cut = name.indexOf(" (");
    return cut > 0 ? [name.slice(0, cut), name.slice(cut + 2, -1)] : [name, ""];
  }
  function refLabel(url) {
    var pr = /\/pull\/(\d+)$/.exec(url);
    return pr ? "PR #" + pr[1] : "commit " + url.split("/commit/")[1].slice(0, 7);
  }
  function lagText(c) {
    if (c.days == null) return "";
    if (c.censored) return "at most " + fmt(c.days) + " days";
    if (c.days === 0) return "same day";
    return c.days < 0 ? fmt(-c.days) + " days before" : fmt(c.days) + " days";
  }
  function shareLink(hash) {
    return location.origin + location.pathname + hash;
  }
  function actions(hash, extra) {
    return "<div class=\"d-actions\"><button class=\"btn small\" type=\"button\" data-copy=\"" + esc(shareLink(hash)) + "\">Copy link</button>" +
      extra + "<span class=\"copied\" role=\"status\"></span></div>";
  }

  function methodPage(id) {
    var m = D.methods[id], nm = splitName(m.name);
    var landed = FWK.map(function (k) { return m.cells[k] && m.cells[k].landed ? [m.cells[k].landed, k] : null; })
      .filter(Boolean).sort();
    var first = landed.length ? landed[0] : null;
    var firstCell = first ? m.cells[first[1]] : null;
    var fails = m.symptoms.length
      ? m.symptoms.map(function (s) { return "<a class=\"d-fail\" href=\"#failure-" + esc(s) + "\">" + esc(SYMPTOM[s] || s) + "</a>"; }).join(" ")
      : "<span class=\"d-muted\">A baseline or general component, not tied to one training failure.</span>";
    var rows = FWK.map(function (k, i) {
      var c = m.cells[k];
      if (!c) return "<tr class=\"d-off\"><th scope=\"row\">" + esc(FWN[i]) + "</th><td colspan=\"5\">Not included</td></tr>";
      var t = TL[c.tier] || [c.tier, c.tier, ""];
      var offered = c.tier === "removed"
        ? "<span class=\"chip t-removed\">removed</span><span class=\"d-sub\">on " + esc(c.date) + "</span>"
        : (c.url ? "<a class=\"chip t-" + esc(c.tier) + "\" href=\"" + esc(c.url) + "\" title=\"" + esc(t[2]) + "\">" + esc(t[1]) + "</a>"
                 : "<span class=\"chip t-" + esc(c.tier) + "\" title=\"" + esc(t[2]) + "\">" + esc(t[1]) + "</span>");
      var change = c.ref ? "<a href=\"" + esc(c.ref) + "\">" + esc(refLabel(c.ref)) + "</a>" +
        (c.byAuthors ? "<span class=\"d-sub\">by the paper's authors</span>" : "") +
        (c.recipe ? "<span class=\"d-sub\">in verl-recipe</span>" : "") : "";
      return "<tr><th scope=\"row\">" + esc(FWN[i]) + "</th><td data-h=\"Offered as\">" + offered + "</td>" +
        "<td data-h=\"Setting\">" + (c.setting ? "<code>" + esc(c.setting) + "</code>" : "") + "</td>" +
        "<td data-h=\"First landed\">" + (c.landed ? (c.censored ? "by " : "") + esc(c.landed) : "") + "</td>" +
        "<td data-h=\"After the source\">" + esc(lagText(c)) + "</td><td data-h=\"Change\">" + change + "</td></tr>";
    }).join("");
    var summary = "<strong>In " + m.n + " of " + FWK.length + " frameworks.</strong>" + (first
      ? " First landing: " + esc(FWN[FWK.indexOf(first[1])]) + " on " + esc(first[0]) +
        (firstCell.censored ? ", at most " : ", ") + esc(lagText(firstCell).replace("at most ", "")) +
        (firstCell.days != null && firstCell.days >= 0 ? " after the source." : ".")
      : "");
    var src = m.title ? "<a href=\"" + esc(m.src || "#") + "\">" + esc(m.title) + "</a>" : "";
    return "<p class=\"d-eyebrow\">Method</p><h2 id=\"detail-title\">" + esc(nm[0]) + "</h2>" +
      (nm[1] ? "<p class=\"d-desc\">" + esc(nm[1]) + "</p>" : "") +
      "<p class=\"d-src\">" + (src ? "Source: " + src + " &middot; " : "") +
      (m.arxiv ? "<span class=\"d-mono\">arXiv " + esc(m.arxiv) + "</span>" : "<span class=\"d-mono\">no arXiv source</span>") +
      (m.date ? " &middot; <span class=\"d-mono\">" + esc(m.date) + "</span>" : "") + "</p>" +
      "<p class=\"d-fails\">" + fails + "</p><p class=\"d-sum\">" + summary + "</p>" +
      "<div class=\"table-wrap\"><table class=\"d-table\"><thead><tr><th scope=\"col\">Framework</th><th scope=\"col\">Offered as</th>" +
      "<th scope=\"col\">Setting</th><th scope=\"col\">First landed</th><th scope=\"col\">After the source</th><th scope=\"col\">Change</th></tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div>" +
      "<p class=\"d-note\">Dates come from each framework's main branch." +
      (FWK.some(function (k) { return m.cells[k] && m.cells[k].censored; })
        ? " \"by\" marks a first sighting in a bulk release or a renamed option, so the method may have landed earlier there." : "") + "</p>" +
      actions("#method-" + id, (m.src ? "<a class=\"btn small\" href=\"" + esc(m.src) + "\">Open on arXiv</a>" : "") +
        "<a class=\"btn small\" href=\"#failures\">All methods by failure</a>");
  }

  function paperPage(arxiv) {
    var p = PAPER[arxiv];
    var head = "<p class=\"d-eyebrow\">Paper</p><h2 id=\"detail-title\" class=\"d-ptitle\">" + esc(p[2]) + "</h2>" +
      "<p class=\"d-src\"><span class=\"d-mono\">arXiv " + esc(p[0]) + " &middot; " + monthName(p[1]) + "</span></p>";
    var body;
    if (p[3]) {
      var ms = (p[7] || []).map(function (id, i) {
        var m = D.methods[id];
        return "<li><a href=\"#method-" + esc(id) + "\">" + esc(p[5][i] || id) + "</a><span class=\"d-sub\">in " +
          (m.n ? m.n + " of " + FWK.length + " frameworks" : "no framework today") + "</span></li>";
      }).join("");
      body = (p[4].length ? "<p class=\"d-status on\">Its method is on the main branch of " + esc(listJoin(p[4])) + ".</p>"
                          : "<p class=\"d-status\">Its method reached a framework and was later removed.</p>") +
        removals(p).map(function (t) { return "<p class=\"d-status gone\">" + esc(t) + ".</p>"; }).join("") +
        (ms ? "<ul class=\"d-methods\">" + ms + "</ul>" : "");
    } else {
      body = "<p class=\"d-status\">Not in any of the seven frameworks at the snapshot of " + esc(D.snapshot) + ".</p>" +
        "<p class=\"d-muted\">If you wrote this paper, the framework guide lists each framework's contribution rules, " +
        "where its RL algorithms live and what reviewers asked for in earlier proposals.</p>";
    }
    return head + body + actions("#paper-" + p[0], "<a class=\"btn small\" href=\"https://arxiv.org/abs/" + esc(p[0]) + "\">Open on arXiv</a>" +
      (p[3] ? "" : "<a class=\"btn small\" href=\"" + esc(REPO) + "/blob/main/FRAMEWORKS.md\">Framework guide</a>"));
  }

  var shown = false;
  function openDetail(html, title) {
    detailBody.innerHTML = html;
    document.title = title + " · RL Method Tracker";
    if (!detail.open) {
      lastFocus = document.activeElement;
      if (detail.showModal) detail.showModal(); else detail.setAttribute("open", "");
    }
    shown = true;
    detail.scrollTop = 0;
    detail.querySelector(".detail-inner").scrollTop = 0;
  }
  function closeDetail() {
    if (!detail.open) return;
    if (detail.close) detail.close(); else detail.removeAttribute("open");
    onClosed();
  }
  // runs once per opening: right away when the page closes the dialog, or on the close event after Escape
  function onClosed() {
    if (!shown) return;
    shown = false;
    document.title = pageTitle;
    if (/^#(method|paper)-/.test(location.hash) && history.replaceState) {
      history.replaceState(null, "", location.pathname + location.search);
    }
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  detail.addEventListener("close", onClosed);
  detail.addEventListener("click", function (e) {
    if (e.target === detail) { closeDetail(); return; }
    var b = e.target.closest("[data-copy]");
    if (b) copyText(b.getAttribute("data-copy"), b.parentNode.querySelector(".copied"));
  });
  $("detail-close").addEventListener("click", closeDetail);

  function route() {
    var h = decodeURIComponent(location.hash || "");
    if (h.indexOf("#method-") === 0 && D.methods[h.slice(8)]) {
      openDetail(methodPage(h.slice(8)), splitName(D.methods[h.slice(8)].name)[0]);
    } else if (h.indexOf("#paper-") === 0 && PAPER[h.slice(7)]) {
      openDetail(paperPage(h.slice(7)), PAPER[h.slice(7)][2]);
    } else {
      closeDetail();
      var i = fromHash();
      if (i >= 0) { choose(i, false); $("failures").scrollIntoView(); }
    }
  }
  window.addEventListener("hashchange", route);

  /* ---------- search ---------- */
  function norm(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9.+_]+/g, " ").trim(); }
  var methodIndex = Object.keys(D.methods).map(function (id) {
    var m = D.methods[id];
    var settings = FWK.map(function (k) { return m.cells[k] && m.cells[k].setting; }).filter(Boolean);
    return { id: id, name: norm(m.name), arxiv: m.arxiv || "",
             hay: norm([id.replace(/_/g, " "), m.name, m.arxiv, m.title, settings.join(" ")].join(" ")) };
  });
  var paperIndex = D.papers.map(function (p) { return { p: p, hay: norm(p[2] + " " + p[0]) }; });

  function search(text) {
    var q = norm(text);
    if (q.length < 2) return { items: [], total: 0 };
    var terms = q.split(" "), out = [], shown = {};
    methodIndex.forEach(function (x) {
      if (!terms.every(function (t) { return x.hay.indexOf(t) >= 0; })) return;
      var score = x.arxiv === q ? 0 : x.name.indexOf(q) === 0 ? 1 : x.name.indexOf(q) >= 0 ? 2 : 3;
      out.push({ kind: "method", id: x.id, score: score });
      if (x.arxiv) shown[x.arxiv] = true;
    });
    paperIndex.forEach(function (x) {
      if (shown[x.p[0]] || !terms.every(function (t) { return x.hay.indexOf(t) >= 0; })) return;
      out.push({ kind: "paper", arxiv: x.p[0], score: x.p[0] === q ? 0 : x.p[3] ? 4 : 5 });
    });
    out.sort(function (a, b) { return a.score - b.score; });
    return { items: out.slice(0, 8), total: out.length };
  }

  var qInput = $("q"), qList = $("q-results"), qNote = $("q-note"), active = -1, found = [];
  function resultHTML(r, i) {
    var inner;
    if (r.kind === "method") {
      var m = D.methods[r.id], nm = splitName(m.name);
      inner = "<span class=\"r-kind\">Method</span><span class=\"r-name\">" + esc(nm[0]) +
        (nm[1] ? " <span class=\"mdesc\">" + esc(nm[1]) + "</span>" : "") + "</span>" +
        "<span class=\"r-meta\">" + (m.n ? "in " + m.n + " of " + FWK.length + " frameworks" : "no framework today") +
        (m.arxiv ? " &middot; arXiv " + esc(m.arxiv) : "") + "</span>";
    } else {
      var p = PAPER[r.arxiv];
      inner = "<span class=\"r-kind\">Paper</span><span class=\"r-name\">" + esc(p[2]) + "</span>" +
        "<span class=\"r-meta\">arXiv " + esc(p[0]) + " &middot; " +
        (p[3] ? "<b class=\"r-in\">" + (p[4].length ? "in " + esc(listJoin(p[4])) : "reached a framework, later removed") + "</b>"
              : "not in any framework") + "</span>";
    }
    var href = r.kind === "method" ? "#method-" + r.id : "#paper-" + r.arxiv;
    return "<li role=\"option\" id=\"q-opt-" + i + "\" aria-selected=\"" + (i === active) + "\"><a href=\"" + esc(href) + "\" tabindex=\"-1\">" + inner + "</a></li>";
  }
  function renderResults() {
    var res = search(qInput.value);
    found = res.items || [];
    if (!qInput.value.trim()) {
      qList.hidden = true; qNote.textContent = ""; qInput.setAttribute("aria-expanded", "false");
      return;
    }
    if (!found.length) {
      qList.hidden = true; qInput.setAttribute("aria-expanded", "false");
      qNote.textContent = norm(qInput.value).length < 2 ? "" :
        "Nothing matches. Try a method name, an arXiv id or a setting such as clip_ratio_high.";
      return;
    }
    if (active >= found.length) active = found.length - 1;
    qList.innerHTML = found.map(resultHTML).join("");
    qList.hidden = false;
    qInput.setAttribute("aria-expanded", "true");
    qInput.setAttribute("aria-activedescendant", active >= 0 ? "q-opt-" + active : "");
    qNote.textContent = res.total > found.length ? "Showing 8 of " + res.total + " matches. Add a word to narrow them." :
      res.total + (res.total === 1 ? " match" : " matches");
  }
  qInput.addEventListener("input", function () { active = -1; renderResults(); });
  qInput.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!found.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + found.length) % found.length;
      renderResults();
    } else if (e.key === "Enter") {
      var r = found[active >= 0 ? active : 0];
      if (r) { e.preventDefault(); location.hash = r.kind === "method" ? "#method-" + r.id : "#paper-" + r.arxiv; }
    } else if (e.key === "Escape") {
      qInput.value = ""; active = -1; renderResults();
    }
  });
  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    if (e.key === "/" && !detail.open && tag !== "input" && tag !== "textarea" && tag !== "select" && !e.target.isContentEditable) {
      e.preventDefault();
      $("lookup").scrollIntoView({ block: "start" });
      qInput.focus();
    }
  });

  /* ---------- footer and citation ---------- */
  $("snapshots").innerHTML = D.snapshots.map(function (s) {
    return "<li><span>" + esc(s[0]) + "</span> " + esc(s[1]) + " &middot; " + esc(s[2]) + "</li>";
  }).join("");
  function copyText(text, statusEl) {
    var done = function () {
      if (!statusEl) return;
      statusEl.textContent = "Copied";
      setTimeout(function () { statusEl.textContent = ""; }, 2000);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {});
      return;
    }
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    (detail.open ? detail : document.body).appendChild(area);
    area.select();
    try { document.execCommand("copy"); done(); } catch (err) { /* the text stays selected for a manual copy */ }
    area.remove();
  }
  $("copy-bib").addEventListener("click", function () { copyText($("bibtex").textContent, $("copied")); });

  if (/^#(method|paper)-/.test(location.hash)) route();
})();
