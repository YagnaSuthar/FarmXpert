'use client';
import { useEffect, useRef } from 'react';
import {
  Sprout, Droplets, Bug, Wheat, BarChart3, TrendingUp,
  Satellite, Mic, Layers, Droplet, Shield, LineChart, Radio
} from 'lucide-react';

const agentCards = [
  {
    category: 'soil',
    delay: '',
    img: 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600&q=80',
    imgAlt: 'Soil Analysis',
    icon: <Sprout size={24} />,
    tag: 'Soil Health',
    name: 'Soil Intelligence Agent',
    desc: 'Analyzes pH, NPK ratios, moisture, and microbial activity using IoT sensors and LSTM time-series models to recommend optimal amendments.',
    metrics: [
      { val: '99.1%', key: 'Accuracy' },
      { val: '24/7', key: 'Monitoring' },
      { val: '6 Params', key: 'Tracked' },
    ],
  },
  {
    category: 'water',
    delay: '0.1s',
    img: 'https://images.unsplash.com/photo-1574943320219-553eb213f72d?w=600&q=80',
    imgAlt: 'Smart Irrigation',
    icon: <Droplets size={24} />,
    tag: 'Irrigation',
    name: 'Smart Irrigation Agent',
    desc: 'Integrates weather APIs, soil moisture sensors, and evapotranspiration models to schedule precision drip and sprinkler irrigation automatically.',
    metrics: [
      { val: '38%', key: 'Water Saved' },
      { val: '15min', key: 'Cycle Time' },
      { val: 'IoT', key: 'Integrated' },
    ],
  },
  {
    category: 'protection',
    delay: '0.2s',
    img: 'https://images.unsplash.com/photo-1464226184884-fa280b87c399?w=600&q=80',
    imgAlt: 'Pest Detection',
    icon: <Bug size={24} />,
    tag: 'Pest & Disease',
    name: 'Pest Detection Agent',
    desc: 'CNN-powered image recognition identifies 240+ pest species and crop diseases from drone or smartphone photos with treatment recommendations.',
    metrics: [
      { val: '94.7%', key: 'Accuracy' },
      { val: '240+', key: 'Species' },
      { val: 'CNN', key: 'Model' },
    ],
  },
  {
    category: 'soil',
    delay: '0.3s',
    img: 'https://images.unsplash.com/photo-1595771805070-1c15ab7dea82?w=600&q=80',
    imgAlt: 'Crop Recommendation',
    icon: <Wheat size={24} />,
    tag: 'Crop AI',
    name: 'Crop Recommendation Agent',
    desc: 'Matches soil profiles, climate patterns, and market trends to suggest the most profitable crops with seasonal rotation strategies.',
    metrics: [
      { val: '150+', key: 'Crop Types' },
      { val: '3×', key: 'More Profit' },
      { val: 'ML', key: 'Powered' },
    ],
  },
  {
    category: 'market',
    delay: '0.1s',
    img: 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600&q=80',
    imgAlt: 'Yield Prediction',
    icon: <BarChart3 size={24} />,
    tag: 'Yield AI',
    name: 'Yield Prediction Agent',
    desc: 'LSTM models trained on 10+ years of satellite imagery and climate data forecast per-acre yield 8 weeks ahead with 91% accuracy.',
    metrics: [
      { val: '91%', key: 'Accuracy' },
      { val: '8 wk', key: 'Ahead' },
      { val: 'LSTM', key: 'Model' },
    ],
  },
  {
    category: 'market',
    delay: '0.2s',
    img: 'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&q=80',
    imgAlt: 'Market Forecast',
    icon: <TrendingUp size={24} />,
    tag: 'Market',
    name: 'Market Price Forecast Agent',
    desc: 'Real-time commodity price tracking with transformer-based forecasting models analyzing 40+ market signals for optimal sell-timing decisions.',
    metrics: [
      { val: '40+', key: 'Signals' },
      { val: 'Live', key: 'Data Feed' },
      { val: '±3%', key: 'Margin' },
    ],
  },
  {
    category: 'monitoring',
    delay: '0.3s',
    img: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=600&q=80',
    imgAlt: 'Growth Monitor',
    icon: <Satellite size={24} />,
    tag: 'Monitoring',
    name: 'Growth Monitoring Agent',
    desc: 'Satellite NDVI analysis and drone imagery track canopy growth, stress zones, and field uniformity weekly to guide variable-rate applications.',
    metrics: [
      { val: 'NDVI', key: 'Analysis' },
      { val: 'Weekly', key: 'Reports' },
      { val: 'Drone', key: 'Integrated' },
    ],
  },
  {
    category: 'monitoring',
    delay: '0.4s',
    img: 'https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&q=80',
    imgAlt: 'Voice Assistant',
    icon: <Mic size={24} />,
    tag: 'Voice AI',
    name: 'Voice Farming Assistant',
    desc: 'Multilingual voice AI trained on agricultural terminology lets farmers query all agents hands-free in the field — supports 12 regional languages.',
    metrics: [
      { val: '12', key: 'Languages' },
      { val: '97%', key: 'Voice Acc.' },
      { val: 'NLP', key: 'Powered' },
    ],
  },
];

