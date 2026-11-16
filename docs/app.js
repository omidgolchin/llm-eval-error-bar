/* Error Bars for LLM Evals — playground.
 *
 * The "Why it matters" mode. Everything shown comes from data/results.json, exported from the
 * Stage 4 results (results/coverage_*.csv, results/budget.csv,
 * results/summary.md) by scripts/export_playground_data.py. No live
 * model calls, no numbers computed in the browser beyond formatting.
 */

/* Presentation only (2026-11-16 restructure): this page is one flow, not
 * two tabs. mine.js (frozen) still binds the tab buttons and hides the
 * inactive view at load, so here the tab strip is replaced by an in-page
 * anchor nav and both sections are shown, stacked: "Your eval" first,
 * "Why it matters: real runs" at the end. No values are computed here. */
(function () {
  "use strict";
  var modes = document.querySelector(".tool-modes");
  if (modes) {
    var nav = document.createElement("nav");
    nav.className = "eb-jump";
    nav.setAttribute("aria-label", "On this page");
    nav.innerHTML = '<a href="#view-mine">Your eval</a>' +
      '<a href="#view-why">Why it matters: real runs</a>';
    modes.replaceWith(nav);
  }
  ["view-mine", "view-why"].forEach(function (id) {
    var s = document.getElementById(id);
    if (s) s.hidden = false;
  });
})();

