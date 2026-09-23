// ============================================================
// FILE: src/components/dashboard/SidebarVine.jsx
//
// Three short climbers for the sidebar, in the greeting card's forest
// green, placed as a set: one hangs from the top-right, one rises at
// the bottom-right, one rises at the bottom-left.
//
// Each is a straight, chain-linked stem with nodes, paired leaves and a
// curling tendril with a bud at the tip. Leaves are drawn in detail:
// two-tone blades split along a curved midrib (lit upper half, shaded
// lower half), a rim highlight, and four pairs of arching side veins.
// Drawn at 1:1 pixel scale so every line stays crisp.
// ============================================================

// One leaf pointing along +x, length s. Slightly asymmetric, like a real blade.
function Leaf({ s, uid }) {
  const tip = `${(s * 1.3).toFixed(2)} ${(-s * 0.04).toFixed(2)}`;
  const upper = `M0 0 C ${s * 0.18} ${-s * 0.62}, ${s * 0.95} ${-s * 0.6}, ${tip} Q ${s * 0.66} ${-s * 0.06}, 0 0 Z`;
  const lower = `M0 0 Q ${s * 0.66} ${-s * 0.06}, ${tip} C ${s * 0.98} ${s * 0.52}, ${s * 0.22} ${s * 0.58}, 0 0 Z`;
  const veins = [0.24, 0.44, 0.64, 0.84].map((f) => {
    const x = s * f;
    const y = -s * 0.06 * f;
    const up = s * 0.38 * (1 - Math.abs(f - 0.45) * 1.1);
    const dn = up * 0.9;
    return `M${x.toFixed(2)} ${y.toFixed(2)} Q ${(x + s * 0.08).toFixed(2)} ${(y - up * 0.55).toFixed(2)}, ${(x + s * 0.2).toFixed(2)} ${(y - up).toFixed(2)}`
      + ` M${x.toFixed(2)} ${y.toFixed(2)} Q ${(x + s * 0.08).toFixed(2)} ${(y + dn * 0.55).toFixed(2)}, ${(x + s * 0.2).toFixed(2)} ${(y + dn).toFixed(2)}`;
  }).join(' ');
  return (
    <>
      <path d={`M${(-s * 0.16).toFixed(2)} 0 L0.5 0`} className="fx-leaf-petiole" />
      <path d={upper} fill={`url(#${uid}-lit)`} />
      <path d={lower} fill={`url(#${uid}-shade)`} />
      <path d={`M0 0 C ${s * 0.18} ${-s * 0.62}, ${s * 0.95} ${-s * 0.6}, ${tip}`} className="fx-leaf-rim" />
      <path d={`M0 0 Q ${s * 0.66} ${-s * 0.06}, ${tip}`} className="fx-leaf-midrib" />
      <path d={veins} className="fx-leaf-veins" />
    </>
  );
}

/**
 * A straight climber `length` px long. `grow` is the direction from its
 * base: 'down' hangs from the top, 'up' rises from the bottom.
 */