const filterOptions = [
  { label: 'All Agents', value: 'all' },
  { label: 'Soil & Crop', value: 'soil' },
  { label: 'Water & Climate', value: 'water' },
  { label: 'Protection', value: 'protection' },
  { label: 'Market & Yield', value: 'market' },
  { label: 'Monitoring', value: 'monitoring' },
];

export default function AgentsSection() {
  const sectionRef = useRef(null);
  const cardsRef = useRef([]);
  const animatedCardsRef = useRef(new Set());

  // Scroll reveal animation for cards
  useEffect(() => {
    const cards = cardsRef.current.filter(Boolean);
    if (cards.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visibleCards = entries
          .filter((e) => e.isIntersecting && !animatedCardsRef.current.has(e.target))
          .map((e) => ({ element: e.target, index: parseInt(e.target.dataset.cardIndex) }))
          .sort((a, b) => a.index - b.index);

        // Apply stagger only to the newly visible cards in this batch
        visibleCards.forEach((card, batchIndex) => {
          animatedCardsRef.current.add(card.element);
          // Staggered delay based on position in this batch (1s per card)
          const delay = batchIndex * 100;
          setTimeout(() => {
            card.element.classList.add('visible');
          }, delay);
          observer.unobserve(card.element);
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -50px 0px' }
    );

    cards.forEach((card) => observer.observe(card));

    return () => observer.disconnect();
  }, []);

  // Filter tabs functionality
  useEffect(() => {
    const tabs = document.querySelectorAll('.filter-tab');
    const allCards = document.querySelectorAll('.agent-card');

    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        tabs.forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        const filter = tab.dataset.filter;
        
        let visibleIndex = 0;
        allCards.forEach((card) => {
          if (filter === 'all' || card.dataset.category === filter) {
            card.classList.remove('hidden');
            card.classList.remove('visible');
            const delay = visibleIndex * 100;
            setTimeout(() => {
              card.classList.add('visible');
            }, delay);
            visibleIndex++;
          } else {
            card.classList.remove('visible');
            card.classList.add('hidden');
          }
        });
      });
    });
  }, []);

  return (
    <section className="agents-section" id="agents">
      <div className="section-container">
        <div className="section-eyebrow">AI Agent Network</div>
        <h2 className="section-title">
          Eight Intelligent <span className="text-green">Agents</span>,<br />One Unified Platform
        </h2>
        <p className="section-sub">
          Each agent is a specialized ML model trained on millions of agricultural data points,
          communicating in real-time to give holistic farm intelligence.
        </p>

        <div className="filter-tabs" style={{ marginTop: '40px' }}>
          {filterOptions.map((opt) => (
            <button
              key={opt.value}
              className={`filter-tab${opt.value === 'all' ? ' active' : ''}`}
              data-filter={opt.value}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="agents-grid">
          {agentCards.map((card, i) => (
            <div
              key={i}
              ref={(el) => { cardsRef.current[i] = el; }}
              className="agent-card agent-reveal"
              data-category={card.category}
              data-card-index={i}
            >
              <img className="agent-card-img" src={card.img} alt={card.imgAlt} />
              <div className="agent-card-body">
                <div className="agent-card-icon-row">
                  <div className="agent-icon-circle">{card.icon}</div>
                  <span className="agent-tag">{card.tag}</span>
                </div>
                <div className="agent-name">{card.name}</div>
                <div className="agent-desc">{card.desc}</div>
                <div className="agent-metrics">
                  {card.metrics.map((m, j) => (
                    <div key={j} className="metric">
                      <span className="metric-val">{m.val}</span>
                      <span className="metric-key">{m.key}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}