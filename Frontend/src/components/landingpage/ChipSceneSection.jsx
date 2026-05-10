import { useEffect, useRef } from "react";

const VW = 1400;
const VH = 500;

// Chip: x=570 y=155 w=260 h=140  → right=830, bottom=295, centerX=700
// 6 top/bottom pin centers spaced 30px, centered at 700:
//   625, 655, 685, 715, 745, 775
// Active (path-connected): 625, 655, 715, 775  →  empty: 685, 745

const CHIP = { x: 570, y: 155, w: 260, h: 140 };

const MODULES = [
    // ── LEFT ────────────────────────────────────────────────────────────────
    {
        id: "soil", label: "SOIL AI", dir: "in", color: [74, 222, 128],
        pts: [[40, 90], [460, 90], [460, 167], [570, 167]], delay: 0, dur: 6.0
    },
    {
        id: "irrigation", label: "IRRIGATION", dir: "out", color: [108, 99, 255],
        pts: [[570, 183], [100, 183], [100, 148], [40, 148]], delay: 1.6, dur: 7.0
    },
    {
        id: "pest", label: "PEST CNNs", dir: "in", color: [224, 64, 251],
        pts: [[40, 230], [460, 230], [460, 199], [570, 199]], delay: 0.8, dur: 6.5
    },
    {
        id: "crop", label: "CROP REC", dir: "out", color: [255, 152, 0],
        pts: [[570, 215], [110, 215], [110, 310], [40, 310]], delay: 2.4, dur: 7.2
    },

    // ── TOP — paths land at pin centers 625,655,715,775 at y=155 ────────────
    {
        id: "nextjs", label: "NEXT.JS", dir: "in", color: [226, 232, 240],
        pts: [[460, 22], [460, 95], [625, 95], [625, 155]], delay: 0.3, dur: 5.8
    },
    {
        id: "fastapi", label: "FASTAPI", dir: "out", color: [34, 211, 238],
        pts: [[655, 155], [655, 22]], delay: 1.4, dur: 5.5
    },
    {
        id: "tensorflow", label: "TensorFlow", dir: "in", color: [248, 113, 113],
        pts: [[860, 22], [860, 80], [715, 80], [715, 155]], delay: 2.2, dur: 6.2
    },
    {
        id: "nextapi", label: "NEXT·API", dir: "in", color: [148, 163, 184],
        pts: [[1040, 22], [1040, 60], [775, 60], [775, 155]], delay: 3.2, dur: 6.4
    },

    // ── BOTTOM — paths land at pin centers 625,655,715,775 at y=295 ─────────
    {
        id: "python", label: "PYTHON", dir: "in", color: [56, 189, 248],
        pts: [[150, 478], [150, 360], [625, 360], [625, 295]], delay: 0.5, dur: 7.2
    },
    {
        id: "lstm", label: "LSTM", dir: "in", color: [251, 146, 60],
        pts: [[340, 478], [340, 400], [655, 400], [655, 295]], delay: 1.8, dur: 6.6
    },
    {
        id: "cnn", label: "CNN", dir: "in", color: [167, 139, 250],
        pts: [[715, 478], [715, 295]], delay: 2.8, dur: 5.8
    },
    {
        id: "transformers", label: "TRANSFORMERS", dir: "in", color: [192, 132, 252],
        pts: [[980, 478], [980, 380], [775, 380], [775, 295]], delay: 3.8, dur: 6.8
    },

    // ── RIGHT ────────────────────────────────────────────────────────────────
    {
        id: "yield", label: "YIELD LSTM", dir: "in", color: [74, 222, 128],
        pts: [[1360, 130], [1050, 130], [1050, 167], [830, 167]], delay: 0.9, dur: 7.0
    },
    {
        id: "market", label: "MARKET AI", dir: "out", color: [244, 114, 182],
        pts: [[830, 183], [1360, 183]], delay: 2.0, dur: 6.4
    },
    {
        id: "growth", label: "GROWTH MON", dir: "in", color: [52, 211, 153],
        pts: [[1360, 290], [1180, 290], [1180, 199], [830, 199]], delay: 1.4, dur: 6.8
    },
    {
        id: "kubernetes", label: "KUBERNETES", dir: "in", color: [96, 165, 250],
        pts: [[1360, 400], [1100, 400], [1100, 215], [830, 215]], delay: 3.4, dur: 7.5
    },
];

