// ============================================================
// FILE: app/layout.jsx
// Root layout — wraps every page in the app.
// Import global styles here; add <head> meta, fonts, providers.
// ============================================================

import '../styles/landing.css';
import '../styles/animation.css';
import '../styles/components.css';
import './globals.css';

import { ThemeProvider } from '@/components/layout/ThemeProvider';

export const metadata = {
  title: 'FarmXpert — AI-Powered Agriculture Platform',
  description: 'Revolutionizing agriculture with intelligent AI agents. Smart farming solutions for crop planning, soil health analysis, and real-time farm analytics.',
  keywords: 'agriculture, AI, farming, smart farming, crop planning, soil health, FarmXpert',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Prevent FOUC by setting theme immediately from localStorage */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('theme');
                if (theme) {
                  document.documentElement.setAttribute('data-theme', theme);
                } else {
                  document.documentElement.setAttribute('data-theme', 'dark');
                }
              } catch (_) {}
            `,
          }}
        />
        {/* Google Fonts — Inter */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <ThemeProvider>
          {/* Global site wrapper — used for scroll context & canvas layering */}
          <div id="site-root">
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}