const featureItems = [
  {
    icon: '🧠',
    title: 'Multi-Agent Collaboration',
    desc: 'Agents communicate asynchronously to produce compound recommendations — for example, irrigation schedules that factor in pest stress and forecasted rain simultaneously.',
    delay: '',
  },
  {
    icon: '⚡',
    title: 'Real-Time Edge Analytics',
    desc: 'Sub-200ms latency analytics via edge-deployed TensorFlow Lite models, even in low-connectivity rural areas with intermittent internet.',
    delay: '0.1s',
  },
  {
    icon: '🛰️',
    title: 'Satellite + IoT Fusion',
    desc: 'Sentinel-2 satellite bands fused with on-field sensor telemetry for ground-truth accuracy at every spatial scale from 10m² to 1000 hectares.',
    delay: '0.2s',
  },
  {
    icon: '📊',
    title: 'Adaptive Learning Loop',
    desc: "Models retrain monthly on your farm's actual outcomes — yield data, treatment results, weather events — continuously improving recommendation precision.",
    delay: '0.3s',
  },
];

export default function FeaturesSection() {
  return (
    <section className="features-section" id="features">
      <div className="section-container">
        <div className="feature-visual">
          <img
            className="feature-main-img"
            src="https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=700&q=80"
            alt="Smart Farm"
          />
          <img
            className="feature-secondary-img"
            src="https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=400&q=80"
            alt="Farm Analytics"
          />
          <div className="feature-badge-card">
            <div className="fbc-icon">🤖</div>
            <span className="fbc-val">8 Agents</span>
            <span className="fbc-label">Always Active</span>
          </div>
        </div>

        <div>
          <div className="section-eyebrow">Platform Capabilities</div>
          <h2 className="section-title">
            Intelligence at Every <span className="text-green">Layer</span>
          </h2>
          <p className="section-sub">
            From root to revenue — FarmXpert's layered AI architecture monitors everything that
            affects your yield and profitability.
          </p>
          <div className="feature-list">
            {featureItems.map((item, i) => (
              <div
                key={i}
                className="feature-item reveal"
                style={item.delay ? { transitionDelay: item.delay } : {}}
              >
                <div className="fi-icon">{item.icon}</div>
                <div>
                  <div className="fi-title">{item.title}</div>
                  <div className="fi-desc">{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}