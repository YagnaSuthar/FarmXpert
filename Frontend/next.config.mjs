import createNextIntlPlugin from 'next-intl/plugin';

// Point the plugin at our request handler so server components can
// resolve messages without us wiring them up manually. The path is
// resolved relative to the project root.
const withNextIntl = createNextIntlPlugin('./src/i18n/request.js');

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Project-level config goes here. Keep this slim — next-intl adds
  // what it needs via the plugin wrapper below.
};

export default withNextIntl(nextConfig);
