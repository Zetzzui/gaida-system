import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BACKEND_URL } from '../../config';
import apiFetch from '../../api';

// Standard 10-item System Usability Scale (Brooke, 1996), unmodified wording.
// Odd items are positively worded, even items negatively worded — this
// alternation is intentional (it's part of the validated instrument) and
// must not be "fixed" or reordered.
const SUS_QUESTIONS = [
  'I think that I would like to use GAIDA frequently.',
  'I found GAIDA unnecessarily complex.',
  'I thought GAIDA was easy to use.',
  'I think that I would need the support of a technical person to be able to use GAIDA.',
  'I found the various functions in GAIDA were well integrated.',
  'I thought there was too much inconsistency in GAIDA.',
  'I would imagine that most students would learn to use GAIDA very quickly.',
  'I found GAIDA very cumbersome to use.',
  'I felt very confident using GAIDA.',
  'I needed to learn a lot of things before I could get going with GAIDA.',
];

const SUS_OPTIONS = [
  { value: 1, label: 'Strongly disagree' },
  { value: 2, label: 'Disagree' },
  { value: 3, label: 'Neutral' },
  { value: 4, label: 'Agree' },
  { value: 5, label: 'Strongly agree' },
];

const STEP = { SUS: 0, SUBMITTING: 1, DONE: 2 };

// Mirrors the "Sky" theme in StudentDashboard.jsx / ResearchFlow.jsx so the
// post-session survey reads as the same experience, not a separate dark page.
const T = {
  bg: '#F7FAF9',
  sidebar: '#EEF4F6',
  card: '#FFFFFF',
  border: '#DCE7EA',
  accent: '#5E8FBD',
  accentDark: '#4A7699',
  textPrimary: '#2E3B44',
  textSecondary: '#5C6F78',
  textMuted: '#95A6AC',
  errorText: '#9C5A3C',
  errorBg: '#F5E4DA',
};

export default function ResearchSUS() {
  const navigate = useNavigate();
  const [step, setStep] = useState(STEP.SUS);
  const [answers, setAnswers] = useState(Array(SUS_QUESTIONS.length).fill(null));
  const [error, setError] = useState('');

  const allAnswered = answers.every((a) => a !== null);

  // Clears the two keys confirmEndSession deliberately left behind for us.
  const clearHandoffKeys = () => {
    localStorage.removeItem('session_id');
    localStorage.removeItem('session_token');
  };

  const handleSubmit = async () => {
    if (!allAnswered) return;
    setError('');
    setStep(STEP.SUBMITTING);

    // This page is only ever reached right after a research session ends,
    // via the same localStorage keys StudentDashboard's confirmEndSession
    // deliberately keeps around for a research session — no separate login
    // or session lookup needed here.
    const session_id = localStorage.getItem('session_id');

    if (!session_id) {
      // Shouldn't normally happen (StudentDashboard should only route here
      // for a research session), but fail gracefully rather than crash.
      setError('Could not find your session — your usability feedback was not saved.');
      setStep(STEP.SUS);
      return;
    }

    try {
      // apiFetch picks up the bearer token from localStorage automatically
      // (session_token, kept around by confirmEndSession for this reason) —
      // /api/research/sus requires it, same as /api/research/gad7.
      const res = await apiFetch(`${BACKEND_URL}/api/research/sus`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, answers }),
      });
      if (!res.ok) throw new Error('Could not save your responses');
      clearHandoffKeys();
      setStep(STEP.DONE);
    } catch (err) {
      console.error('SUS submit error:', err);
      setError('Something went wrong saving your responses. Please try again.');
      setStep(STEP.SUS);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{ background: T.bg, color: T.textPrimary }}
    >
      <div
        className="w-full max-w-xl rounded-2xl p-8"
        style={{ background: T.card, border: `1px solid ${T.border}`, boxShadow: '0 1px 3px rgba(46,59,68,0.06)' }}
      >
        <h1 className="text-2xl font-bold mb-1" style={{ color: T.textPrimary }}>One Last Thing</h1>
        <p className="text-sm mb-6" style={{ color: T.textSecondary }}>
          A quick 10-question survey about your experience using GAIDA just now. This
          helps us evaluate how usable the system actually is — there are no right or
          wrong answers.
        </p>

        {step === STEP.SUS && (
          <div>
            <div className="space-y-5 max-h-96 overflow-y-auto pr-1">
              {SUS_QUESTIONS.map((q, i) => (
                <div key={i}>
                  <p className="text-sm mb-2" style={{ color: T.textPrimary }}>{i + 1}. {q}</p>
                  <div className="grid grid-cols-5 gap-1">
                    {SUS_OPTIONS.map((opt) => {
                      const selected = answers[i] === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          title={opt.label}
                          onClick={() => {
                            const next = [...answers];
                            next[i] = opt.value;
                            setAnswers(next);
                          }}
                          className="text-[11px] py-2 px-1 rounded-lg leading-tight font-medium transition-colors"
                          style={
                            selected
                              ? { background: T.accent, color: '#FFFFFF', border: `1px solid ${T.accent}` }
                              : { background: T.card, color: T.textSecondary, border: `1px solid ${T.border}` }
                          }
                        >
                          {opt.value}
                        </button>
                      );
                    })}
                  </div>
                  <div className="flex justify-between text-[10px] mt-1 px-1" style={{ color: T.textMuted }}>
                    <span>Strongly disagree</span>
                    <span>Strongly agree</span>
                  </div>
                </div>
              ))}
            </div>

            {error && (
              <p className="text-sm mt-4 rounded-lg px-3 py-2" style={{ color: T.errorText, background: T.errorBg }}>
                {error}
              </p>
            )}

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  clearHandoffKeys();
                  navigate('/');
                }}
                className="flex-1 py-2 rounded-lg text-sm font-medium transition-colors"
                style={{ background: T.card, border: `1px solid ${T.border}`, color: T.textSecondary }}
              >
                Skip
              </button>
              <button
                disabled={!allAnswered}
                onClick={handleSubmit}
                className="flex-1 py-2 rounded-lg font-semibold transition-opacity disabled:opacity-40"
                style={{ background: T.accent, color: '#FFFFFF' }}
              >
                Submit
              </button>
            </div>
          </div>
        )}

        {step === STEP.SUBMITTING && (
          <p className="text-center py-10" style={{ color: T.textSecondary }}>Saving your responses…</p>
        )}

        {step === STEP.DONE && (
          <div className="text-center py-6">
            <p className="mb-6" style={{ color: T.textPrimary }}>Thank you — your feedback has been recorded.</p>
            <button
              onClick={() => navigate('/')}
              className="w-full py-2 rounded-lg font-semibold transition-opacity"
              style={{ background: T.accent, color: '#FFFFFF' }}
            >
              Return to Portal
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