(function () {
  "use strict";

  var NS = [25, 50, 100, 200];
  var KS = [1, 2, 3, 5];
  var state = { model: "qwen", method: "naive", N: 50, K: 5, bmethod: "cluster" };
  var DATA = null;

  function $(id) { return document.getElementById(id); }
  function pct(x, digits) { return (x * 100).toFixed(digits == null ? 1 : digits) + "%"; }
  function num(x, digits) { return x.toFixed(digits == null ? 3 : digits); }

  function covRow(model, method, N, K) {
    return DATA.coverage.find(function (r) {
      return r.model === model && r.method === method && r.N === N && r.K === K;
    });
  }
  function modelInfo(slug) {
    return DATA.models.find(function (m) { return m.slug === slug; });
  }
  function methodInfo(id) {
    return DATA.methods.find(function (m) { return m.id === id; });
  }

  function fillSelect(el, items, value, labelFn) {
    el.innerHTML = "";
    items.forEach(function (it) {
      var o = document.createElement("option");
      o.value = it.value;
      o.textContent = labelFn ? labelFn(it) : it.label;
      if (String(it.value) === String(value)) o.selected = true;
      el.appendChild(o);
    });
  }

  function renderCoverage() {
    var row = covRow(state.model, state.method, state.N, state.K);
    var naive = covRow(state.model, "naive", state.N, state.K);
    var info = modelInfo(state.model);
    if (!row) return;
    $("method-note").textContent = methodInfo(state.method).note +
      (state.method === "bayes" ? " Coverage for this method rests on B = 200 subsamples per design, so its Monte Carlo interval is wider." : "");
    $("st-cov").textContent = pct(row.coverage);
    $("st-width").textContent = num(row.median_width);
    var v = $("st-verdict");
    v.textContent = row.under_covers ? "Too narrow" : "Holds up";
    v.className = "value " + (row.under_covers ? "verdict-bad" : "verdict-good");
    $("st-ref").textContent = num(info.reference, 4);
    $("cov-note").textContent =
      "Monte Carlo 95% interval for this coverage estimate: [" +
      num(row.mc_lower) + ", " + num(row.mc_upper) + "] · B = " + row.B +
      " subsamples drawn from the model's 400-question pool · reference" +
      " accuracy is the model's mean over all 400 x 5 runs. At the same" +
      " design the naive interval covers " + pct(naive.coverage) + ".";
    $("seedonly-note").classList.toggle("hidden", state.method !== "seed_only");

    var series = [];
    var selPoints = KS.map(function (k) {
      var r = covRow(state.model, state.method, state.N, k);
      return { k: k, r: r };
    });
    series.push({
      label: (({ naive: "Naive", question_means: "Question means + t", cluster: "Cluster-robust", bootstrap: "Bootstrap", bayes: "Bayesian", seed_only: "These questions only" })[state.method] || methodInfo(state.method).name) + ": coverage",
      color: "accent", markers: true,
      points: selPoints.map(function (p) { return [p.k, p.r.coverage]; }),
      ci: selPoints.map(function (p) { return [p.r.mc_lower, p.r.mc_upper]; })
    });
    if (state.method !== "naive") {
      series.push({
        label: "Naive: coverage",
        color: "series2", dash: "5 4", markers: true,
        points: KS.map(function (k) {
          var r = covRow(state.model, "naive", state.N, k);
          return [k, r.coverage];
        })
      });
    }
    Tool.lineChart($("chart-cov"), {
      series: series, legend: true, height: 280,
      hLines: [{ y: 0.95, label: "target 95%", color: "bad" }],
      xTitle: "runs per question (K)", yTitle: "empirical coverage",
      yMin: 0, yMax: 1, xTicks: KS,
      xFormat: function (x) { return String(x); }, yFormat: function (y) { return y.toFixed(2); }
    });
    $("cov-chart-note").textContent =
      "Coverage across K at N = " + state.N + " questions for " + info.name +
      ". Whiskers are the Monte Carlo interval of the coverage estimate." +
      " The pattern to see: the pooled (naive) interval gets worse as K" +
      " grows, because repeated runs on one question are not new data.";
  }

  function renderBudget() {
    var rows = DATA.budget.filter(function (r) {
      return r.model === state.model && r.method === state.bmethod;
    }).sort(function (a, b) { return a.K - b.K; });
    var info = modelInfo(state.model);
    var best = rows.reduce(function (a, b) {
      return b.median_width < a.median_width ? b : a;
    });
    var w1 = rows.find(function (r) { return r.K === 1; });
    var w5 = rows.find(function (r) { return r.K === 5; });
    $("st-best").textContent = best.N + " x " + best.K;
    $("st-w1").textContent = num(w1.median_width);
    $("st-w5").textContent = num(w5.median_width);
    Tool.lineChart($("chart-budget"), {
      series: [
        { label: "empirical median width", color: "accent", markers: true,
          points: rows.map(function (r) { return [r.K, r.median_width]; }) },
        { label: "predicted from variance components", color: "neutral", dash: "5 4", markers: true,
          points: rows.map(function (r) { return [r.K, r.predicted_width]; }) }
      ],
      legend: true, height: 260, xTicks: rows.map(function (r) { return r.K; }),
      xTitle: "runs per question (K), with N = 250 / K questions",
      yTitle: "median interval width", yMin: 0,
      xFormat: function (x) { return String(x); }, yFormat: function (y) { return y.toFixed(2); }
    });
    var gain = (1 - w1.median_width / w5.median_width) * 100;
    $("budget-note").textContent =
      "For " + info.name + " with the " + methodInfo(state.bmethod).name +
      " interval: spending all 250 calls on questions (250 x 1) gives a" +
      " median width of " + num(w1.median_width) + ", against " +
      num(w5.median_width) + " for 50 x 5 — " + gain.toFixed(0) +
      "% narrower. The naive interval's width barely moves across" +
      " splits; that is the bug, not a bargain: its coverage collapses" +
      " as K grows (see the explorer above).";
  }

  function renderVariance() {
    $("vc-body").innerHTML = DATA.models.map(function (m) {
      return "<tr><td>" + m.name + "</td><td>" + num(m.sigma2_q, 4) +
        "</td><td>" + num(m.sigma2_w, 4) + "</td><td>" +
        m.parse_fail_pct.toFixed(1) + "%</td></tr>";
    }).join("");
  }

  function drawAll() { if (document.getElementById("view-why") && document.getElementById("view-why").hidden) return; renderCoverage(); renderBudget(); }
  window.ExplorerRedraw = function () { if (DATA) drawAll(); };

  function init() {
    fillSelect($("sel-model"),
      DATA.models.map(function (m) { return { value: m.slug, label: m.name }; }),
      state.model);
    var NICE = { naive: "Naive: all runs independent", question_means: "Question means + t", cluster: "Cluster-robust by question", bootstrap: "Two-stage bootstrap", bayes: "Hierarchical Bayesian", seed_only: "These questions only (different target)" };
    var methodItems = DATA.methods.map(function (m) {
      return { value: m.id, label: NICE[m.id] || m.name };
    });
    fillSelect($("sel-method"), methodItems, state.method);
    fillSelect($("sel-bmethod"), methodItems, state.bmethod);
    fillSelect($("sel-n"), NS.map(function (n) {
      return { value: n, label: n + " questions" };
    }), state.N);
    fillSelect($("sel-k"), KS.map(function (k) {
      return { value: k, label: k + (k === 1 ? " run" : " runs") };
    }), state.K);
    renderVariance();
    drawAll();
    KitTheme.onChange(drawAll);
    $("sel-model").addEventListener("change", function () {
      state.model = this.value; drawAll();
    });
    $("sel-method").addEventListener("change", function () {
      state.method = this.value; renderCoverage();
    });
    $("sel-n").addEventListener("change", function () {
      state.N = parseInt(this.value, 10); renderCoverage();
    });
    $("sel-k").addEventListener("change", function () {
      state.K = parseInt(this.value, 10); renderCoverage();
    });
    $("sel-bmethod").addEventListener("change", function () {
      state.bmethod = this.value; renderBudget();
    });
  }

  fetch("data/results.json")
    .then(function (r) { return r.json(); })
    .then(function (d) { DATA = d; init(); })
    .catch(function () {
      $("cov-note").textContent =
        "Could not load data/results.json — serve this folder over HTTP" +
        " (e.g. python3 -m http.server) rather than opening the file directly.";
    });
})();

