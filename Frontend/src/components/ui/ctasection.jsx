// ============================================================
// FILE: components/ui/CTASection.jsx
// Bottom call-to-action — email capture or redirect to signup.
//
// TODO: wire form submission (API route or external service)
// TODO: add loading / success / error states to button
// ============================================================

'use client';

export default function CTASection() {
  // TODO: const [email, setEmail] = useState('')
  // TODO: const [status, setStatus] = useState('idle') // idle|loading|success|error

  const handleSubmit = (e) => {
    e.preventDefault();
    // TODO: POST to /api/subscribe or external endpoint
  };

  return (
    <section className="cta-section section" id="cta">
      <div className="container cta-section__inner">

        {/* Glow orb — purely decorative, matches particle accent */}
        <div className="cta-section__glow" aria-hidden="true" />

        <div className="cta-section__content">
          <p className="label">Get early access</p>
          <h2 className="cta-section__headline display-md">
            Ready to ship<br />something real?
          </h2>
          <p className="cta-section__subtext body-lg">
            {/* TODO: real copy */}
            Join the waitlist and be first to experience
            the full particle-powered launch.
          </p>
        </div>

        {/* Email form */}
        <form className="cta-section__form" onSubmit={handleSubmit} noValidate>
          <div className="cta-section__input-group">
            <label htmlFor="cta-email" className="sr-only">Email address</label>
            <input
              id="cta-email"
              type="email"
              name="email"
              placeholder="you@example.com"
              className="input input--lg cta-section__email-input"
              autoComplete="email"
              required
              // TODO: value={email} onChange={e => setEmail(e.target.value)}
            />
            <button type="submit" className="btn btn--primary btn--lg">
              {/* TODO: swap text on status change */}
              Claim your spot
            </button>
          </div>
          <p className="cta-section__disclaimer caption">
            No spam, ever. Unsubscribe at any time.
          </p>
        </form>

      </div>
    </section>
  );
}