// 6 pin centers: 625 655 685 715 745 775  (span=150, centered at 700)
const PIN_W = 12;
const PIN_H = 16;
const TOP_BOT_PIN_CENTERS = [625, 655, 685, 715, 745, 775];
const ACTIVE_PIN_CENTERS = new Set([625, 655, 715, 775]); // 685, 745 are empty
const TOP_PIN_Y = 155 - PIN_H; // 139 — flush above chip top edge y=155
const BOT_PIN_Y = 295;         // flush below chip bottom edge y=295

function buildPath(pts) {
    const segs = [];
    let total = 0;
    for (let i = 1; i < pts.length; i++) {
        const dx = pts[i][0] - pts[i - 1][0];
        const dy = pts[i][1] - pts[i - 1][1];
        const len = Math.sqrt(dx * dx + dy * dy);
        segs.push({ x0: pts[i - 1][0], y0: pts[i - 1][1], x1: pts[i][0], y1: pts[i][1], len, start: total });
        total += len;
    }
    return { segs, total };
}

function pointAt(path, t) {
    const d = Math.max(0, Math.min(path.total, t));
    for (const seg of path.segs) {
        if (d <= seg.start + seg.len) {
            const r = (d - seg.start) / seg.len;
            return [seg.x0 + r * (seg.x1 - seg.x0), seg.y0 + r * (seg.y1 - seg.y0)];
        }
    }
    const last = path.segs[path.segs.length - 1];
    return [last.x1, last.y1];
}

function chipOcclusion(x, y) {
    const pad = 20;
    const cx = CHIP.x - pad, cy = CHIP.y - pad;
    const cw = CHIP.w + pad * 2, ch = CHIP.h + pad * 2;
    if (x < cx || x > cx + cw || y < cy || y > cy + ch) return 0;
    const dx = Math.min(x - cx, cx + cw - x) / pad;
    const dy = Math.min(y - cy, cy + ch - y) / pad;
    return Math.min(Math.min(dx, dy, 1), 1) * 0.82;
}

