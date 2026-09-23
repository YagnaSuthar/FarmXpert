'use client';
import { useEffect } from 'react';
import { Scale } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

/**
 * Split a string into user-perceived characters (grapheme clusters).
 *
 * `[...str]` and `Array.from(str)` only split on Unicode code points,
 * which is wrong for Devanagari ("कृषि" splits into क + ृ + ष + ि,
 * scattering vowel marks) and Gujarati (same problem). Intl.Segmenter
 * with `granularity: 'grapheme'` respects extended grapheme clusters
 * per Unicode UAX #29 — consonant + matras stay as one unit.
 *
 * Falls back to code-point splitting on the (rare) environment that
 * doesn't ship Intl.Segmenter, which is acceptable degradation.
 */
function toGraphemes(text, locale) {
  if (typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function') {
    const segmenter = new Intl.Segmenter(locale, { granularity: 'grapheme' });
    return Array.from(segmenter.segment(text), (s) => s.segment);
  }
  return Array.from(text);
}

export default function HeroSection() {
  const t = useTranslations('hero');
  const tTitle = useTranslations('hero.titleParts');
  const tSensors = useTranslations('hero.sensors');
  const tStats = useTranslations('hero.stats');
  const locale = useLocale();

  // Title is animated character-by-character below. Read the three
  // localized title parts once so the animation effect can rebuild
  // the DOM whenever the language changes.
  const titleBefore = tTitle('before');
  const titleAccent = tTitle('accent');
  const titleAfter = tTitle('after');

  useEffect(() => {
    // ══ HERO TITLE — character by character animation ══
    const lineData = [
      { text: titleBefore, green: false },
      { text: titleAccent, green: true },
      { text: titleAfter, green: false },
    ];

    const titleEl = document.getElementById('heroTitle');
    if (!titleEl) return;

    // Locale switches keep the DOM node but we re-fire this effect,
    // so wipe the previous render before appending the new chars.
    titleEl.innerHTML = '';

    const baseDelay = 400;
    let charIdx = 0;

    lineData.forEach((line, li) => {
      const lineSpan = document.createElement('span');
      lineSpan.style.display = 'block';
      lineSpan.style.lineHeight = '1.1';
      if (li === 1) lineSpan.style.color = 'var(--accent-primary)';

      // Split into user-perceived characters so Devanagari/Gujarati
      // conjuncts and vowel marks animate as a single unit.
      toGraphemes(line.text, locale).forEach((ch) => {
        const span = document.createElement('span');
        span.className = 'char' + (line.green ? ' char-green' : '');
        span.textContent = ch === ' ' ? '\u00A0' : ch;
        span.style.animationDelay = baseDelay + charIdx * 55 + 'ms';
        lineSpan.appendChild(span);
        charIdx++;
      });

      titleEl.appendChild(lineSpan);
      if (li < lineData.length - 1) charIdx += 1;
    });

    // ══ ROOT CANVAS ANIMATION ══
    const canvas = document.getElementById('rootCanvas');
    const wrap = document.getElementById('rootWrap');
    if (!canvas || !wrap) return;

    const ctx = canvas.getContext('2d');
    let CW, CH;
    let currentDPR = window.devicePixelRatio || 1;
    let BRANCHES = [];
    let animStart = null;
    let running = true;
    let rafId = null;
    let pulses = [];
    let lastPulse = 0;
    let soilPts = [];
    let resizeTimer = null;

    // Read canvas colors from CSS custom properties (set in globals.css :root)
    const rootStyles = getComputedStyle(document.documentElement);
    const BR = parseInt(rootStyles.getPropertyValue('--canvas-branch-r')) || 0;
    const BG = parseInt(rootStyles.getPropertyValue('--canvas-branch-g')) || 0;
    const BB = parseInt(rootStyles.getPropertyValue('--canvas-branch-b')) || 128;
    const SR = parseInt(rootStyles.getPropertyValue('--canvas-soil-r')) || 173;
    const SG = parseInt(rootStyles.getPropertyValue('--canvas-soil-g')) || 216;
    const SB = parseInt(rootStyles.getPropertyValue('--canvas-soil-b')) || 230;
    const SDR = parseInt(rootStyles.getPropertyValue('--canvas-seed-r')) || 0;
    const SDG = parseInt(rootStyles.getPropertyValue('--canvas-seed-g')) || 0;
    const SDB = parseInt(rootStyles.getPropertyValue('--canvas-seed-b')) || 128;
    const PR = parseInt(rootStyles.getPropertyValue('--canvas-pulse-r')) || 0;
    const PG = parseInt(rootStyles.getPropertyValue('--canvas-pulse-g')) || 0;
    const PB = parseInt(rootStyles.getPropertyValue('--canvas-pulse-b')) || 128;

    const NP = {
      seed: [0.500, 0.000],
      ph: [0.500, 0.320],
      sm: [0.220, 0.520],
      n: [0.780, 0.520],
      p: [0.130, 0.440],
      k: [0.370, 0.440],
      st: [0.630, 0.440],
      at: [0.870, 0.440],
      hum: [0.500, 0.720],
      lux: [0.500, 0.880],
    };

    function P(nx, ny) { return { x: nx * CW, y: ny * CH }; }
    function Pn(name) { return P(...NP[name]); }

    function crPt(p0, p1, p2, p3, t) {
      const t2 = t * t, t3 = t2 * t;
      return {
        x: 0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
        y: 0.5 * (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
      };
    }

    function buildSpline(pts, steps = 80) {
      if (pts.length < 2) return [];
      const cp = [pts[0], ...pts, pts[pts.length - 1]];
      const out = [];
      for (let i = 0; i < cp.length - 3; i++)
        for (let s = 0; s <= steps; s++)
          out.push(crPt(cp[i], cp[i + 1], cp[i + 2], cp[i + 3], s / steps));
      return out;
    }

    function arcLen(sp) {
      const l = [0];
      for (let i = 1; i < sp.length; i++) {
        const dx = sp[i].x - sp[i - 1].x, dy = sp[i].y - sp[i - 1].y;
        l.push(l[i - 1] + Math.sqrt(dx * dx + dy * dy));
      }
      return l;
    }

    function defineBranches() {
      return [
        { d: 0, delay: 600, dur: 900, pts: [NP.seed, [0.500, 0.100], [0.500, 0.210], NP.ph] },
        { d: 0, delay: 600, dur: 1050, pts: [NP.seed, [0.440, 0.060], [0.340, 0.200], [0.270, 0.340], [0.230, 0.430], NP.sm] },
        { d: 0, delay: 600, dur: 1050, pts: [NP.seed, [0.560, 0.060], [0.660, 0.200], [0.730, 0.340], [0.770, 0.430], NP.n] },
        { d: 1, delay: 900, dur: 900, pts: [NP.seed, [0.390, 0.050], [0.270, 0.150], [0.190, 0.290], [0.150, 0.370], NP.p] },
        { d: 1, delay: 900, dur: 900, pts: [NP.seed, [0.610, 0.050], [0.730, 0.150], [0.810, 0.290], [0.850, 0.370], NP.at] },
        { d: 1, delay: 1100, dur: 700, pts: [NP.ph, [0.450, 0.360], [0.410, 0.420], NP.k] },
        { d: 1, delay: 1100, dur: 700, pts: [NP.ph, [0.550, 0.360], [0.590, 0.420], NP.st] },
        { d: 2, delay: 1400, dur: 600, pts: [NP.p, [0.175, 0.460], [0.200, 0.480], NP.sm] },
        { d: 2, delay: 1450, dur: 580, pts: [NP.sm, [0.295, 0.480], [0.335, 0.455], NP.k] },
        { d: 2, delay: 1500, dur: 500, pts: [NP.k, [0.440, 0.400], NP.ph] },
        { d: 2, delay: 1500, dur: 500, pts: [NP.st, [0.560, 0.400], NP.ph] },
        { d: 2, delay: 1450, dur: 580, pts: [NP.st, [0.665, 0.455], [0.705, 0.480], NP.n] },
        { d: 2, delay: 1400, dur: 600, pts: [NP.n, [0.800, 0.480], [0.825, 0.460], NP.at] },
        { d: 1, delay: 1300, dur: 950, pts: [NP.ph, [0.500, 0.420], [0.500, 0.550], [0.500, 0.640], NP.hum] },
        { d: 2, delay: 1600, dur: 750, pts: [NP.sm, [0.380, 0.580], [0.440, 0.660], NP.hum] },
        { d: 2, delay: 1600, dur: 750, pts: [NP.n, [0.620, 0.580], [0.560, 0.660], NP.hum] },
        { d: 1, delay: 1900, dur: 850, pts: [NP.hum, [0.500, 0.790], [0.500, 0.840], NP.lux] },
        { d: 3, delay: 2100, dur: 600, pts: [NP.lux, [0.430, 0.910], [0.370, 0.950]] },
        { d: 3, delay: 2150, dur: 580, pts: [NP.lux, [0.455, 0.920], [0.410, 0.962]] },
        { d: 3, delay: 2100, dur: 600, pts: [NP.lux, [0.570, 0.910], [0.630, 0.950]] },
        { d: 3, delay: 2150, dur: 580, pts: [NP.lux, [0.545, 0.920], [0.590, 0.962]] },
        { d: 3, delay: 2000, dur: 550, pts: [NP.hum, [0.400, 0.750], [0.340, 0.800]] },
        { d: 3, delay: 2050, dur: 530, pts: [NP.hum, [0.600, 0.750], [0.660, 0.800]] },
        { d: 3, delay: 1900, dur: 580, pts: [NP.sm, [0.155, 0.600], [0.110, 0.660]] },
        { d: 3, delay: 1950, dur: 560, pts: [NP.sm, [0.200, 0.610], [0.180, 0.680]] },
        { d: 3, delay: 1900, dur: 580, pts: [NP.sm, [0.240, 0.590], [0.230, 0.660]] },
        { d: 3, delay: 1900, dur: 580, pts: [NP.n, [0.845, 0.600], [0.890, 0.660]] },
        { d: 3, delay: 1950, dur: 560, pts: [NP.n, [0.800, 0.610], [0.820, 0.680]] },
        { d: 3, delay: 1900, dur: 580, pts: [NP.n, [0.760, 0.590], [0.770, 0.660]] },
        { d: 3, delay: 1800, dur: 550, pts: [NP.p, [0.080, 0.480], [0.050, 0.540]] },
        { d: 3, delay: 1850, dur: 530, pts: [NP.p, [0.110, 0.500], [0.090, 0.570]] },
        { d: 3, delay: 1800, dur: 550, pts: [NP.at, [0.920, 0.480], [0.950, 0.540]] },
        { d: 3, delay: 1850, dur: 530, pts: [NP.at, [0.890, 0.500], [0.910, 0.570]] },
        { d: 3, delay: 2200, dur: 500, pts: [NP.lux, [0.500, 0.930], [0.500, 0.980]] },
        { d: 3, delay: 2200, dur: 500, pts: [NP.lux, [0.478, 0.935], [0.465, 0.988]] },
        { d: 3, delay: 2200, dur: 500, pts: [NP.lux, [0.522, 0.935], [0.535, 0.988]] },
      ];
    }

    function resize() {
      // Re-read DPR on every resize — browser zoom changes this value
      currentDPR = window.devicePixelRatio || 1;
      const r = wrap.getBoundingClientRect();
      CW = r.width;
      CH = Math.max(420, Math.round(window.innerHeight * 0.52));
      canvas.width = CW * currentDPR;
      canvas.height = CH * currentDPR;
      canvas.style.width = CW + 'px';
      canvas.style.height = CH + 'px';
      // Reset the transform matrix before applying the new scale —
      // without this, ctx.scale() stacks on each resize/zoom and the
      // canvas content shifts offscreen (appears white / frozen).
      ctx.setTransform(currentDPR, 0, 0, currentDPR, 0, 0);
    }

    function initBranches() {
      BRANCHES = defineBranches().map((b) => {
        const px = b.pts.map(([nx, ny]) => ({ x: nx * CW, y: ny * CH }));
        const sp = buildSpline(px, 80);
        return { ...b, spline: sp, lens: arcLen(sp) };
      });
    }

    function positionNodes() {
      document.querySelectorAll('.snode').forEach((el) => {
        const nx = parseFloat(el.dataset.x);
        const ny = parseFloat(el.dataset.y);
        el.style.left = nx * CW + 'px';
        el.style.top = ny * CH + 'px';
      });
      const sl = document.getElementById('surfaceLine');
      const sll = document.getElementById('surfaceLbl');
      const r = wrap.getBoundingClientRect();
      const heroTop = document.querySelector('.hero').getBoundingClientRect().top;
      const wrapTop = r.top - heroTop;
      if (sl) sl.style.top = wrapTop + 2 + 'px';
      if (sll) sll.style.top = wrapTop + 8 + 'px';
    }

    const NODE_SHOW = {
      'sn-ph': 800, 'sn-sm': 1000, 'sn-n': 1000,
      'sn-k': 1350, 'sn-p': 1250, 'sn-st': 1350, 'sn-at': 1250,
      'sn-hum': 1700, 'sn-lux': 2000,
    };

    function scheduleNodes() {
      Object.entries(NODE_SHOW).forEach(([id, ms]) => {
        setTimeout(() => {
          const el = document.getElementById(id);
          if (el) el.classList.add('show');
        }, ms + 600);
      });
    }

    const easeOut3 = (t) => 1 - Math.pow(1 - t, 3);

    function drawBranch(b, progress) {
      if (progress <= 0 || !b.spline.length) return;
      const sp = b.spline, lens = b.lens;
      const total = lens[lens.length - 1];
      const tgt = total * Math.min(1, progress);
      let endIdx = sp.length - 1;
      for (let i = 1; i < lens.length; i++) {
        if (lens[i] >= tgt) { endIdx = i; break; }
      }
      const d = b.d;
      const lw = [2.2, 1.3, 0.75, 0.38][d] || 0.35;
      const a = [0.52, 0.36, 0.22, 0.11][d] || 0.09;
      const s0 = sp[0], se = sp[endIdx];
      const g = ctx.createLinearGradient(s0.x, s0.y, se.x, se.y);
      g.addColorStop(0, `rgba(${BR},${BG},${BB},${Math.min(1, a * 1.8)})`);
      g.addColorStop(0.3, `rgba(${BR},${BG},${BB},${a * 1.3})`);
      g.addColorStop(0.7, `rgba(${BR},${BG},${BB},${a * 0.8})`);
      g.addColorStop(1, `rgba(${BR},${BG},${BB},${a * 0.28})`);
      ctx.beginPath();
      ctx.moveTo(sp[0].x, sp[0].y);
      for (let i = 1; i <= endIdx; i++) ctx.lineTo(sp[i].x, sp[i].y);
      ctx.strokeStyle = g;
      ctx.lineWidth = lw;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();
      if (d === 0 && progress > 0.5) {
        ctx.beginPath();
        ctx.moveTo(sp[0].x, sp[0].y);
        for (let i = 1; i <= endIdx; i++) ctx.lineTo(sp[i].x, sp[i].y);
        ctx.strokeStyle = `rgba(${BR},${BG},${BB},${0.04 * Math.min(1, progress)})`;
        ctx.lineWidth = lw * 4.5;
        ctx.stroke();
      }
    }

    function spawnPulse(ts) {
      if (ts - lastPulse < 950) return;
      lastPulse = ts;
      const cands = BRANCHES.filter((b) => b.d <= 2 && b.spline.length > 6);
      if (!cands.length) return;
      const b = cands[Math.floor(Math.random() * cands.length)];
      pulses.push({ b, born: ts, life: 1400 + Math.random() * 500 });
    }

    function drawPulses(ts) {
      pulses = pulses.filter((p) => ts - p.born < p.life);
      pulses.forEach((p) => {
        const t = (ts - p.born) / p.life;
        const sp = p.b.spline, lens = p.b.lens;
        const total = lens[lens.length - 1], tgt = total * t;
        let idx = 0;
        for (let i = 1; i < lens.length; i++) {
          if (lens[i] >= tgt) { idx = i; break; }
        }
        const pt = sp[idx] || sp[sp.length - 1];
        const fade = t < 0.12 ? t / 0.12 : t > 0.8 ? (1 - t) / 0.2 : 1;
        ctx.beginPath(); ctx.arc(pt.x, pt.y, 2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${PR},${PG},${PB},${0.88 * fade})`; ctx.fill();
        ctx.beginPath(); ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${PR},${PG},${PB},${0.12 * fade})`; ctx.fill();
      });
    }

    function buildSoilPts() {
      soilPts = [];
      let s = 99;
      const lcg = (v) => { v = (1664525 * v + 1013904223) & 0xffffffff; return v / 0xffffffff; };
      for (let i = 0; i < 350; i++) {
        const nx = lcg((s += 1));
        const ny = 0.06 + lcg((s += 1)) * 0.94;
        soilPts.push([nx, ny]);
      }
    }

    function drawSoil(alpha) {
      if (!soilPts || alpha <= 0) return;
      soilPts.forEach(([nx, ny]) => {
        if (ny < 0.08) return;
        const d = ny;
        ctx.beginPath();
        ctx.arc(nx * CW, ny * CH, 0.6, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${SR},${SG},${SB},${alpha * (0.12 + d * 0.72)})`;
        ctx.fill();
      });
    }

    function drawSeed(ts) {
      const pulse = (Math.sin(ts * 0.0012) + 1) * 0.5;
      const sx = NP.seed[0] * CW, sy = 0;
      ctx.beginPath(); ctx.arc(sx, sy, 6 + pulse * 4, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${SDR},${SDG},${SDB},${0.04 + pulse * 0.06})`; ctx.fill();
    }

    function render(ts) {
      if (!running) return;
      if (!animStart) animStart = ts;
      const el = ts - animStart - 400;
      ctx.clearRect(0, 0, CW, CH);
      if (el > 2400) drawSoil(Math.min(1, (el - 2400) / 1200) * 0.025);
      BRANCHES.forEach((b) => {
        if (el < b.delay) return;
        const t = Math.min(1, (el - b.delay) / b.dur);
        drawBranch(b, easeOut3(t));
      });
      if (el > 2600) { spawnPulse(ts); drawPulses(ts); }
      drawSeed(ts);
      rafId = requestAnimationFrame(render);
    }

    function init() {
      resize();
      buildSoilPts();
      initBranches();
      positionNodes();
      scheduleNodes();
      rafId = requestAnimationFrame(render);
    }

    init();

    const handleResize = () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        resize();
        initBranches();
        positionNodes();
        pulses = [];
      }, 100);
    };

    window.addEventListener('resize', handleResize);
    return () => {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
      clearTimeout(resizeTimer);
      window.removeEventListener('resize', handleResize);
    };
    // Re-run when title strings or the active locale change so the
    // animation re-renders with the new content + grapheme rules.
  }, [titleBefore, titleAccent, titleAfter, locale]);

  return (
    <section className="hero">
      <div className="hero-grid"></div>

      {/* Text block */}
      <div className="hero-text-block">
        <h1 className="hero-title" id="heroTitle"></h1>
        <p className="hero-desc">{t('description')}</p>
        <div className="hero-actions">
          {/* CTAs intentionally commented; uncomment when ready and
              wire to messages: tCta('launch'), tCta('demo') */}
        </div>
      </div>

      {/* Surface line */}
      <div className="surface-line" id="surfaceLine"></div>
      <div className="surface-lbl" id="surfaceLbl">{t('surfaceLabel')}</div>

      {/* Root canvas */}
      <div className="root-canvas-wrap" id="rootWrap">
        <canvas id="rootCanvas"></canvas>

        {/* Ledger account nodes — the root canvas reads as the chart of
            accounts tree. Numeric balances are sample data, not copy, so
            they are not translated. Labels are. */}
        <div className="snode lg" id="sn-ph" data-x="0.50" data-y="0.32">
          <span className="snode-sym">AR</span>
          <span className="snode-val">₹12.4L</span>
          <span className="snode-lbl">{tSensors('debtors')}</span>
          <div className="snode-dot"></div>
        </div>
        <div className="snode lg" id="sn-sm" data-x="0.22" data-y="0.52">
          <span className="snode-sym">AP</span>
          <span className="snode-val">₹8.2L</span>
          <span className="snode-lbl">{tSensors('creditors')}</span>
          <div className="snode-dot"></div>
        </div>
        <div className="snode lg" id="sn-n" data-x="0.78" data-y="0.52">
          <span className="snode-sym">IN</span>
          <span className="snode-val">₹24.6L</span>
          <span className="snode-lbl">{tSensors('salesIncome')}</span>
          <div className="snode-dot"></div>
        </div>
        <div className="snode md" id="sn-p" data-x="0.13" data-y="0.44">
          <span className="snode-sym">EX</span>
          <span className="snode-val">₹9.8L</span>
          <span className="snode-lbl">{tSensors('purchaseExpense')}</span>
        </div>
        <div className="snode md" id="sn-k" data-x="0.37" data-y="0.44">
          <span className="snode-sym">CA</span>
          <span className="snode-val">₹3.1L</span>
          <span className="snode-lbl">{tSensors('cash')}</span>
        </div>
        <div className="snode md" id="sn-st" data-x="0.63" data-y="0.44">
          <span className="snode-sym">BK</span>
          <span className="snode-val">₹15.7L</span>
          <span className="snode-lbl">{tSensors('bank')}</span>
        </div>
        <div className="snode md" id="sn-at" data-x="0.87" data-y="0.44">
          <span className="snode-sym">TX</span>
          <span className="snode-val">18%</span>
          <span className="snode-lbl">{tSensors('outputTax')}</span>
        </div>
        <div className="snode sm" id="sn-hum" data-x="0.50" data-y="0.72">
          <span className="snode-sym">EQ</span>
          <span className="snode-val">₹22L</span>
          <span className="snode-lbl">{tSensors('capital')}</span>
        </div>
        <div className="snode sm" id="sn-lux" data-x="0.50" data-y="0.88">
          <span className="snode-sym"><Scale size={14} /></span>
          <span className="snode-val">0.00</span>
          <span className="snode-lbl">{tSensors('variance')}</span>
        </div>
      </div>

      {/* Stats bar */}
      <div className="hero-stats">
        <div className="stat-card">
          <span className="stat-num">100%</span>
          <span className="stat-label">{tStats('balancedEntries')}</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">70%</span>
          <span className="stat-label">{tStats('fasterClose')}</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">3×</span>
          <span className="stat-label">{tStats('reportSpeed')}</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">50K+</span>
          <span className="stat-label">{tStats('entriesPosted')}</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">&lt;200ms</span>
          <span className="stat-label">{tStats('response')}</span>
        </div>
      </div>
    </section>
  );
}