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
    <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-gray-800 rounded-xl shadow-xl p-8">
        <h1 className="text-2xl font-bold mb-1">One Last Thing</h1>
        <p className="text-gray-400 text-sm mb-6">
          A quick 10-question survey about your experience using GAIDA just now. This
          helps us evaluate how usable the system actually is — there are no right or
          wrong answers.
        </p>

        {step === STEP.SUS && (
          <div>
            <div className="space-y-5 max-h-96 overflow-y-auto pr-1">
              {SUS_QUESTIONS.map((q, i) => (
                <div key={i}>
                  <p className="text-sm mb-2">{i + 1}. {q}</p>
                  <div className="grid grid-cols-5 gap-1">
                    {SUS_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        title={opt.label}
                        onClick={() => {
                          const next = [...answers];
                          next[i] = opt.value;
                          setAnswers(next);
                        }}
                        className={`text-[11px] py-2 px-1 rounded-lg border leading-tight ${
                          answers[i] === opt.value
                            ? 'bg-red-600 border-red-600'
                            : 'border-gray-600 hover:bg-gray-700'
                        }`}
                      >
                        {opt.value}
                      </button>
                    ))}
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500 mt-1 px-1">
                    <span>Strongly disagree</span>
                    <span>Strongly agree</span>
                  </div>
                </div>
              ))}
            </div>

            {error && <p className="text-red-400 text-sm mt-4">{error}</p>}

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  clearHandoffKeys();
                  navigate('/');
                }}
                className="flex-1 py-2 rounded-lg border border-gray-600 hover:bg-gray-700 text-sm"
              >
                Skip
              </button>
              <button
                disabled={!allAnswered}
                onClick={handleSubmit}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:hover:bg-red-600 font-semibold"
              >
                Submit
              </button>
            </div>
          </div>
        )}

        {step === STEP.SUBMITTING && (
          <p className="text-center text-gray-400 py-10">Saving your responses…</p>
        )}

        {step === STEP.DONE && (
          <div className="text-center py-6">
            <p className="text-gray-200 mb-6">Thank you — your feedback has been recorded.</p>
            <button
              onClick={() => navigate('/')}
              className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 font-semibold"
            >
              Return to Portal
            </button>
          </div>
        )}
      </div>
    </div>
  );
}