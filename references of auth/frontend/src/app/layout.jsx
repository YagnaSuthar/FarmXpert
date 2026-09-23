import './globals.css';
import '../styles/landingpage.css';
import '../styles/navbar.css';
import '../styles/footer.css';
import '../styles/auth.css';
import '../styles/loading.css';
import '../styles/dashboard.css';
import '../styles/dashboard-shell.css';
import '../styles/graphs.css';

export const metadata = {
  title: 'Furnova — Accounting Built for Furniture Businesses',
  description: 'Double-entry accounting for furniture retail: master data, transactions, automatic journal entries and real-time financial reports.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" data-theme="dark" data-scroll-behavior="smooth" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
