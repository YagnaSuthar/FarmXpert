/**
 * Auth Validation
 *
 * Input validation for all auth endpoints.
 * Returns an object: { isValid: boolean, errors: string[], data?: object }
 *
 * RULES:
 * - Validate before any business logic
 * - Sanitize inputs (trim, lowercase emails)
 * - Never trust client-side validation alone
 */

const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
const OTP_REGEX = /^\d{6}$/;
const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_MAX_LENGTH = 128;

function validatePasswordComplexity(password, errors) {
  if (!password || typeof password !== 'string') {
    errors.push('Password is required');
    return;
  }
  if (password.length < PASSWORD_MIN_LENGTH) {
    errors.push(`Password must be at least ${PASSWORD_MIN_LENGTH} characters long`);
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    errors.push(`Password must not exceed ${PASSWORD_MAX_LENGTH} characters`);
  }
  if (!/[a-z]/.test(password)) {
    errors.push('Password must contain at least one lowercase letter');
  }
  if (!/[A-Z]/.test(password)) {
    errors.push('Password must contain at least one uppercase letter');
  }
  if (!/[0-9]/.test(password)) {
    errors.push('Password must contain at least one number');
  }
  if (!/[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?`~]/.test(password)) {
    errors.push('Password must contain at least one special character');
  }
}

const authValidation = {
  /**
   * Validate registration payload.
   * Enforces name, email format, and password complexity.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { name: string, email: string, password: string, captchaId?: string, captchaAnswer?: string } }}
   */
  validateRegistration(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { name, email, password, captchaId, captchaAnswer } = body;

    // Validate Name
    if (!name || typeof name !== 'string' || name.trim().length === 0) {
      errors.push('Name is required');
    } else if (name.trim().length < 2 || name.trim().length > 100) {
      errors.push('Name must be between 2 and 100 characters');
    }

    // Validate Email
    if (!email || typeof email !== 'string' || email.trim().length === 0) {
      errors.push('Email is required');
    } else {
      const sanitizedEmail = email.trim().toLowerCase();
      if (!EMAIL_REGEX.test(sanitizedEmail) || sanitizedEmail.length > 255) {
        errors.push('Please provide a valid email address');
      }
    }

    // Validate Password
    validatePasswordComplexity(password, errors);

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        captchaId: captchaId ? String(captchaId).trim() : undefined,
        captchaAnswer: captchaAnswer !== undefined ? String(captchaAnswer).trim() : undefined,
      },
    };
  },

  /**
   * Validate email verification payload.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { email: string, otp: string } }}
   */
  validateVerifyEmail(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { email, otp } = body;

    // Validate Email
    if (!email || typeof email !== 'string' || email.trim().length === 0) {
      errors.push('Email is required');
    } else {
      const sanitizedEmail = email.trim().toLowerCase();
      if (!EMAIL_REGEX.test(sanitizedEmail) || sanitizedEmail.length > 255) {
        errors.push('Please provide a valid email address');
      }
    }

    // Validate OTP (6 digits)
    if (!otp || (typeof otp !== 'string' && typeof otp !== 'number')) {
      errors.push('Verification code is required');
    } else {
      const otpStr = String(otp).trim();
      if (!OTP_REGEX.test(otpStr)) {
        errors.push('Verification code must be exactly 6 digits');
      }
    }

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        email: email.trim().toLowerCase(),
        otp: String(otp).trim(),
      },
    };
  },

  /**
   * Validate resend verification OTP payload.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { email: string } }}
   */
  validateResendOtp(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { email } = body;

    if (!email || typeof email !== 'string' || email.trim().length === 0) {
      errors.push('Email is required');
    } else {
      const sanitizedEmail = email.trim().toLowerCase();
      if (!EMAIL_REGEX.test(sanitizedEmail) || sanitizedEmail.length > 255) {
        errors.push('Please provide a valid email address');
      }
    }

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        email: email.trim().toLowerCase(),
      },
    };
  },

  /**
   * Validate login payload.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { email: string, password: string, captchaId?: string, captchaAnswer?: string, remember?: boolean } }}
   */
  validateLogin(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { email, password, captchaId, captchaAnswer, remember } = body;

    // Validate Email
    if (!email || typeof email !== 'string' || email.trim().length === 0) {
      errors.push('Email is required');
    } else {
      const sanitizedEmail = email.trim().toLowerCase();
      if (!EMAIL_REGEX.test(sanitizedEmail)) {
        errors.push('Please provide a valid email address');
      }
    }

    // Validate Password
    if (!password || typeof password !== 'string' || password.length === 0) {
      errors.push('Password is required');
    }

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        email: email.trim().toLowerCase(),
        password,
        captchaId: captchaId ? String(captchaId).trim() : undefined,
        captchaAnswer: captchaAnswer !== undefined ? String(captchaAnswer).trim() : undefined,
        remember: Boolean(remember),
      },
    };
  },

  /**
   * Validate standalone CAPTCHA answer verification request.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { captchaId: string, captchaAnswer: string } }}
   */
  validateCaptcha(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { captchaId, captchaAnswer } = body;

    if (!captchaId || typeof captchaId !== 'string' || captchaId.trim().length === 0) {
      errors.push('CAPTCHA ID is required');
    }

    if (captchaAnswer === undefined || captchaAnswer === null || String(captchaAnswer).trim() === '') {
      errors.push('CAPTCHA answer is required');
    }

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        captchaId: String(captchaId).trim(),
        captchaAnswer: String(captchaAnswer).trim(),
      },
    };
  },

  /**
   * Validate forgot-password payload.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { email: string, captchaId?: string, captchaAnswer?: string } }}
   */
  validateForgotPassword(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { email, captchaId, captchaAnswer } = body;

    if (!email || typeof email !== 'string' || email.trim().length === 0) {
      errors.push('Email is required');
    } else {
      const sanitizedEmail = email.trim().toLowerCase();
      if (!EMAIL_REGEX.test(sanitizedEmail) || sanitizedEmail.length > 255) {
        errors.push('Please provide a valid email address');
      }
    }

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        email: email.trim().toLowerCase(),
        captchaId: captchaId ? String(captchaId).trim() : undefined,
        captchaAnswer: captchaAnswer !== undefined ? String(captchaAnswer).trim() : undefined,
      },
    };
  },

  /**
   * Validate verify-reset-otp payload.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { email: string, otp: string } }}
   */
  validateVerifyResetOtp(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { email, otp } = body;

    if (!email || typeof email !== 'string' || email.trim().length === 0) {
      errors.push('Email is required');
    } else {
      const sanitizedEmail = email.trim().toLowerCase();
      if (!EMAIL_REGEX.test(sanitizedEmail) || sanitizedEmail.length > 255) {
        errors.push('Please provide a valid email address');
      }
    }

    if (!otp || (typeof otp !== 'string' && typeof otp !== 'number')) {
      errors.push('Reset verification code is required');
    } else {
      const otpStr = String(otp).trim();
      if (!OTP_REGEX.test(otpStr)) {
        errors.push('Reset verification code must be exactly 6 digits');
      }
    }

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        email: email.trim().toLowerCase(),
        otp: String(otp).trim(),
      },
    };
  },

  /**
   * Validate reset-password payload.
   *
   * @param {Object} body
   * @returns {{ isValid: boolean, errors: string[], data?: { resetToken: string, newPassword: string } }}
   */
  validateResetPassword(body) {
    const errors = [];

    if (!body || typeof body !== 'object') {
      return { isValid: false, errors: ['Request body must be a JSON object'] };
    }

    const { resetToken, newPassword } = body;

    if (!resetToken || typeof resetToken !== 'string' || resetToken.trim().length === 0) {
      errors.push('Reset authorization token is required');
    }

    validatePasswordComplexity(newPassword, errors);

    if (errors.length > 0) {
      return { isValid: false, errors };
    }

    return {
      isValid: true,
      errors: [],
      data: {
        resetToken: String(resetToken).trim(),
        newPassword,
      },
    };
  },
};

module.exports = authValidation;
