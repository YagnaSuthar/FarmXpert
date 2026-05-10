import { Radio, Microscope, Handshake, CheckCircle2 } from 'lucide-react';

const steps = [
  {
    num: '01',
    icon: <Radio size={18} />,
    title: 'Data Ingestion',
    desc: 'IoT sensors, drones, satellite feeds, and weather APIs stream live data to the FarmXpert edge gateway continuously.',
    delay: '',
  },
  {
    num: '02',
    icon: <Microscope size={18} />,
    title: 'Agent Analysis',
    desc: 'Specialized AI agents process relevant data streams in parallel using CNN, LSTM, and transformer models optimized for agriculture.',
    delay: '0.1s',
  },
  {
    num: '03',
    icon: <Handshake size={18} />,
    title: 'Multi-Agent Fusion',
    desc: 'Orchestration layer combines insights from all agents, resolves conflicts, and weights recommendations by confidence scores.',
    delay: '0.2s',
  },
  {
    num: '04',
    icon: <CheckCircle2 size={18} />,
    title: 'Smart Action',
    desc: 'Recommendations delivered via app, voice, or direct actuator control — automated irrigation, alerts, task assignments, and reports.',
    delay: '0.3s',
  },
];

export default function HowItWorksSection() {
  return (
    <section className="how-section" id="how">
      <div className="section-container">
        <div style={{ textAlign: 'center', marginBottom: 0 }}>
          <div className="section-eyebrow" style={{ justifyContent: 'center' }}>
            Process Flow
          </div>
          <h2 className="section-title" style={{ textAlign: 'center' }}>
            From Data to <span className="text-green">Decision</span>
          </h2>
          <p className="section-sub" style={{ margin: '0 auto', textAlign: 'center' }}>
            FarmXpert's pipeline transforms raw sensor readings into actionable decisions in under 200
            milliseconds.
          </p>
        </div>

        <div className="how-grid">
          {steps.map((step, i) => (
            <div
              key={i}
              className="how-step reveal"
              style={step.delay ? { transitionDelay: step.delay } : {}}
            >
              <div className="how-num-circle">
                <span className="how-num">{step.num}</span>
                <span className="how-step-icon">{step.icon}</span>
              </div>
              <div className="how-step-title">{step.title}</div>
              <div className="how-step-desc">{step.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}