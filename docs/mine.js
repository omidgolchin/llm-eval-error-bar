/* mine.js: the "My eval" mode. Reads pasted per-question results, computes the
 * error bar with evalbar.js, and recommends questions or repeats. */
(function () {
  "use strict";
  var E = window.EvalBar, F = Tool.fmt;
  var $ = function (id) { return document.getElementById(id); };
  var state = Tool.readParams({ mode: "mine", level: "0.95", nameA: "", nameB: "", ex: "" });
  var EXAMPLES = [], last = null;

  function pp(x, d) { return (100 * x).toFixed(d == null ? 1 : d) + "%"; }
  function pts(x, d) { return (100 * x).toFixed(d == null ? 1 : d); }
  function sgn(x, d) { return (x >= 0 ? "+" : "−") + pts(Math.abs(x), d); }
  function nm(which) { var v = $(which === "A" ? "nameA" : "nameB").value.trim(); return v || which; }
  function check(cls, badge, name, text) { return { cls: cls, badge: badge, name: name, text: text }; }

  /* ---------- modes ---------- */
  function setMode(m) {
    state.mode = m;
    ["mine", "why"].forEach(function (k) {
      var on = k === m;
      $("tab-" + k).classList.toggle("active", on); $("tab-" + k).setAttribute("aria-selected", String(on));
      $("view-" + k).hidden = !on;
    });
    if (m === "why" && window.ExplorerRedraw) window.ExplorerRedraw();
    if (m === "mine" && last) drawChart();
    save();
  }
  $("tab-mine").addEventListener("click", function () { setMode("mine"); });
  $("tab-why").addEventListener("click", function () { setMode("why"); });

  function save() { Tool.writeParams({ mode: state.mode === "why" ? "why" : "", level: $("level").value === "0.95" ? "" : $("level").value, nameA: $("nameA").value.trim(), nameB: $("nameB").value.trim(), ex: state.ex }); }

  /* ---------- compute ---------- */
  function run() {
    var level = Number($("level").value), lv = Math.round(level * 100) + "%";
    var pa = E.parse($("resA").value), pb = E.parse($("resB").value);
    $("cntA").textContent = pa.rows.length ? "· " + pa.rows.length + " question" + (pa.rows.length === 1 ? "" : "s") : "";
    $("cntB").textContent = pb.rows.length ? "· " + pb.rows.length + " question" + (pb.rows.length === 1 ? "" : "s") : "";
    showErr("errA", pa.errors); showErr("errB", pb.errors);
    $("vKicker").textContent = (pb.rows.length ? "Comparison (" : "Error bar (") + lv + ")";
    if (pa.rows.length < 2) {
      last = null;
      $("vTitle").textContent = "Paste results to start";
      $("vBody").textContent = pa.rows.length === 1 ? "Add at least one more question: an error bar needs two or more." : "Or load an example from the menu: all three use real runs from this project.";
      $("kpis").innerHTML = ""; $("checks").innerHTML = ""; $("chart-next").innerHTML = ""; $("next-caption").textContent = "";
      $("verdict").className = "panel verdict v-neutral"; save(); return;
    }
    var A = E.cluster(pa.rows, level), nA = E.naive(pa.rows, level), vcA = E.components(pa.rows);
    var kbar = A.kbar, kTxt = Number.isInteger(kbar) ? String(kbar) : kbar.toFixed(1);
    var cmp = pb.rows.length >= 2 ? E.paired(pa.rows, pb.rows, level) : null;
    var checks = [], title, body, kpis, cls;

    if (!cmp) {
      var lo = Math.max(0, A.lo), hi = Math.min(1, A.hi);
      title = pp(A.est) + " ± " + pts(A.half) + " points";
      body = "The true accuracy on questions like these is between " + pp(lo) + " and " + pp(hi) + ", at " + lv + " confidence. From " +
        A.n + " questions × " + kTxt + " run" + (kbar === 1 ? "" : "s") + ", with the error bar clustered by question.";
      cls = "v-accent";
      kpis = [[pp(A.est), "accuracy"], ["± " + pts(A.half), "error bar, points", "errbar"], [A.n + " × " + kTxt, "questions × runs"]];
      if (kbar > 1) kpis.push([Math.round(A.total / Math.max(1, (A.se * A.se) / (nA.se * nA.se))).toLocaleString("en-US"), "independent answers it is worth", "neff"]);
    } else {
      var d = cmp, lead = d.lo > 0 ? "B" : d.hi < 0 ? "A" : null;
      title = lead ? nm(lead) + " is ahead by " + pts(Math.abs(d.diff)) + " points" : "No clear difference";
      body = nm("B") + " − " + nm("A") + " = " + sgn(d.diff) + " points (" + lv + " interval: " + sgn(d.lo) + " to " + sgn(d.hi) + "), from " + d.n +
        " shared questions, paired by question. " + nm("A") + " scores " + pp(d.a.est) + " ± " + pts(d.a.half) + "; " + nm("B") + " scores " + pp(d.b.est) + " ± " + pts(d.b.half) + "." +
        (lead ? "" : " The interval includes zero: these results cannot tell the two apart.");
      cls = lead ? "v-good" : "v-neutral";
      kpis = [[sgn(d.diff), "points, " + nm("B") + " − " + nm("A")], ["± " + pts(d.half), "error bar, points", "errbar"], [pp(d.a.est), nm("A") + " accuracy"], [pp(d.b.est), nm("B") + " accuracy"]];
      var gain = 1 - d.half / d.halfUnpaired;
      checks.push(check(gain > 0.1 ? "is-ok" : "is-info", "PAIRED", "Same questions for both.",
        "Comparing question by question gives ±" + pts(d.half) + " points; comparing the two scores separately would give ±" + pts(d.halfUnpaired) +
        (gain > 0 ? " (" + Math.round(100 * gain) + "% wider)." : ".")));
      if (d.mismatch) checks.push(check("is-warn", "MISMATCH", "Different numbers of lines.", "Model A has " + pa.rows.length + " questions and model B " + pb.rows.length + "; only the first " + d.n + " are compared. Lines must be the same questions in the same order."));
    }

    // checks shared by both modes (about model A's design)
    var n = cmp ? cmp.n : A.n;
    checks.push(n < 30
      ? check("is-warn", "FEW QUESTIONS", n + " questions.", "The t interval is approximate with this few; treat the error bar as rough and add questions if you can.")
      : check("is-ok", "QUESTIONS", n + " questions.", "Enough for the interval's approximations to hold."));
    if (!cmp && kbar > 1) {
      var narrow = 1 - nA.half / A.half;
      checks.push(check(narrow > 0.15 ? "is-warn" : "is-ok", "USUAL INTERVAL", "The usual interval would be " + (narrow > 0 ? Math.round(100 * narrow) + "% too narrow." : "about the same."),
        "Treating all " + A.total.toLocaleString("en-US") + " runs as independent gives ±" + pts(nA.half) + " points. Runs of one question share its difficulty, so they are not independent evidence; see <i>Why it matters</i> for what that does to coverage."));
    }
    var next = nextBuy(pa.rows, A, vcA, level);
    if (next) checks.push(next.check);
    if (!cmp && (A.est < 0.03 || A.est > 0.97) && A.n < 100) checks.push(check("is-warn", "EDGE", "Accuracy near " + (A.est < 0.5 ? "0%" : "100%") + ".", "Near the edge the interval is less reliable; it has been clipped to 0–100%."));

    $("vTitle").textContent = title; $("vBody").textContent = body;
    $("verdict").className = "panel verdict " + cls;
    $("kpis").innerHTML = kpis.map(function (x) { return '<div class="kpi"><span class="k-val">' + x[0] + '</span><span class="k-lbl">' + x[1] + (x[2] ? ' <button type="button" data-tip="' + x[2] + '"></button>' : "") + "</span></div>"; }).join("");
    $("checks").innerHTML = checks.map(function (c) { return '<div class="check ' + c.cls + '"><span class="badge">' + c.badge + '</span><span><span class="c-name">' + c.name + '</span> <span class="c-text">' + c.text + "</span></span></div>"; }).join("");
    last = { A: A, nA: nA, vc: vcA, cmp: cmp, level: level, lv: lv, title: title, body: body, kTxt: kTxt, checks: checks };
    drawChart(); save();
  }
  function showErr(id, errs) {
    $(id).hidden = !errs.length;
    $(id).textContent = errs.length ? errs.slice(0, 2).join(" ") + (errs.length > 2 ? " (" + (errs.length - 2) + " more lines skipped.)" : "") + " Those lines were skipped." : "";
  }

  /* questions or repeats for the next round */
  function nextBuy(rows, A, vc, level) {
    var N = A.n, K = Math.max(1, Math.round(A.kbar));
    if (!vc || vc.single) {
      var h2 = A.half * Math.sqrt(N / (2 * N));
      return { check: check("is-info", "NEXT ROUND", "More questions is the lever you can measure.",
        "Doubling to " + 2 * N + " questions narrows the error bar to about ±" + pts(h2) + " points. With one run per question, run noise and question difficulty cannot be separated; rerun 30 questions a second time to find out whether repeats would help.") };
    }
    var hQ = E.halfWidth(vc, 2 * N, K, level), hK = E.halfWidth(vc, N, 2 * K, level);
    var floor = E.tq(1 - (1 - level) / 2, N - 1) * Math.sqrt(vc.sigma2_q / N);
    var shareQ = vc.sigma2_q / (vc.sigma2_q + vc.sigma2_w / K);
    var better = hQ < hK ? "questions" : "runs";
    return { check: check("is-info", "NEXT ROUND", "Spend it on " + (better === "questions" ? "new questions." : "more runs per question."),
      "For the same extra cost (" + (N * K).toLocaleString("en-US") + " more runs): doubling the questions gives ±" + pts(hQ) + " points; doubling the runs per question gives ±" + pts(hK) + ". " +
      Math.round(100 * shareQ) + "% of the noise comes from questions differing, which only new questions reduce: on these " + N + " questions, even unlimited runs stop at ±" + pts(floor) + "."),
      hQ: hQ, hK: hK, floor: floor };
  }

  /* ---------- chart ---------- */
  function drawChart() {
    if (!last || $("view-mine").hidden) return;
    var L = last, A = L.A, N = A.n, K = Math.max(1, Math.round(A.kbar)), T = N * K, crit;
    var mult = [1, 1.5, 2, 3, 4], series = [], cap;
    if (L.cmp) {
      var d = L.cmp;
      series.push({ label: "Add shared questions", color: "accent", markers: true, points: mult.map(function (m) { return [m * d.n * K, 100 * d.half * Math.sqrt(1 / m)]; }) });
      cap = "Error bar of the difference as you add shared questions (both models run on each). Pairing already removed question difficulty; what is left shrinks with the square root of the questions.";
    } else if (!L.vc || L.vc.single) {
      series.push({ label: "Add questions (1 run each)", color: "accent", markers: true, points: mult.map(function (m) { return [m * T, 100 * A.half * Math.sqrt(1 / m)]; }) });
      cap = "With one run per question, the error bar shrinks with the square root of the number of questions. Whether repeats would help cannot be measured from these results.";
    } else {
      series.push({ label: "Add questions (" + K + " run" + (K === 1 ? "" : "s") + " each)", color: "accent", markers: true,
        points: mult.map(function (m) { return [m * T, 100 * E.halfWidth(L.vc, Math.round(m * N), K, L.level)]; }) });
      series.push({ label: "Add runs to the same " + N + " questions", color: "series2", markers: true, dash: "5 4",
        points: mult.map(function (m) { return [m * T, 100 * E.halfWidth(L.vc, N, m * K, L.level)]; }) });
      crit = E.tq(1 - (1 - L.level) / 2, N - 1);
      cap = "Predicted error bar for the same total number of runs, spent two ways, from your estimated noise split (questions σ²q = " + L.vc.sigma2_q.toFixed(4) + ", runs σ²w = " + L.vc.sigma2_w.toFixed(4) + "). The dashed line can never go below ±" + pts(crit * Math.sqrt(L.vc.sigma2_q / N)) + " points: only new questions get past it.";
    }
    Tool.lineChart($("chart-next"), {
      height: 240, legend: true, series: series, xTitle: "total runs (questions × runs per question)", yTitle: "error bar (± points)",
      yMin: 0, xFormat: function (x) { return Math.round(x).toLocaleString("en-US"); }, yFormat: function (y) { return y.toFixed(1); },
      aria: "Error bar against total runs"
    });
    $("next-caption").textContent = cap;
  }

  /* ---------- actions ---------- */
  $("copySummary").addEventListener("click", function () {
    if (!last) return;
    var L = last, A = L.A, txt;
    if (L.cmp) {
      var d = L.cmp;
      txt = nm("B") + " − " + nm("A") + ": " + sgn(d.diff) + " points (" + L.lv + " CI " + sgn(d.lo) + " to " + sgn(d.hi) + "), paired by question over " + d.n + " questions; " +
        nm("A") + " " + pp(d.a.est) + " ± " + pts(d.a.half) + ", " + nm("B") + " " + pp(d.b.est) + " ± " + pts(d.b.half) + " (cluster-robust SE by question, t interval with " + (d.n - 1) + " df).";
    } else {
      txt = "Accuracy " + pp(A.est) + " (" + L.lv + " CI " + pp(Math.max(0, A.lo)) + " to " + pp(Math.min(1, A.hi)) + "; " + A.n + " questions × " + L.kTxt + " runs, cluster-robust SE by question, t interval with " + (A.n - 1) + " df).";
    }
    Tool.copy(txt, $("toast"), "Summary copied");
  });
  $("copyLink").addEventListener("click", function () { save(); Tool.copy(location.href, $("toast"), "Link copied (settings only; results stay on your device)"); });

  ["resA", "resB"].forEach(function (id) { $(id).addEventListener("input", function () { state.ex = ""; $("example").value = ""; run(); }); });
  ["level", "nameA", "nameB"].forEach(function (id) { $(id).addEventListener("input", run); $(id).addEventListener("change", run); });
  $("example").addEventListener("change", function () {
    if (this.value === "") return;
    loadExample(+this.value);
  });
  function loadExample(i) {
    var ex = EXAMPLES[i]; if (!ex) return;
    state.ex = String(i); $("example").value = String(i);
    $("resA").value = ex.a; $("resB").value = ex.b || ""; $("nameA").value = ex.nameA || ""; $("nameB").value = ex.nameB || "";
    run();
  }
  var rz; window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(drawChart, 150); });
  if (window.KitTheme && KitTheme.onChange) KitTheme.onChange(drawChart);

  Tool.explain({
    format: { t: "What to paste", d: "One line per question, in a fixed order. Each line holds that question's runs: <code>1 0 1</code> (1 = correct), <code>pass fail pass</code>, or a count like <code>2/3</code>. Lines can start with a question id. Most eval harnesses can export this as a CSV with one row per question." },
    level: { t: "Confidence level", d: "How often intervals built this way contain the true accuracy. 95% is the convention in papers; 90% gives a narrower, less certain bar." },
    errbar: { t: "Error bar", d: "Half the width of the confidence interval: the score is within this many points of the true accuracy, at the chosen confidence. It treats questions as the independent units, because a model's runs on one question are not independent of each other." },
    neff: { t: "Independent answers it is worth", d: "Your N × K runs carry as much information about accuracy as this many truly independent answers (total runs ÷ design effect). It is far below N × K when questions differ a lot in difficulty, which is why repeats add little." },
    narrow: { t: "What narrows it fastest", d: "Both lines spend the same number of runs. One adds new questions; the other adds more runs to the questions you already have. The prediction uses your own split of the noise into question difficulty (σ²q) and run-to-run flips (σ²w): Var ≈ σ²q/N + σ²w/(N·K)." },
    coverage: { t: "Coverage", d: "If you build a 95% interval many times on different samples, it should contain the true value about 95% of the time. Here the 'true value' is the model's accuracy over all 400 questions × 5 runs, and each sample is a smaller eval drawn from them." },
    methods: { t: "The interval methods", d: "<b>Naive</b>: all N×K answers as independent (the common mistake). <b>Question means + t</b> and <b>cluster-robust</b>: treat questions as the units (what this tool uses). <b>Two-stage bootstrap</b>: resample questions, then runs. <b>Hierarchical Bayesian</b>: a model with a difficulty per question. <b>Seed-only</b>: answers a different question, accuracy on these exact questions." },
    undercover: { t: "Verdict", d: "An interval 'under-covers' when its coverage is below 93% and even the top of its Monte Carlo range is below 95%: it is too narrow for sure, not just by chance. The rule was fixed in the project's plan before the runs." },
    budget: { t: "Fixed budget", d: "The same 250 model calls, split into more questions with fewer runs each, or fewer questions with more runs. The solid line is what the runs produced; the dashed line is the variance-components prediction, which tracks it closely." },
    components: { t: "Variance components", d: "Accuracy estimates are noisy for two reasons: questions differ in difficulty (σ²q) and the same question flips between runs (σ²w). A one-way analysis of variance on the runs estimates both." }
  });

  fetch("data/examples.json").then(function (r) { return r.json(); }).then(function (exs) {
    EXAMPLES = exs;
    exs.forEach(function (ex, i) { var o = document.createElement("option"); o.value = i; o.textContent = ex.label; $("example").appendChild(o); });
    if (state.nameA) $("nameA").value = state.nameA;
    if (state.nameB) $("nameB").value = state.nameB;
    loadExample(state.ex !== "" && exs[+state.ex] ? +state.ex : 0);
  }).catch(function () { run(); });
  $("level").value = state.level;
  setMode(state.mode === "why" ? "why" : "mine");
})();
