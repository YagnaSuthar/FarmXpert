export default function CTASection() {
  return (
    <section className="cta-section">
      <div className="section-container">
        <div className="cta-box reveal">
          <div className="section-eyebrow" style={{ justifyContent: 'center', marginBottom: '20px' }}>
            Start Today
          </div>
          <h2 className="cta-title">
            Your Farm's AI <span className="text-green">Command Center</span> Awaits
          </h2>
          <p className="cta-desc">
            Join 12,000+ farmers already using FarmXpert to optimize every acre. Setup takes under 10
            minutes — no hardware required to start.
          </p>
          <div className="cta-actions">
            <button className="btn-primary">Start Free Trial</button>
            <button className="btn-secondary">Schedule a Demo</button>
          </div>
        </div>
      </div>
    </section>
  );
}