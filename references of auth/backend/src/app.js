const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const cookieParser = require('cookie-parser');
const { env } = require('./config/env');

// Middleware
const errorMiddleware = require('./middleware/error.middleware');
const notFoundMiddleware = require('./middleware/notFound.middleware');

// Feature routes
const authRoutes = require('./auth/auth.routes');

/**
 * Create and configure Express application.
 *
 * Middleware order:
 * 1. Security headers (Helmet)
 * 2. CORS
 * 3. Body parsing (JSON, URL-encoded)
 * 4. Cookie parsing
 * 5. Feature routes
 * 6. 404 handler
 * 7. Centralized error handler
 */
const app = express();

// ─── Security Headers ───────────────────────────────────
app.use(helmet());

// ─── CORS ───────────────────────────────────────────────
app.use(cors({
  origin: env.corsOrigin,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}));

// ─── Body Parsing ───────────────────────────────────────
app.use(express.json({ limit: '10kb' }));
app.use(express.urlencoded({ extended: true, limit: '10kb' }));

// ─── Cookie Parsing ─────────────────────────────────────
app.use(cookieParser());

// ─── Health Check ───────────────────────────────────────
app.get('/api/health', (req, res) => {
  res.json({
    success: true,
    message: 'Server is running',
    timestamp: new Date().toISOString(),
    environment: env.nodeEnv,
  });
});

// ─── Feature Routes ─────────────────────────────────────
app.use('/api/auth', authRoutes);

// Future feature routes will be mounted here:
// app.use('/api/users', userRoutes);
// app.use('/api/orders', orderRoutes);
// app.use('/api/payments', paymentRoutes);
// app.use('/api/admin', adminRoutes);

// ─── 404 Handler (must be after all routes) ─────────────
app.use(notFoundMiddleware);

// ─── Error Handler (must be last) ───────────────────────
app.use(errorMiddleware);

module.exports = app;
