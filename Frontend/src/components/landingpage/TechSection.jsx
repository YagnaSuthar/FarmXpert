const techChips = [
  'Next.js 14',
  'FastAPI',
  'TensorFlow 2.x',
  'Python 3.11',
  'CNN Models',
  'LSTM Networks',
  'Transformer AI',
  'Multi-Agent Systems',
  'Real-Time Analytics',
  'Satellite APIs',
  'IoT Edge Computing',
  'PostgreSQL',
  'Redis Cache',
  'Kubernetes',
  'Docker',
  'WebSocket Streams',
];

export default function TechSection() {
  return (
    <section className="tech-section" id="tech">
      <div className="section-container">
        <div className="section-eyebrow">Technology Stack</div>
        <h2 className="section-title">
          Built on <span className="text-green">Modern</span>
          <br />
          AI Infrastructure
        </h2>
        <p className="section-sub">
          Enterprise-grade ML pipelines, scalable microservices, and production-ready AI — built for
          the demands of precision agriculture at scale.
        </p>
        <div className="tech-strip reveal">
          {techChips.map((chip, i) => (
            <div key={i} className="tech-chip">
              <span className="tc-dot"></span>
              {chip}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}