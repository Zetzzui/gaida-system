import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import GoogleSignIn from '../../components/GoogleSignIn';
import { BACKEND_URL } from '../../config';

export default function StudentLogin() {
  const [captchaText, setCaptchaText] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const canvasRef = useRef(null);

  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    student_number: '',
    email: '',
    access_code: '',
    antibot: '',
  });
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);

  // Generate captcha immediately when the page loads
  useEffect(() => {
    handleRefreshCaptcha();
  }, []);

  const handleChange = (e) => {
    const { id, value } = e.target;
    setFormData((prev) => ({ ...prev, [id]: value }));
    // Clear global error and specific field error when user starts typing
    setError('');
    setFieldErrors((prev) => ({ ...prev, [id]: false }));
  };

  const validateEmail = (email) => {
    return email.trim().toLowerCase().endsWith('@ue.edu.ph');
  };

  const generateCaptcha = () => {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';
    let text = '';
    for (let i = 0; i < 6; i++) {
      text += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setCaptchaText(text);
    return text;
  };

  const drawCaptcha = (text) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#f9fafb';
    ctx.fillRect(0, 0, width, height);

    for (let i = 0; i < 5; i++) {
      ctx.strokeStyle = `rgba(${Math.random() * 200},${Math.random() * 50},${Math.random() * 50},0.3)`;
      ctx.beginPath();
      ctx.moveTo(Math.random() * width, Math.random() * height);
      ctx.lineTo(Math.random() * width, Math.random() * height);
      ctx.stroke();
    }

    for (let i = 0; i < 40; i++) {
      ctx.fillStyle = 'rgba(0,0,0,0.05)';
      ctx.fillRect(Math.random() * width, Math.random() * height, 2, 2);
    }

    ctx.font = 'bold 20px monospace';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < text.length; i++) {
      const x = 10 + i * 16;
      const y = height / 2;
      const angle = (Math.random() - 0.5) * 0.4;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(angle);
      ctx.fillStyle = `rgb(${120 + Math.random() * 80},${Math.random() * 30},${Math.random() * 30})`;
      ctx.fillText(text[i], 0, 0);
      ctx.restore();
    }
  };

  const handleRefreshCaptcha = () => {
    const text = generateCaptcha();
    drawCaptcha(text);
    setFormData((prev) => ({ ...prev, antibot: '' }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setFieldErrors({});

    if (!validateEmail(formData.email)) {
      setError('Please enter a valid UE email address (@ue.edu.ph).');
      setFieldErrors({ email: true });
      return;
    }

    if (formData.antibot.toLowerCase() !== captchaText.toLowerCase()) {
      setError('Incorrect verification code. Please try again.');
      setFieldErrors({ antibot: true });
      handleRefreshCaptcha();
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/api/auth/login`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData),
        }
      );
      const data = await response.json();
      if (response.ok) {
        localStorage.setItem('session_token', data.session_token);
        localStorage.setItem('student_id', data.student_id);
        navigate('/consent');
      } else {
        setError(data.detail || 'Login failed. Please check your credentials.');
        setFieldErrors({ student_number: true, access_code: true });
        handleRefreshCaptcha();
      }
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleCredential = async (credential) => {
    if (loading) return;
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential, role: 'student' }),
      });
      const data = await response.json();
      if (response.ok) {
        localStorage.setItem('session_token', data.session_token);
        localStorage.setItem('student_id', data.student_id);
        navigate('/consent');
      } else {
        setError(data.detail || 'Google sign-in failed. Please try again.');
      }
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Helper for dynamic border colors
  const getInputClasses = (fieldId) => {
    const baseClasses =
      'w-full px-3 py-2 text-sm bg-gray-50 border rounded-lg text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-1 transition-colors';
    const errorClasses = 'border-red-500 ring-red-100 focus:border-red-500';
    const normalClasses = 'border-gray-200 focus:border-red-500 focus:ring-red-100';
    return `${baseClasses} ${fieldErrors[fieldId] ? errorClasses : normalClasses}`;
  };

  return (
    <div className="min-h-screen relative overflow-hidden flex items-center justify-center">
      {/* Full bleed UE background */}
      <div
        className="absolute inset-0 bg-center bg-cover bg-no-repeat"
        style={{
          backgroundImage:
            "url('https://www.ue.edu.ph/mla/wp-content/uploads/2023/04/uesocialogp.png')",
        }}
      >
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
      </div>

      {/* p-5 sm:p-7 ensures better padding on mobile screens */}
      <div className="relative z-10 bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 p-5 sm:p-7">
        {/* Logo */}
        <div className="flex flex-col items-center mb-5">
          <img
            src="https://www.ue.edu.ph/mla/wp-content/uploads/2020/12/UE_RED_SEAL_09.png"
            alt="University of the East"
            className="w-24 h-24 object-cover object-right rounded-full mb-3 shadow-lg border-4 border-red-700"
          />
          <h2 className="text-xl font-bold text-gray-900">Student Login</h2>
          <p className="text-gray-500 text-xs mt-1">Sign in to access your account</p>
        </div>

        {error && (
          <div className="mb-4 p-2.5 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs font-medium text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label
              htmlFor="student_number"
              className="block text-gray-700 text-xs font-semibold mb-1"
            >
              Student Number
            </label>
            <input
              type="text"
              id="student_number"
              placeholder="Enter your student number"
              value={formData.student_number}
              onChange={handleChange}
              className={getInputClasses('student_number')}
              required
            />
          </div>

          <div>
            <label
              htmlFor="email"
              className="block text-gray-700 text-xs font-semibold mb-1"
            >
              UE Email Address
            </label>
            <input
              type="email"
              id="email"
              placeholder="yourname@ue.edu.ph"
              value={formData.email}
              onChange={handleChange}
              className={getInputClasses('email')}
              required
            />
          </div>

          <div>
            <div className="flex justify-between mb-1">
              <label
                htmlFor="access_code"
                className="block text-gray-700 text-xs font-semibold"
              >
                Password
              </label>
              <a
                href="/forgot-password?role=student"
                className="text-red-600 hover:text-red-700 text-[10px] font-medium transition-colors"
              >
                Forgot Password?
              </a>
            </div>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                id="access_code"
                placeholder="Enter your password"
                value={formData.access_code}
                onChange={handleChange}
                className={`${getInputClasses('access_code')} pr-10`}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none"
              >
                {showPassword ? (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.29 3.29m0 0a10.05 10.05 0 015.71-1.581c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0l-3.29-3.29"
                    />
                  </svg>
                ) : (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                    />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <div>
            <label
              htmlFor="antibot"
              className="block text-gray-700 text-xs font-semibold mb-1"
            >
              Verification Code
            </label>
            <div className="flex gap-2">
              <div className="flex-shrink-0 relative rounded-lg border border-gray-200 bg-white overflow-hidden flex items-center justify-center p-0.5 shadow-sm">
                <canvas ref={canvasRef} width={110} height={34} className="rounded" />
              </div>
              <div className="relative flex-1">
                <input
                  type="text"
                  id="antibot"
                  placeholder="Type code"
                  value={formData.antibot}
                  onChange={handleChange}
                  autoComplete="off"
                  disabled={loading}
                  required
                  className={`${getInputClasses('antibot')} pr-8`}
                />
                <button
                  type="button"
                  onClick={handleRefreshCaptcha}
                  disabled={loading}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-red-600 transition-colors focus:outline-none disabled:opacity-50"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="flex-1 border border-gray-200 hover:border-red-400 hover:bg-red-50 text-gray-700 hover:text-red-700 font-semibold py-2 px-3 text-sm rounded-lg transition-all duration-200"
            >
              Back
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 flex justify-center items-center gap-2 bg-red-700 hover:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2 px-3 text-sm rounded-lg transition-colors duration-200 shadow-sm"
            >
              {loading ? (
                <>
                  <svg
                    className="animate-spin h-4 w-4 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                  Signing in...
                </>
              ) : (
                'Log In'
              )}
            </button>
          </div>
        </form>

        {/* Google SSO */}
        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-200"></div>
          </div>
          <div className="relative flex justify-center">
            <span className="px-2 bg-white text-gray-400 text-[10px] font-medium uppercase tracking-wider">
              or
            </span>
          </div>
        </div>

        <GoogleSignIn
          clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID}
          onCredential={handleGoogleCredential}
          text="continue_with"
        />

        <div className="mt-4 text-center space-y-2">
          <p className="text-gray-600 text-xs">
            New here?{' '}
            <a
              href="#"
              className="text-red-600 hover:text-red-700 font-semibold transition-colors"
            >
              Create an account
            </a>
          </p>
          <div className="flex justify-center gap-4 text-[10px] text-gray-400">
            <a href="#" className="hover:text-gray-600 transition-colors">
              Help
            </a>
            <a href="#" className="hover:text-gray-600 transition-colors">
              Privacy Policy
            </a>
            <a href="#" className="hover:text-gray-600 transition-colors">
              Terms
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}