function Vine({ uid, length, grow, leaves, size, delay, className }) {
  const W = 84;
  const cx = W / 2;
  const up = grow === 'up';
  const baseY = up ? length : 0;
  const dir = up ? -1 : 1;
  const tipY = baseY + dir * (length - 22);
  // The stem as a chain: short capsule links, each a little narrower and
  // turned the other way, so it reads like twisted, jointed growth.
  const LINK = 6.5;
  const span = Math.abs(tipY - baseY);
  const links = Array.from({ length: Math.floor(span / LINK) }, (_, k) => {
    const t = (k * LINK) / span;
    const w = 3.2 - t * 1.8;
    return { y: baseY + dir * (k * LINK + LINK / 2), w, tilt: k % 2 === 0 ? 9 : -9, k };
  });
  const nodes = Array.from({ length: leaves }, (_, i) => {
    const t = (i + 0.7) / (leaves + 0.6);
    const y = baseY + dir * (length - 30) * t;
    const side = i % 2 === 0 ? -1 : 1;
    const s = size * (1.05 - t * 0.4);
    const lift = 30 + (i % 3) * 7;
    // leaves reach away from the base, toward the light
    const angle = side < 0 ? (up ? 180 + lift : 180 - lift) : (up ? -lift : lift);
    return { y, s, angle, i };
  });
  // curling tendril and bud at the tip
  const c = dir;
  const tendril = `M${cx} ${tipY} c -6 ${c * 4}, -7 ${c * 13}, 0 ${c * 15} c 6 ${c * 1.5}, 7 ${c * -5}, 2 ${c * -6} c -3 ${c * -0.6}, -4 ${c * 2}, -1.6 ${c * 3}`;

  return (
    <svg className={`fx-vine ${className}`} width={W} height={length + 8} viewBox={`0 -4 ${W} ${length + 8}`} aria-hidden>
      <defs>
        <linearGradient id={`${uid}-lit`} x1="0" y1="1" x2="0.6" y2="0">
          <stop offset="0" stopColor="#2f7a3e" />
          <stop offset="0.6" stopColor="#4f9a57" />
          <stop offset="1" stopColor="#8cc28a" />
        </linearGradient>
        <linearGradient id={`${uid}-shade`} x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0" stopColor="#1f6a3a" />
          <stop offset="0.7" stopColor="#12502f" />
          <stop offset="1" stopColor="#0b3a22" />
        </linearGradient>
        <linearGradient id={`${uid}-stem`} x1="0" y1={up ? 1 : 0} x2="0" y2={up ? 0 : 1}>
          <stop offset="0" stopColor="#0f4a2e" />
          <stop offset="1" stopColor="#3f8a4c" />
        </linearGradient>
        <linearGradient id={`${uid}-link`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#3f8a4c" />
          <stop offset="0.5" stopColor="#1f6a3a" />
          <stop offset="1" stopColor="#0b3a22" />
        </linearGradient>
        <radialGradient id={`${uid}-bud`} cx="0.35" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#b9dca8" />
          <stop offset="1" stopColor="#2f7a3e" />
        </radialGradient>
      </defs>

      <g className="fx-vine-stem" style={{ transformOrigin: `${cx}px ${baseY}px`, animationDelay: `${delay}s` }}>
        {links.map(({ y, w, tilt, k }) => (
          <g key={k} transform={`translate(${cx} ${y.toFixed(2)}) rotate(${tilt})`}>
            <rect x={-w / 2} y={-LINK / 2 - 0.4} width={w} height={LINK + 0.8} rx={w / 2} fill={`url(#${uid}-link)`} />
            <rect x={-w / 2 + 0.45} y={-LINK / 2 + 0.6} width={Math.max(0.35, w * 0.22)} height={LINK - 1.6} rx="0.3" className="fx-link-sheen" />
          </g>
        ))}
        {nodes.map(({ y, i }) => <ellipse key={i} cx={cx} cy={y} rx="2.3" ry="1.6" className="fx-stem-node" />)}
      </g>

      {nodes.map(({ y, s, angle, i }) => (
        <g key={i} transform={`translate(${cx} ${y.toFixed(1)}) rotate(${angle})`}>
          <g className="fx-vine-leaf" style={{ animationDelay: `${delay + 0.45 + i * 0.12}s` }}>
            {/* each leaf flutters on its own slow breath, out of step with its neighbours */}
            <g className="fx-leaf-sway" style={{ animationDelay: `${-(i * 1.3 + delay * 2).toFixed(2)}s`, animationDuration: `${4.2 + (i % 3) * 0.9}s` }}>
              <Leaf s={s} uid={uid} />
            </g>
          </g>
        </g>
      ))}

      <g className="fx-vine-bud" style={{ animationDelay: `${delay + 0.45 + nodes.length * 0.12}s` }}>
        <path d={tendril} className="fx-vine-tendril" />
        <ellipse cx={cx} cy={tipY} rx="2.6" ry="3.4" fill={`url(#${uid}-bud)`} />
      </g>
    </svg>
  );
}

export default function SidebarVines() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <Vine uid="vtr" className="fx-vine-tr" length={230} grow="down" leaves={6} size={22} delay={0.2} />
      <Vine uid="vbr" className="fx-vine-br" length={200} grow="up" leaves={5} size={21} delay={0.6} />
      <Vine uid="vbl" className="fx-vine-bl" length={170} grow="up" leaves={4} size={20} delay={1} />
    </div>
  );
}