export default function ChipSceneSection() {
    const canvasRef = useRef(null);
    const svgRef = useRef(null);
    const rafRef = useRef(null);

    const paths = MODULES.map(m => buildPath(m.pts));

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        let startTime = null;

        function drawHead(ctx, x, y, r, g, b, alpha) {
            const halo = ctx.createRadialGradient(x, y, 0, x, y, 4);
            halo.addColorStop(0, `rgba(${r},${g},${b},${alpha * 0.35})`);
            halo.addColorStop(0.6, `rgba(${r},${g},${b},${alpha * 0.08})`);
            halo.addColorStop(1, `rgba(${r},${g},${b},0)`);
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, Math.PI * 2);
            ctx.fillStyle = halo;
            ctx.fill();

            ctx.beginPath();
            ctx.arc(x, y, 1.4, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(255,255,255,${alpha * 0.92})`;
            ctx.fill();

            ctx.beginPath();
            ctx.arc(x, y, 0.8, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
            ctx.fill();
        }

        function drawFrame(ts) {
            if (!startTime) startTime = ts;
            const elapsed = (ts - startTime) / 1000;

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            MODULES.forEach((m, i) => {
                const path = paths[i];
                const [r, g, b] = m.color;

                const raw = (elapsed - m.delay) % m.dur;
                if (raw < 0) return;
                const cycleT = raw / m.dur;

                const headDist = cycleT * (path.total + 180) - 60;
                const tailLen = 160;

                let envAlpha = 1;
                if (cycleT < 0.08) envAlpha = cycleT / 0.08;
                else if (cycleT > 0.90) envAlpha = (1 - cycleT) / 0.10;
                envAlpha = Math.max(0, Math.min(1, envAlpha));
                if (envAlpha < 0.01) return;

                const STEPS = 36;
                ctx.lineCap = "round";
                ctx.lineJoin = "round";

                for (let s = 0; s < STEPS - 1; s++) {
                    const tNorm0 = s / (STEPS - 1);
                    const tNorm1 = (s + 1) / (STEPS - 1);

                    const dist0 = headDist - tailLen * (1 - tNorm0);
                    const dist1 = headDist - tailLen * (1 - tNorm1);

                    if (dist1 < -10 || dist0 > path.total + 10) continue;

                    const [px, py] = pointAt(path, dist0);
                    const [nx, ny] = pointAt(path, dist1);

                    const occ0 = chipOcclusion(px, py);
                    const occ1 = chipOcclusion(nx, ny);
                    const depth = 1 - (occ0 + occ1) * 0.5;

                    const trailAlpha = Math.pow(tNorm0, 2.2);
                    const flicker = tNorm0 > 0.3 && tNorm0 < 0.85
                        ? 0.88 + 0.12 * Math.sin(elapsed * 12 + dist0 * 0.04 + i * 1.3)
                        : 1.0;

                    const alpha = trailAlpha * envAlpha * depth * flicker;
                    if (alpha < 0.004) continue;

                    ctx.beginPath();
                    ctx.moveTo(px, py);
                    ctx.lineTo(nx, ny);
                    ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
                    ctx.lineWidth = 1.5;
                    ctx.stroke();

                    if (tNorm0 > 0.82) {
                        const softA = (tNorm0 - 0.82) / 0.18 * alpha * 0.15;
                        ctx.beginPath();
                        ctx.moveTo(px, py);
                        ctx.lineTo(nx, ny);
                        ctx.strokeStyle = `rgba(${r},${g},${b},${softA})`;
                        ctx.lineWidth = 3.0;
                        ctx.stroke();
                    }
                }

                const headClamp = Math.max(0, Math.min(path.total, headDist));
                const [hx, hy] = pointAt(path, headClamp);
                const headOcc = chipOcclusion(hx, hy);
                const headVis = (1 - headOcc) * envAlpha;
                if (headVis > 0.04 && headDist >= -8 && headDist <= path.total + 8) {
                    drawHead(ctx, hx, hy, r, g, b, headVis);
                }
            });

            rafRef.current = requestAnimationFrame(drawFrame);
        }

        rafRef.current = requestAnimationFrame(drawFrame);
        return () => cancelAnimationFrame(rafRef.current);
    }, []);

    // Left/right pins: centered on path y endpoints
    const LR_PIN_W = 18;
    const LR_PIN_H = 10;
    const lrPinYs = [167, 183, 199, 215];

    return (
        <>
            <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Sora:wght@300;400;600&display=swap');

        .chip-scene-section-chipsection {
          background: #131313ff;
          padding: 60px 0 72px;
          position: relative;
          overflow: hidden;
                    background-image:
            linear-gradient(to right, rgba(22, 22, 22, 0.85) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(22,22,22,0.85) 1px, transparent 1px);
          background-size: 40px 40px;
          background-position: 40px 40px;
        }

        .chip-scene-section-chipsection .chip-scene-container-chipsection { max-width:960px; margin:0 auto; padding:0 24px; }
        .chip-scene-section-chipsection .chip-scene-header-chipsection  { text-align:center; margin-bottom:40px; }
        .chip-scene-section-chipsection .section-eyebrow-chipsection {
          font-family:'Orbitron',monospace; font-size:11px; font-weight:600;
          letter-spacing:4px; color:#4ade80; text-transform:uppercase; margin-bottom:16px;
        }
        .chip-scene-section-chipsection .section-title-chipsection {
          font-family:'Orbitron',monospace;
          font-size:clamp(20px,3vw,32px); font-weight:900;
          color:#e0e0e0; line-height:1.2; margin:0 0 14px; letter-spacing:1px;
        }
        .chip-scene-section-chipsection .text-green-chipsection { color:#4ade80; }
        .chip-scene-section-chipsection .section-sub-chipsection {
          font-family:'Sora',sans-serif; font-size:14px; color:#666;
          max-width:500px; margin:0 auto; line-height:1.7; font-weight:300;
        }

        /* ── Card wrapper — same bg as section ── */
        .chip-scene-section-chipsection .chip-scene-wrap-chipsection {
          width:100%; border-radius:16px;
          background-color: #13131300;
        //   background-image:
        //     linear-gradient(to right, rgba(22, 22, 22, 0.85) 1px, transparent 1px),
        //     linear-gradient(to bottom, rgba(22,22,22,0.85) 1px, transparent 1px);
        //   background-size: 40px 40px;
        //   background-position: 40px 40px;
          position:relative; overflow:visible;
          padding: 24px 0;
        }

        .chip-scene-section-chipsection .chip-scene-inner-chipsection { position:relative; width:100%; z-index:1; }
        .chip-scene-section-chipsection .chip-canvas-chipsection {
          position:absolute; inset:0; width:100%; height:100%; pointer-events:none; z-index:2;
        }
        .chip-scene-section-chipsection .chip-svg-layer-chipsection { display:block; width:100%; height:auto; position:relative; z-index:1; }

        .filter-container {
          width: 100%;
          height: 100%;
          position: absolute;
          inset: 0;
          pointer-events: none;
          z-index: 3;
          border-radius: 16px;
        }
      `}</style>

            <section className="chip-scene-section-chipsection" id="poweredby">
                <div className="chip-scene-container-chipsection">
                    <div className="chip-scene-header-chipsection">
                        <div className="section-eyebrow-chipsection">Core Architecture</div>
                        <h2 className="section-title-chipsection">
                            The <span className="text-green-chipsection">Neural Core</span>
                            <br />Driving Every Decision
                        </h2>
                        <p className="section-sub-chipsection">
                            FarmXpert's multi-agent processor — sixteen specialized AI modules on a single
                            intelligent substrate, routing real-time farm intelligence at sub-200ms latency.
                        </p>
                    </div>



                    <div className="chip-scene-wrap-chipsection">
                        <div className="filter-container"></div>
                        <div className="chip-scene-inner-chipsection" style={{ aspectRatio: `${VW}/${VH}` }}>

                            <canvas ref={canvasRef} className="chip-canvas-chipsection" width={VW} height={VH} />

                            <svg
                                ref={svgRef}
                                className="chip-svg-layer-chipsection"
                                viewBox={`0 0 ${VW} ${VH}`}
                                xmlns="http://www.w3.org/2000/svg"
                            >
                                <defs>
                                    <clipPath id="chipClip">
                                        <rect x="570" y="155" width="260" height="140" rx="12" />
                                    </clipPath>
                                    <linearGradient id="shineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
                                        <stop offset="40%" stopColor="#ffffff" stopOpacity="0.04" />
                                        <stop offset="50%" stopColor="#ffffff" stopOpacity="0.13" />
                                        <stop offset="60%" stopColor="#ffffff" stopOpacity="0.04" />
                                        <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
                                    </linearGradient>
                                    <linearGradient id="leftGlowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" stopColor="#2e2e2e" stopOpacity="0.05" />
                                        <stop offset="10%" stopColor="#2a2a2a" stopOpacity="0.14" />
                                        <stop offset="24%" stopColor="#222222" stopOpacity="0.20" />
                                        <stop offset="42%" stopColor="#1a1a1a" stopOpacity="0.12" />
                                        <stop offset="60%" stopColor="#121212" stopOpacity="0.06" />
                                        <stop offset="100%" stopColor="#080808" stopOpacity="0" />
                                    </linearGradient>

                                    <linearGradient id="bgGrad2" x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" stopColor="#0e0e0e" />
                                        <stop offset="100%" stopColor="#0a0a0a" />
                                    </linearGradient>
                                    <linearGradient id="chipGrad2" x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" stopColor="#353535" />
                                        <stop offset="25%" stopColor="#2a2a2c" />
                                        <stop offset="50%" stopColor="#1f2020" />
                                        <stop offset="75%" stopColor="#191a1a" />
                                        <stop offset="100%" stopColor="#131414" />
                                    </linearGradient>
                                    <linearGradient id="chipSheen2" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" stopColor="#404040" stopOpacity="0" />
                                        <stop offset="40%" stopColor="#484848" stopOpacity="0.5" />
                                        <stop offset="60%" stopColor="#484848" stopOpacity="0.5" />
                                        <stop offset="100%" stopColor="#404040" stopOpacity="0" />
                                    </linearGradient>
                                    <radialGradient id="chipAura" cx="50%" cy="50%" r="50%">
                                        <stop offset="0%" stopColor="#0d0d0d" stopOpacity="0.92" />
                                        <stop offset="100%" stopColor="#0d0d0d" stopOpacity="0" />
                                    </radialGradient>
                                </defs>

                                <rect width={VW} height={VH} fill="transparent" />

                                {/* Static traces */}
                                <g fill="none" stroke="#272727" strokeWidth="1.3"
                                    strokeLinecap="round" strokeLinejoin="round">
                                    {MODULES.map(m => {
                                        const d = m.pts.map((p, j) => `${j === 0 ? 'M' : 'L'} ${p[0]},${p[1]}`).join(' ');
                                        return <path key={`st-${m.id}`} d={d} />;
                                    })}
                                </g>

                                {/* Chip body */}
                                <rect x="570" y="155" width="260" height="140" rx="12" fill="url(#chipGrad2)" />
                                <rect x="570" y="155" width="260" height="6" rx="3" fill="url(#chipSheen2)" />
                                <rect x="570" y="155" width="260" height="140" rx="12"
                                    fill="none" stroke="#2e2e2e" strokeWidth="1.3" />
                                <rect x="580" y="165" width="240" height="120" rx="8"
                                    fill="none" stroke="#1e1e1e" strokeWidth="0.8" />
                                {/* ── Shine sweep: right → left ── */}
                                <g clipPath="url(#chipClip)">
                                    <rect y="155" width="90" height="140" fill="url(#shineGrad)"
                                        transform="skewX(-10)">
                                        <animateTransform attributeName="transform" type="translate"
                                            values="400,0; -150,0" additive="sum"
                                            dur="3.8s" repeatCount="indefinite" calcMode="spline"
                                            keySplines="0.4 0 0.6 1" />
                                    </rect>
                                </g>

                                {/* ── Glow pulse: sweeps right → left at angle ── */}
                                <g clipPath="url(#chipClip)">
                                    <rect x="570" y="155" width="80" height="140" fill="url(#leftGlowGrad)"
                                        opacity="0.42" transform="skewX(-12)">
                                        <animateTransform attributeName="transform" type="translate"
                                            values="340,0; -120,0" additive="sum"
                                            dur="2.6s" repeatCount="indefinite" begin="1.2s"
                                            calcMode="spline" keySplines="0.25 0 0.6 1" />
                                    </rect>
                                </g>

                                <ellipse cx="700" cy="225" rx="160" ry="90" fill="url(#chipAura)" opacity="0" />

                                <g stroke="#252525" strokeWidth="0.8" opacity="0" fill="none">
                                    <line x1="630" y1="170" x2="630" y2="285" />
                                    <line x1="770" y1="170" x2="770" y2="285" />
                                    <line x1="572" y1="210" x2="828" y2="210" />
                                    <rect x="640" y="175" width="22" height="14" rx="2" fill="#181818" stroke="#282828" />
                                    <rect x="738" y="175" width="22" height="14" rx="2" fill="#181818" stroke="#282828" />
                                    <rect x="668" y="218" width="64" height="34" rx="3" fill="#141414" stroke="#242424" />
                                    <line x1="675" y1="228" x2="725" y2="228" stroke="#1d1d1d" />
                                    <line x1="675" y1="237" x2="725" y2="237" stroke="#1d1d1d" />
                                    <line x1="675" y1="246" x2="725" y2="246" stroke="#1d1d1d" />
                                </g>

                                <g stroke="#333" strokeWidth="1.1" fill="none">
                                    <path d="M582 166 L594 166 M582 166 L582 178" />
                                    <path d="M818 166 L806 166 M818 166 L818 178" />
                                    <path d="M582 284 L594 284 M582 284 L582 272" />
                                    <path d="M818 284 L806 284 M818 284 L818 272" />
                                </g>

                                {/* ── TOP PINS ── 6 pins, centers at 625 655 685 715 745 775
                     rect x = center − 6,  y = 139 (flush above chip top y=155)
                     active: 625 655 715 775  |  empty (darker): 685 745        */}
                                <g strokeWidth="0.7">
                                    {TOP_BOT_PIN_CENTERS.map((cx, i) => {
                                        const active = ACTIVE_PIN_CENTERS.has(cx);
                                        return (
                                            <rect key={`tp${i}`}
                                                x={cx - PIN_W / 2} y={TOP_PIN_Y}
                                                width={PIN_W} height={PIN_H} rx="2"
                                                fill={active ? "#2e2e2e" : "#181818"}
                                                stroke="#181818">
                                                {active && (
                                                    <animate attributeName="fill"
                                                        values="#2e2e2e;#3a3a3a;#2e2e2e" dur="3s"
                                                        repeatCount="indefinite" begin={`${i * 0.32}s`} />
                                                )}
                                            </rect>
                                        );
                                    })}
                                </g>

                                {/* ── BOTTOM PINS ── same 6 centers, y=295 (flush below chip bottom) */}
                                <g strokeWidth="0.7">
                                    {TOP_BOT_PIN_CENTERS.map((cx, i) => {
                                        const active = ACTIVE_PIN_CENTERS.has(cx);
                                        return (
                                            <rect key={`bp${i}`}
                                                x={cx - PIN_W / 2} y={BOT_PIN_Y}
                                                width={PIN_W} height={PIN_H} rx="2"
                                                fill={active ? "#2e2e2e" : "#181818"}
                                                stroke="#181818">
                                                {active && (
                                                    <animate attributeName="fill"
                                                        values="#2e2e2e;#3a3a3a;#2e2e2e" dur="2.8s"
                                                        repeatCount="indefinite" begin={`${i * 0.38}s`} />
                                                )}
                                            </rect>
                                        );
                                    })}
                                </g>

                                {/* ── LEFT PINS ── 4, centered on path y endpoints */}
                                <g strokeWidth="0.7">
                                    {lrPinYs.map((py, i) => (
                                        <rect key={`lp${i}`}
                                            x={570 - LR_PIN_W} y={py - LR_PIN_H / 2}
                                            width={LR_PIN_W} height={LR_PIN_H} rx="2"
                                            fill="#2e2e2e" stroke="#181818">
                                            <animate attributeName="fill" values="#2e2e2e;#3a3a3a;#2e2e2e"
                                                dur="3.2s" repeatCount="indefinite" begin={`${i * 0.5}s`} />
                                        </rect>
                                    ))}
                                </g>

                                {/* ── RIGHT PINS ── 4, centered on path y endpoints */}
                                <g strokeWidth="0.7">
                                    {lrPinYs.map((py, i) => (
                                        <rect key={`rp${i}`}
                                            x={830} y={py - LR_PIN_H / 2}
                                            width={LR_PIN_W} height={LR_PIN_H} rx="2"
                                            fill="#2e2e2e" stroke="#181818">
                                            <animate attributeName="fill" values="#2e2e2e;#3a3a3a;#2e2e2e"
                                                dur="3.2s" repeatCount="indefinite" begin={`${i * 0.5 + 0.2}s`} />
                                        </rect>
                                    ))}
                                </g>

                                {/* Status LED */}
                                <circle cx="582" cy="167" r="4" fill="#4ade80" opacity="0.25">
                                    <animate attributeName="opacity" values="0.12;0.7;0.12" dur="2.4s" repeatCount="indefinite" />
                                    <animate attributeName="r" values="3;5;3" dur="2.4s" repeatCount="indefinite" />
                                </circle>
                                <circle cx="582" cy="167" r="8" fill="#4ade80" opacity="0.04">
                                    <animate attributeName="opacity" values="0.02;0.1;0.02" dur="2.4s" repeatCount="indefinite" />
                                </circle>

                                {/* Chip text */}
                                <text x="700" y="204" textAnchor="middle"
                                    fontFamily="'Orbitron',monospace" fontSize="10" fontWeight="600"
                                    fill="#3a3a3a" letterSpacing="5">POWERED BY</text>
                                <text x="700" y="236" textAnchor="middle"
                                    fontFamily="'Orbitron',monospace" fontSize="22" fontWeight="900"
                                    fill="#cccccc" letterSpacing="1">
                                    Farm<tspan fill="#4ade80">X</tspan>pert
                                </text>
                                <text x="700" y="258" textAnchor="middle"
                                    fontFamily="'Sora',sans-serif" fontSize="8" fontWeight="300"
                                    fill="#363636" letterSpacing="6">MULTI-AGENT AI CORE</text>

                                {/* Module labels */}
                                <g fontFamily="'Orbitron',monospace" fontSize="12" fill="#525252" letterSpacing="1">
                                    <text x="44" y="86" >SOIL AI</text>
                                    <text x="44" y="144">IRRIGATION</text>
                                    <text x="44" y="226">PEST CNNs</text>
                                    <text x="44" y="307">CROP REC</text>
                                    <text x="420" y="16" >NEXT.JS</text>
                                    <text x="612" y="16" >FASTAPI</text>
                                    <text x="812" y="16" >TensorFlow</text>
                                    <text x="990" y="16" >NEXT·API</text>
                                    <text x="110" y="492">PYTHON</text>
                                    <text x="300" y="492">LSTM</text>
                                    <text x="692" y="492">CNN</text>
                                    <text x="900" y="492">TRANSFORMERS</text>
                                    <text x="1190" y="126">YIELD LSTM</text>
                                    <text x="1240" y="179">MARKET AI</text>
                                    <text x="1190" y="286">GROWTH MON</text>
                                    <text x="1190" y="396">KUBERNETES</text>
                                </g>
                            </svg>
                        </div>
                    </div>
                </div>
            </section>
        </>
    );
}