/* Presentation only: the verdict drawn as a horizontal error-bar strip
 * (one model) or forest rows (two models, plus the difference). Every
 * number is read back from the verdict text and KPIs that mine.js has
 * just rendered — nothing is recomputed here. Upload buttons fill the
 * paste boxes from a local file and fire the same "input" event that
 * typing does, so mine.js does all the parsing as usual. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function num(s) { return parseFloat(String(s).replace(/−/g, "-")); }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

  function stripRow(x, y, name, est, lo, hi, valLabel) {
    var s = "";
    if (name) s += '<text class="strip-name" x="0" y="' + (y + 4) + '">' + esc(name) + "</text>";
    s += '<line class="strip-track" x1="' + x(0) + '" y1="' + y + '" x2="' + x(100) + '" y2="' + y + '"/>';
    s += '<line class="strip-bar" x1="' + x(lo) + '" y1="' + y + '" x2="' + x(hi) + '" y2="' + y + '"/>';
    s += '<line class="strip-cap" x1="' + x(lo) + '" y1="' + (y - 6) + '" x2="' + x(lo) + '" y2="' + (y + 6) + '"/>';
    s += '<line class="strip-cap" x1="' + x(hi) + '" y1="' + (y - 6) + '" x2="' + x(hi) + '" y2="' + (y + 6) + '"/>';
    s += '<circle class="strip-dot" cx="' + x(est) + '" cy="' + y + '" r="5"/>';
    if (valLabel) s += '<text class="strip-val" x="' + Math.min(x(hi) + 9, 634) + '" y="' + (y + 4) + '">' + esc(valLabel) + "</text>";
    return s;
  }

  function renderStrip() {
    var host = $("ebStrip");
    if (!host) return;
    var title = $("vTitle").textContent || "";
    var body = $("vBody").textContent || "";
    var vals = document.querySelectorAll("#kpis .k-val");
    host.innerHTML = "";
    if (/Paste results/.test(title) || !vals.length) return;

    var m1 = body.match(/between ([\d.]+)% and ([\d.]+)%/);
    if (m1) {
      var est = num(vals[0].textContent), lo = num(m1[1]), hi = num(m1[2]);
      var W = 640, L = 8, R = 632;
      var x = function (v) { return L + (v / 100) * (R - L); };
      host.innerHTML =
        '<svg viewBox="0 0 ' + W + ' 62" role="img" aria-label="Error bar from ' + lo.toFixed(1) + '% to ' + hi.toFixed(1) + '%, estimate ' + est.toFixed(1) + '%">' +
        '<text class="strip-val" x="' + x(est) + '" y="12" text-anchor="middle">' + est.toFixed(1) + "%</text>" +
        stripRow(x, 30, "", est, lo, hi, "") +
        '<text x="' + x(lo) + '" y="52" text-anchor="middle">' + lo.toFixed(1) + "%</text>" +
        '<text x="' + x(hi) + '" y="52" text-anchor="middle">' + hi.toFixed(1) + "%</text>" +
        '<text x="' + L + '" y="52">0%</text>' +
        '<text x="' + R + '" y="52" text-anchor="end">100%</text></svg>';
      return;
    }

    var scores = [];
    var re = /scores ([\d.]+)% ± ([\d.]+)/g, sm;
    while ((sm = re.exec(body)) !== null && scores.length < 2) {
      scores.push({ est: num(sm[1]), half: num(sm[2]) });
    }
    var dm = body.match(/interval: ([+−][\d.]+) to ([+−][\d.]+)\)/);
    if (scores.length === 2 && dm) {
      var nameA = ($("nameA").value.trim() || "A"), nameB = ($("nameB").value.trim() || "B");
      var L2 = 8, R2 = 560, W2 = 640;
      var xf = function (v) { return L2 + (v / 100) * (R2 - L2); };
      function forestRow(name, sc, yName, yBar) {
        return '<text class="strip-name" x="0" y="' + yName + '">' + esc(name) + "</text>" +
          stripRow(xf, yBar, "", sc.est, sc.est - sc.half, sc.est + sc.half,
            sc.est.toFixed(1) + "% ± " + sc.half.toFixed(1));
      }
      var rows = forestRow(nameA, scores[0], 12, 30) + forestRow(nameB, scores[1], 62, 80);
      var diff = num(vals[0].textContent), dlo = num(dm[1]), dhi = num(dm[2]);
      var M = Math.max(Math.abs(dlo), Math.abs(dhi), Math.abs(diff), 1) * 1.2;
      var xd = function (v) { return 320 + (v / M) * 300; };
      host.innerHTML =
        '<svg viewBox="0 0 ' + W2 + ' 104" role="img" aria-label="Forest plot: ' + esc(nameA) + " " + scores[0].est.toFixed(1) + "%, " + esc(nameB) + " " + scores[1].est.toFixed(1) + '%">' + rows +
        '<text x="' + L2 + '" y="102">0%</text><text x="' + R2 + '" y="102" text-anchor="end">100%</text></svg>' +
        '<svg viewBox="0 0 640 58" role="img" aria-label="Difference ' + esc(nameB) + " minus " + esc(nameA) + ": " + diff.toFixed(1) + ' points">' +
        '<text class="strip-name" x="0" y="14">' + esc((nameA.length + nameB.length > 24 ? "Difference" : nameB + " − " + nameA) + ", points") + "</text>" +
        '<line class="strip-zero" x1="' + xd(0) + '" y1="20" x2="' + xd(0) + '" y2="44"/>' +
        '<line class="strip-bar" x1="' + xd(dlo) + '" y1="32" x2="' + xd(dhi) + '" y2="32"/>' +
        '<line class="strip-cap" x1="' + xd(dlo) + '" y1="26" x2="' + xd(dlo) + '" y2="38"/>' +
        '<line class="strip-cap" x1="' + xd(dhi) + '" y1="26" x2="' + xd(dhi) + '" y2="38"/>' +
        '<circle class="strip-dot" cx="' + xd(diff) + '" cy="32" r="5"/>' +
        '<text x="' + xd(dlo) + '" y="56" text-anchor="middle">' + dlo.toFixed(1) + "</text>" +
        '<text class="strip-val" x="' + xd(diff) + '" y="14" text-anchor="middle">' + (diff >= 0 ? "+" : "−") + Math.abs(diff).toFixed(1) + "</text>" +
        '<text x="' + xd(dhi) + '" y="56" text-anchor="middle">' + dhi.toFixed(1) + "</text></svg>";
    }
  }

  if (window.MutationObserver) {
    var pending = false;
    var obs = new MutationObserver(function () {
      if (pending) return;
      pending = true;
      setTimeout(function () { pending = false; renderStrip(); }, 30);
    });
    ["vTitle", "vBody", "kpis"].forEach(function (id) {
      var el = $(id);
      if (el) obs.observe(el, { childList: true, subtree: true, characterData: true });
    });
  }
  setTimeout(renderStrip, 900);

  [["fileA", "resA"], ["fileB", "resB"]].forEach(function (pair) {
    var input = $(pair[0]);
    if (!input) return;
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) return;
      f.text().then(function (t) {
        var ta = $(pair[1]);
        ta.value = t;
        ta.dispatchEvent(new Event("input", { bubbles: true }));
        input.value = "";
      });
    });
  });
})();
