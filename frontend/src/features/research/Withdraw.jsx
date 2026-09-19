import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiFetch from '../../api';

// Lets an anonymous research participant delete everything tied to their
// code: sessions, chat messages, GAD-7/SUS responses, ratings, notes,
// counselor alerts, acoustic logs, and the participant record itself.
// Backed by POST /api/research/withdraw (backend/app/api/research.py) —
// this page is the only way a participant can actually reach that
// endpoint; it's public (no login/token required), matching the fact that
// an anonymous participant has no account to authenticate with, only the
// code they were shown once.
const STEP = { FORM: 0, SUBMITTING: 1, DONE: 2 };

export default function Withdraw() {
  const navigate = useNavigate();
  const [step, setStep] = useState(STEP.FORM);
  const [code, setCode] = useState('');
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!code.trim() || !confirmChecked) return;
    setError('');
    setStep(STEP.SUBMITTING);

    try {
      const res = await apiFetch('/api/research/withdraw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participant_code: code.trim() }),
      });
      if (!res.ok) throw new Error('Request failed');
      const data = await res.json();
      setResult(data);
      setStep(STEP.DONE);
    } catch (err) {
      console.error('Withdraw error:', err);
      setError('Something went wrong submitting your request. Please try again, or email the research team directly if this keeps happening.');
      setStep(STEP.FORM);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-gray-800 rounded-xl shadow-xl p-8">
        <h1 className="text-2xl font-bold mb-1">Withdraw From the Study</h1>
        <p className="text-gray-400 text-sm mb-6">
          For participants who joined anonymously. Entering your code below permanently
          deletes every session, message, and response tied to it — there's no way to
          undo this once it's done.
        </p>

        {step === STEP.FORM && (
          <form onSubmit={handleSubmit}>
            <label className="text-sm text-gray-300">Your anonymous code</label>
            <input
              type="text"
              placeholder="The code you were shown after your first session"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm font-mono"
            />

            <label className="flex items-start gap-2 mt-4 text-sm">
              <input
                type="checkbox"
                checked={confirmChecked}
                onChange={(e) => setConfirmChecked(e.target.checked)}
                className="mt-1"
              />
              I understand this permanently deletes all data tied to this code, and
              cannot be undone.
            </label>

            {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

            <div className="flex gap-3 mt-6">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="flex-1 py-2 rounded-lg border border-gray-600 hover:bg-gray-700 text-sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!code.trim() || !confirmChecked}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:hover:bg-red-600 font-semibold text-sm"
              >
                Delete My Data
              </button>
            </div>
          </form>
        )}

        {step === STEP.SUBMITTING && (
          <p className="text-center text-gray-400 py-10">Processing your request…</p>
        )}

        {step === STEP.DONE && (
          <div className="text-center py-4">
            <p className="text-gray-200 mb-2">
              {result?.deleted_sessions
                ? `Done — ${result.deleted_sessions} session${result.deleted_sessions === 1 ? '' : 's'} and all associated data have been deleted.`
                : 'Done — no data was found for that code, so there was nothing to delete.'}
            </p>
            <p className="text-gray-500 text-xs mb-6">
              If you believe this is a mistake, contact the research team — but note the
              deletion itself cannot be reversed.
            </p>
            <button
              onClick={() => navigate('/')}
              className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 font-semibold text-sm"
            >
              Return to Portal
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
