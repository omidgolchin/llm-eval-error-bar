/* evalbar.js: the math behind "My eval". Mirrors src/errorbars (intervals.py,
 * analyze.py) so the page and the Python package give the same numbers;
 * tests/test_evalbar_js.py checks that on random matrices.
 *
 *   parse(text)              rows of per-question results -> { rows: [{c, k}], errors }
 *   cluster(rows)            pooled accuracy, cluster-robust SE by question, t interval
 *   naive(rows)              Wilson interval treating all N*K answers as independent
 *   components(rows)         one-way ANOVA: sigma2_q (between), sigma2_w (within)
 *   halfWidth(vc, n, k)      predicted 95% half-width at design (n, k)
 *   paired(rowsA, rowsB)     per-question differences, t interval
 *   tq(p, df), zq(p)         quantiles of t and the standard normal
 */
(function () {
  "use strict";

  /* ---------- quantiles ---------- */
  function zq(p) { // Acklam's inverse normal, |error| < 1.2e-9
    var a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239];
    var b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
    var c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
    var d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416];
    var q, r;
    if (p < 0.02425) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (p > 1 - 0.02425) { q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    q = p - 0.5; r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
  function tq(p, df) { // t quantile: exact for df 1 and 2, Cornish-Fisher series beyond
    if (!isFinite(df) || df > 1e6) return zq(p);
    if (df === 1) return Math.tan(Math.PI * (p - 0.5));
    if (df === 2) return (2 * p - 1) / Math.sqrt(2 * p * (1 - p));
    var z = zq(p), z2 = z * z, v = df;
    return z + (z2 * z + z) / (4 * v)
      + (5 * Math.pow(z, 5) + 16 * z2 * z + 3 * z) / (96 * v * v)
      + (3 * Math.pow(z, 7) + 19 * Math.pow(z, 5) + 17 * z2 * z - 15 * z) / (384 * v * v * v)
      + (79 * Math.pow(z, 9) + 776 * Math.pow(z, 7) + 1482 * Math.pow(z, 5) - 1920 * z2 * z - 945 * z) / (92160 * v * v * v * v);
  }

  /* ---------- input ---------- */
  var YES = { "1": 1, "y": 1, "yes": 1, "true": 1, "t": 1, "pass": 1, "correct": 1, "right": 1, "✓": 1 };
  var NO = { "0": 0, "n": 0, "no": 0, "false": 0, "f": 0, "fail": 0, "wrong": 0, "incorrect": 0, "✗": 0 };
  /* One line per question. A line is either runs ("1 0 1", "pass,fail") or a
   * count ("2/3"). Blank lines and lines starting with # are skipped; a first
   * column that is not a result (a question id) is ignored. */
  function parse(text) {
    var rows = [], errors = [];
    String(text || "").split(/\r?\n/).forEach(function (line, i) {
      var s = line.trim();
      if (!s || s[0] === "#") return;
      var m = s.match(/(\d+)\s*\/\s*(\d+)\s*$/);
      if (m) {
        var c = +m[1], k = +m[2];
        if (k < 1 || c > k) { errors.push("Line " + (i + 1) + ": \"" + s + "\" is not a valid count."); return; }
        rows.push({ c: c, k: k }); return;
      }
      var toks = s.split(/[\s,;\t|]+/).filter(Boolean), cc = 0, kk = 0, bad = 0;
      toks.forEach(function (t, j) {
        var x = t.toLowerCase();
        if (x in YES) { cc++; kk++; } else if (x in NO) { kk++; }
        else if (j === 0) { /* a question id */ } else bad++;
      });
      if (!kk || bad) { if (i > 0 || kk) errors.push("Line " + (i + 1) + ": could not read \"" + s.slice(0, 40) + "\"."); return; }
      rows.push({ c: cc, k: kk });
    });
    return { rows: rows, errors: errors };
  }

  /* ---------- single model ---------- */
  function sums(rows) {
    var C = 0, K = 0;
    rows.forEach(function (r) { C += r.c; K += r.k; });
    return { C: C, K: K, n: rows.length, p: K ? C / K : NaN, kbar: rows.length ? K / rows.length : NaN };
  }
  // cluster-robust SE of the pooled mean, clusters = questions, small-sample factor n/(n-1)
  function cluster(rows, level) {
    level = level || 0.95;
    var s = sums(rows), est = s.p, acc = 0;
    rows.forEach(function (r) { var u = r.c - r.k * est; acc += u * u; });
    var se = s.n > 1 ? Math.sqrt((s.n / (s.n - 1)) * acc / (s.K * s.K)) : NaN;
    var crit = tq(1 - (1 - level) / 2, s.n - 1);
    return { est: est, se: se, crit: crit, lo: est - crit * se, hi: est + crit * se, half: crit * se, n: s.n, kbar: s.kbar, total: s.K };
  }
  function naive(rows, level) {
    level = level || 0.95;
    var s = sums(rows), n = s.K, p = s.p, z = zq(1 - (1 - level) / 2);
    var den = 1 + z * z / n, centre = (p + z * z / (2 * n)) / den;
    var half = (z / den) * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n));
    return { est: p, se: Math.sqrt(p * (1 - p) / n), lo: centre - half, hi: centre + half, half: half };
  }
  // one-way ANOVA on question means (analyze.variance_components); needs k >= 2.
  // With unequal k the harmonic-free average k is used, which is exact when balanced.
  function components(rows) {
    var s = sums(rows);
    if (s.n < 2) return null;
    var ssB = 0, ssW = 0, dfW = 0, kmin = Infinity;
    rows.forEach(function (r) {
      var m = r.c / r.k;
      ssB += r.k * (m - s.p) * (m - s.p);
      ssW += r.c * (1 - m) * (1 - m) + (r.k - r.c) * m * m; // sum of squared deviations of 0/1 cells
      dfW += r.k - 1; kmin = Math.min(kmin, r.k);
    });
    if (kmin < 2 || dfW < 1) return { sigma2_q: null, sigma2_w: null, k: s.kbar, n: s.n, single: true };
    var msB = ssB / (s.n - 1), msW = ssW / dfW, k0 = s.kbar;
    return { sigma2_q: Math.max((msB - msW) / k0, 0), sigma2_w: msW, k: k0, n: s.n, single: false };
  }
  function halfWidth(vc, n, k, level) {
    level = level || 0.95;
    var se = Math.sqrt(vc.sigma2_q / n + vc.sigma2_w / (n * k));
    return tq(1 - (1 - level) / 2, n - 1) * se;
  }

  /* ---------- two models on the same questions ---------- */
  function paired(rowsA, rowsB, level) {
    level = level || 0.95;
    var n = Math.min(rowsA.length, rowsB.length);
    if (n < 2) return null;
    var d = [], mean = 0;
    for (var i = 0; i < n; i++) { var x = rowsB[i].c / rowsB[i].k - rowsA[i].c / rowsA[i].k; d.push(x); mean += x; }
    mean /= n;
    var v = 0; d.forEach(function (x) { v += (x - mean) * (x - mean); }); v /= (n - 1);
    var se = Math.sqrt(v / n), crit = tq(1 - (1 - level) / 2, n - 1);
    var a = cluster(rowsA.slice(0, n), level), b = cluster(rowsB.slice(0, n), level);
    var seUnpaired = Math.sqrt(a.se * a.se + b.se * b.se);
    return { diff: mean, se: se, crit: crit, lo: mean - crit * se, hi: mean + crit * se, half: crit * se, n: n,
      a: a, b: b, seUnpaired: seUnpaired, halfUnpaired: crit * seUnpaired, mismatch: rowsA.length !== rowsB.length };
  }

  var api = { zq: zq, tq: tq, parse: parse, cluster: cluster, naive: naive, components: components, halfWidth: halfWidth, paired: paired };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.EvalBar = api;
})();
