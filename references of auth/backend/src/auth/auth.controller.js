const { env } = require('../config/env');
const { success, created, error } = require('../utils/response');
const authValidation = require('./auth.validation');
const authService = require('./auth.service');
const authSession = require('./auth.session');

/**
 * Auth Controller
 *
 * Responsible ONLY for:
 * - Reading request
 * - Calling validation & service
 * - Managing cookies (for privileged session authentication & refresh token)
 * - Returning standardized responses
 */

const authController = {
  async register(req, res, next) {
    try {
      const validation = authValidation.validateRegistration(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const newUser = await authService.register(validation.data);
      return created(res, 'Registration successful. A verification code has been sent to your email.', {
        user: newUser,
      });
    } catch (err) {
      next(err);
    }
  },

  async verifyEmail(req, res, next) {
    try {
      const validation = authValidation.validateVerifyEmail(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const result = await authService.verifyEmail(validation.data);
      return success(res, 'Email verified successfully', result);
    } catch (err) {
      next(err);
    }
  },

  async resendVerificationOtp(req, res, next) {
    try {
      const validation = authValidation.validateResendOtp(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const result = await authService.resendVerificationOtp(validation.data);
      return success(res, result.message);
    } catch (err) {
      next(err);
    }
  },

  async login(req, res, next) {
    try {
      const validation = authValidation.validateLogin(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const userAgent = req.headers['user-agent'] || null;
      const ipAddress = req.ip || req.connection?.remoteAddress || null;

      const result = await authService.login({
        ...validation.data,
        userAgent,
        ipAddress,
      });

      if (result.authType === 'session') {
        res.cookie('sid', result.sessionId, result.cookieOptions);
        res.clearCookie('refreshToken', {
          path: '/',
          httpOnly: true,
          secure: env.isProduction,
          sameSite: env.isProduction ? 'strict' : 'lax',
        });

        return success(res, 'Login successful', {
          user: result.user,
        });
      }

      res.clearCookie('sid', { path: '/' });

      if (result.rawRefreshToken) {
        res.cookie('refreshToken', result.rawRefreshToken, result.cookieOptions);
      }

      return success(res, 'Login successful', {
        token: result.token,
        user: result.user,
      });
    } catch (err) {
      next(err);
    }
  },

  async refresh(req, res, next) {
    try {
      const rawRefreshToken = req.cookies?.refreshToken;
      const userAgent = req.headers['user-agent'] || null;
      const ipAddress = req.ip || req.connection?.remoteAddress || null;

      if (!rawRefreshToken) {
        res.clearCookie('refreshToken', {
          path: '/',
          httpOnly: true,
          secure: env.isProduction,
          sameSite: env.isProduction ? 'strict' : 'lax',
        });
        return error(res, 'Refresh token is missing. Please log in again.', 401);
      }

      const result = await authService.refreshToken({
        rawRefreshToken,
        userAgent,
        ipAddress,
      });

      // Set rotated HttpOnly refresh token cookie
      res.cookie('refreshToken', result.rawRefreshToken, result.cookieOptions);

      return success(res, 'Token refreshed successfully', {
        token: result.token,
        user: result.user,
      });
    } catch (err) {
      // Clear refresh token cookie on failure
      res.clearCookie('refreshToken', {
        path: '/',
        httpOnly: true,
        secure: env.isProduction,
        sameSite: env.isProduction ? 'strict' : 'lax',
      });
      return error(res, err.message || 'Token refresh failed', err.statusCode || 401);
    }
  },

  async logout(req, res, next) {
    try {
      const sessionCookie = req.cookies?.sid;
      const rawRefreshToken = req.cookies?.refreshToken;

      await authService.logout({
        rawRefreshToken,
        sessionId: sessionCookie,
      });

      res.clearCookie('sid', { path: '/' });
      res.clearCookie('refreshToken', {
        path: '/',
        httpOnly: true,
        secure: env.isProduction,
        sameSite: env.isProduction ? 'strict' : 'lax',
      });

      return success(res, 'Logged out successfully');
    } catch (err) {
      next(err);
    }
  },

  async getMe(req, res, next) {
    try {
      return success(res, 'User profile retrieved successfully', {
        user: req.user,
      });
    } catch (err) {
      next(err);
    }
  },

  async getCaptcha(req, res, next) {
    try {
      const captcha = authService.getCaptchaChallenge();
      return success(res, 'CAPTCHA challenge generated successfully', captcha);
    } catch (err) {
      next(err);
    }
  },

  async forgotPassword(req, res, next) {
    try {
      const validation = authValidation.validateForgotPassword(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const result = await authService.forgotPassword(validation.data);
      return success(res, result.message);
    } catch (err) {
      next(err);
    }
  },

  async verifyResetOtp(req, res, next) {
    try {
      const validation = authValidation.validateVerifyResetOtp(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const result = await authService.verifyResetOtp(validation.data);
      return success(res, result.message, { resetToken: result.resetToken });
    } catch (err) {
      next(err);
    }
  },

  async resetPassword(req, res, next) {
    try {
      const validation = authValidation.validateResetPassword(req.body);
      if (!validation.isValid) {
        return error(res, 'Validation failed', 400, validation.errors);
      }

      const result = await authService.resetPassword(validation.data);
      return success(res, result.message);
    } catch (err) {
      next(err);
    }
  },

  async listUsers(req, res, next) {
    try {
      const users = await authService.listUsers(req.query);
      return success(res, 'Users retrieved successfully', { users });
    } catch (err) {
      next(err);
    }
  },

  async updateUserRole(req, res, next) {
    try {
      const { role } = req.body;
      if (!role) {
        return error(res, 'Role is required in request body', 400);
      }

      const updatedUser = await authService.updateUserRole({
        userId: req.params.id,
        newRole: role,
      });

      return success(res, 'User role updated successfully', { user: updatedUser });
    } catch (err) {
      next(err);
    }
  },

  async getManagerDashboard(req, res, next) {
    try {
      return success(res, 'Manager operational dashboard data retrieved', {
        manager: req.user.name,
        role: req.user.role,
        status: 'active',
        systemLoad: 'optimal',
      });
    } catch (err) {
      next(err);
    }
  },

  async getUserProfileById(req, res, next) {
    try {
      const user = await authService.getUserById(req.params.id);
      return success(res, 'User profile retrieved successfully', { user });
    } catch (err) {
      next(err);
    }
  },
};

module.exports = authController;
