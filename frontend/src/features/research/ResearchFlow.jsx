import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BACKEND_URL } from '../../config';

// Standard GAD-7 items (Spitzer et al., 2006), asked over the last 2 weeks.
const GAD7_QUESTIONS = [
  'Feeling nervous, anxious, or on edge',
  'Not being able to stop or control worrying',
  'Worrying too much about different things',
  'Trouble relaxing',
  "Being so restless that it's hard to sit still",
  'Becoming easily annoyed or irritable',
  'Feeling afraid as if something awful might happen',
];

const GAD7_OPTIONS = [
  { value: 0, label: 'Not at all' },
  { value: 1, label: 'Several days' },
  { value: 2, label: 'More than half the days' },
  { value: 3, label: 'Nearly every day' },
];

const STEP = { CONSENT: 0, IDENTIFICATION: 1, DEMOGRAPHICS: 2, GAD7: 3, SUBMITTING: 4, SAVE_CODE: 5 };

// -----------------------------------------------------------------------
// TODO: add Reyes's email to RESEARCH_CONTACT_EMAIL once available.
// -----------------------------------------------------------------------
const RESEARCH_TEAM = 'Burlasa, Lazaro, Olazo, Reyes, and Roxas — BS Computer Science, University of the East, Manila';
const RESEARCH_CONTACT_EMAIL = 'lazaro.edward@ue.edu.ph, olazo.davenathaniel@ue.edu.ph, or roxas.jahnvincent@ue.edu.ph';
const CERC_REFERENCE = 'CCSS-CERC Code/Registration ID 2025-1-PTCS-202';

// UE student numbers observed as 4-digit enrollment year + 7-digit sequence
// (e.g. 20240001234) — 11 digits total. This is a format sanity check only,
// not verification: it catches typos and garbage input, not impersonation.
const STUDENT_NUMBER_PATTERN = /^\d{11}$/;
const CURRENT_YEAR = new Date().getFullYear();

function studentNumberError(value) {
  const trimmed = value.trim();
  if (!STUDENT_NUMBER_PATTERN.test(trimmed)) {
    return 'Student number should be 11 digits (e.g. 20240001234).';
  }
  const year = parseInt(trimmed.slice(0, 4), 10);
  if (year < 1946 || year > CURRENT_YEAR) {
    return `The first 4 digits should be your enrollment year — "${trimmed.slice(0, 4)}" doesn't look right.`;
  }
  return null;
}

export default function ResearchFlow() {
  const navigate = useNavigate();
  const [step, setStep] = useState(STEP.CONSENT);
  const [consentChecked, setConsentChecked] = useState(false);
  const [error, setError] = useState('');

  const [anonymous, setAnonymous] = useState(false);
  const [studentNumber, setStudentNumber] = useState('');
  const [hasExistingCode, setHasExistingCode] = useState(false);
  const [existingCode, setExistingCode] = useState('');

  const [demographics, setDemographics] = useState({
    year_level: '',
    program: '',
    gender: '',
    region: '',
  });

  const [answers, setAnswers] = useState(Array(GAD7_QUESTIONS.length).fill(null));
  const [issuedCode, setIssuedCode] = useState(null);

  const allAnswered = answers.every((a) => a !== null);

  const [checkingParticipant, setCheckingParticipant] = useState(false);
  const [skippedDemographics, setSkippedDemographics] = useState(false);

  const handleIdentificationSubmit = async (e) => {
    e.preventDefault();
    if (!anonymous) {
      const formatError = studentNumberError(studentNumber);
      if (formatError) {
        setError(formatError);
        return;
      }
    }
    setError('');
    setCheckingParticipant(true);

    try {
      // Ask the backend whether this participant already has demographics
      // on file — if so, skip asking again. A brand-new anonymous
      // participant (no code yet) always comes back "not returning."
      const res = await fetch(`${BACKEND_URL}/api/research/participant-check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anonymous,
          student_number: anonymous ? null : studentNumber.trim(),
          participant_code: anonymous && hasExistingCode ? existingCode.trim() : null,
        }),
      });
      const { is_returning } = res.ok ? await res.json() : { is_returning: false };
      setSkippedDemographics(is_returning);
      setStep(is_returning ? STEP.GAD7 : STEP.DEMOGRAPHICS);
    } catch (err) {
      console.error('Participant check failed:', err);
      // Fail safe: if the check itself errors, just ask demographics as
      // normal rather than blocking the participant entirely.
      setStep(STEP.DEMOGRAPHICS);
    } finally {
      setCheckingParticipant(false);
    }
  };

  const handleDemographicsSubmit = (e) => {
    e.preventDefault();
    setStep(STEP.GAD7);
  };

  const handleFinalSubmit = async () => {
    if (!allAnswered) return;
    setError('');
    setStep(STEP.SUBMITTING);

    try {
      // 1. Create the session — identified (student number) or anonymous.
      const startRes = await fetch(`${BACKEND_URL}/api/research/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anonymous,
          student_number: anonymous ? null : studentNumber.trim(),
          participant_code: anonymous && hasExistingCode ? existingCode.trim() : null,
          ...demographics,
        }),
      });
      if (!startRes.ok) throw new Error('Could not start a research session');
      const { session_token, session_id, participant_id, participant_code } = await startRes.json();

      // 2. Record consent against that same session_id — same endpoint and
      //    same mechanism the real student flow already uses.
      await fetch(`${BACKEND_URL}/api/auth/consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, consent_given: true }),
      });

      // 3. Submit the GAD-7 answers tied to this session.
      const gad7Res = await fetch(`${BACKEND_URL}/api/research/gad7`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, answers }),
      });
      if (!gad7Res.ok) throw new Error('Could not save your GAD-7 responses');

      // 4. Stage the handoff into the exact same dashboard/chat component
      //    real students use — it only ever reads these localStorage keys.
      localStorage.setItem('session_token', session_token);
      localStorage.setItem('student_id', participant_id);
      localStorage.setItem('session_id', session_id);
      localStorage.setItem('consent_given', 'true');
      localStorage.setItem('is_research_session', 'true');

      if (anonymous && participant_code && !hasExistingCode) {
        // First-time anonymous participant — show their code once before
        // continuing, since it's the only way they can reference this
        // session later.
        setIssuedCode(participant_code);
        setStep(STEP.SAVE_CODE);
      } else {
        navigate('/student-dashboard');
      }
    } catch (err) {
      console.error('Research intake error:', err);
      setError('Something went wrong starting your session. Please try again.');
      setStep(STEP.GAD7);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-gray-800 rounded-xl shadow-xl p-8">
        <h1 className="text-2xl font-bold mb-1">GAIDA Research Participation</h1>
        <p className="text-gray-400 text-sm mb-6">
          Part of an undergraduate thesis study — see below for what that means for you.
        </p>

        {step === STEP.CONSENT && (
          <div>
            <div className="bg-gray-900 rounded-lg p-4 max-h-80 overflow-y-auto text-sm text-gray-300 space-y-3 border border-gray-700">
              <p>
                <strong>What this is:</strong> This is part of an undergraduate thesis study,
                "GAIDA: A Web-based Guidance System with Multimodal Anxiety Detection and
                Virtual Agent," conducted by {RESEARCH_TEAM}. You're invited to chat briefly
                with GAIDA's virtual counselor and complete a short screening
                questionnaire. GAIDA uses artificial intelligence and machine learning to
                detect and classify anxiety levels from your voice and text, and provides
                automated emotional support through a virtual agent. This session is for
                research purposes — to help train and evaluate the system. GAIDA is a
                research tool and not a medical or diagnostic system.
              </p>
              <p>
                <strong>What we collect:</strong> Your typed messages, and if you choose to
                use voice input, your voice recordings will be collected and analyzed —
                speech characteristics such as tone, pitch, and pauses are processed to help
                infer your emotional state; recordings are processed at the time of your
                session and are not stored afterward. We also collect your answers to a
                7-question anxiety screening (GAD-7), and a few optional self-reported
                details (year level, program, gender, region). If you choose to participate
                with your student number, that number is linked to your session for
                follow-up and continuity. If you choose to participate anonymously, no
                student number, name, or email is ever collected — you'll choose this on
                the next screen.
              </p>
              <p>
                <strong>How your data is used and who can see it:</strong> Your responses
                are reviewed by the research team and, for labeling accuracy, by a licensed
                psychologist or guidance counselor. Your text messages may be processed
                using external AI services (such as OpenAI's API) to generate GAIDA's
                replies, and may be transmitted securely to third-party servers for this
                processing. Your data will be used to help train and evaluate the system's
                anxiety-detection model, and may be included in the thesis document,
                presentations, or future research, always without your name attached to any
                quoted excerpt. Your data is stored in the project's Supabase database; at
                this stage of development, that storage is pseudonymous or identified as you
                choose, but is not yet independently encrypted beyond standard
                cloud-provider transport security — please keep that in mind when sharing
                sensitive details.
              </p>
              <p>
                <strong>If you're in distress:</strong> An immediate referral protocol is in
                place for high-risk (Crisis-level) responses, and identified high-risk cases
                are reviewed under counselor supervision. If your session is identified (you
                gave your student number) and GAIDA detects signs of significant distress,
                the research team may follow up or notify the university's Guidance Office.
                If you're participating anonymously, no one is able to be notified about
                you specifically, since we have no way to identify or reach you. Either way,
                GAIDA is not an emergency service. If you are in crisis right now, please
                contact the National Crisis Hotline at 1553 (24/7) or the UE Guidance Office
                directly rather than relying on this session.
              </p>
              <p>
                <strong>Risks and benefits:</strong> Talking about anxiety or stress may
                itself feel uncomfortable for some participants. If GAIDA incorrectly
                classifies your anxiety level, it may fail to identify that you need
                additional support, provide false reassurance, cause emotional distress, or
                delay you from receiving appropriate professional care — this is why
                identified high-risk responses are escalated to a human counselor rather
                than left to the system alone. There is no guaranteed personal benefit to
                you from participating; your contribution helps improve a tool intended to
                support future students.
              </p>
              <p>
                <strong>Your rights:</strong> Participation is voluntary. You may stop at
                any time by closing this page, with no penalty. If you participated with
                your student number, you may request access to or deletion of your data at
                any time by contacting the research team below. If you participated
                anonymously, you may request deletion using the personal code you'll be
                shown, but note that without it we cannot locate or identify your specific
                session. If you are under 18, please also have a parent or guardian review
                this with you before continuing.
              </p>
              <p>
                <strong>Approval and contact:</strong> This study has been reviewed under
                {' '}{CERC_REFERENCE}. Questions or concerns may be directed to{' '}
                {RESEARCH_CONTACT_EMAIL} or the University Guidance Office.
              </p>
            </div>

            <label className="flex items-start gap-2 mt-4 text-sm">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(e) => setConsentChecked(e.target.checked)}
                className="mt-1"
              />
              I have read the above and voluntarily agree to participate.
            </label>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => navigate('/')}
                className="flex-1 py-2 rounded-lg border border-gray-600 hover:bg-gray-700"
              >
                Back
              </button>
              <button
                disabled={!consentChecked}
                onClick={() => setStep(STEP.IDENTIFICATION)}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:hover:bg-red-600 font-semibold"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === STEP.IDENTIFICATION && (
          <form onSubmit={handleIdentificationSubmit}>
            <p className="text-sm text-gray-400 mb-4">
              By default, your student number is linked to your session. You can choose to
              participate anonymously instead.
            </p>

            <div className="space-y-3">
              <label className="flex items-center gap-2 p-3 rounded-lg border border-gray-600 cursor-pointer">
                <input
                  type="radio"
                  checked={!anonymous}
                  onChange={() => setAnonymous(false)}
                />
                <span className="text-sm">Participate with my student number</span>
              </label>

              {!anonymous && (
                <input
                  type="text"
                  placeholder="Student number (e.g. 20240001234)"
                  value={studentNumber}
                  onChange={(e) => setStudentNumber(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm"
                />
              )}

              <label className="flex items-center gap-2 p-3 rounded-lg border border-gray-600 cursor-pointer">
                <input
                  type="radio"
                  checked={anonymous}
                  onChange={() => setAnonymous(true)}
                />
                <span className="text-sm">Participate anonymously</span>
              </label>

              {anonymous && (
                <div className="pl-2 space-y-2">
                  <label className="flex items-center gap-2 text-xs text-gray-400">
                    <input
                      type="checkbox"
                      checked={hasExistingCode}
                      onChange={(e) => setHasExistingCode(e.target.checked)}
                    />
                    I have a code from a previous anonymous session
                  </label>
                  {hasExistingCode && (
                    <input
                      type="text"
                      placeholder="Your previous code"
                      value={existingCode}
                      onChange={(e) => setExistingCode(e.target.value)}
                      className="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm"
                    />
                  )}
                </div>
              )}
            </div>

            {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

            <div className="flex gap-3 mt-6">
              <button
                type="button"
                onClick={() => setStep(STEP.CONSENT)}
                className="flex-1 py-2 rounded-lg border border-gray-600 hover:bg-gray-700"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={checkingParticipant}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 font-semibold"
              >
                {checkingParticipant ? 'Checking…' : 'Continue'}
              </button>
            </div>
          </form>
        )}

        {step === STEP.DEMOGRAPHICS && (
          <form onSubmit={handleDemographicsSubmit}>
            <p className="text-sm text-gray-400 mb-4">
              All optional — leave any field blank if you'd rather not say.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-sm text-gray-300">Year level</label>
                <select
                  value={demographics.year_level}
                  onChange={(e) => setDemographics({ ...demographics, year_level: e.target.value })}
                  className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-lg p-2"
                >
                  <option value="">Prefer not to say</option>
                  <option value="1">1st year</option>
                  <option value="2">2nd year</option>
                  <option value="3">3rd year</option>
                  <option value="4">4th year</option>
                  <option value="5+">5th year or beyond</option>
                </select>
              </div>

              <div>
                <label className="text-sm text-gray-300">Program</label>
                <input
                  type="text"
                  placeholder="e.g. BS Psychology"
                  value={demographics.program}
                  onChange={(e) => setDemographics({ ...demographics, program: e.target.value })}
                  className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-lg p-2"
                />
              </div>

              <div>
                <label className="text-sm text-gray-300">Gender</label>
                <select
                  value={demographics.gender}
                  onChange={(e) => setDemographics({ ...demographics, gender: e.target.value })}
                  className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-lg p-2"
                >
                  <option value="">Prefer not to say</option>
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                  <option value="nonbinary">Non-binary</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div>
                <label className="text-sm text-gray-300">Region / hometown</label>
                <input
                  type="text"
                  placeholder="e.g. Metro Manila, Cebu, Davao"
                  value={demographics.region}
                  onChange={(e) => setDemographics({ ...demographics, region: e.target.value })}
                  className="w-full mt-1 bg-gray-900 border border-gray-600 rounded-lg p-2"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                type="button"
                onClick={() => setStep(STEP.IDENTIFICATION)}
                className="flex-1 py-2 rounded-lg border border-gray-600 hover:bg-gray-700"
              >
                Back
              </button>
              <button
                type="submit"
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 font-semibold"
              >
                Continue
              </button>
            </div>
          </form>
        )}

        {step === STEP.GAD7 && (
          <div>
            <p className="text-sm text-gray-400 mb-4">
              Over the last 2 weeks, how often have you been bothered by the following?
            </p>

            <div className="space-y-5 max-h-96 overflow-y-auto pr-1">
              {GAD7_QUESTIONS.map((q, i) => (
                <div key={i}>
                  <p className="text-sm mb-2">{i + 1}. {q}</p>
                  <div className="grid grid-cols-2 gap-2">
                    {GAD7_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => {
                          const next = [...answers];
                          next[i] = opt.value;
                          setAnswers(next);
                        }}
                        className={`text-xs py-2 px-2 rounded-lg border ${
                          answers[i] === opt.value
                            ? 'bg-red-600 border-red-600'
                            : 'border-gray-600 hover:bg-gray-700'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {error && <p className="text-red-400 text-sm mt-4">{error}</p>}

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setStep(skippedDemographics ? STEP.IDENTIFICATION : STEP.DEMOGRAPHICS)}
                className="flex-1 py-2 rounded-lg border border-gray-600 hover:bg-gray-700"
              >
                Back
              </button>
              <button
                disabled={!allAnswered}
                onClick={handleFinalSubmit}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:hover:bg-red-600 font-semibold"
              >
                Start Chat
              </button>
            </div>
          </div>
        )}

        {step === STEP.SUBMITTING && (
          <p className="text-center text-gray-400 py-10">Setting up your session…</p>
        )}

        {step === STEP.SAVE_CODE && (
          <div>
            <p className="text-sm text-gray-300 mb-3">
              Save this code — it's the only way to reference this session later
              (to request deletion, or to continue as the same anonymous participant
              next time). We have no other way to identify your session.
            </p>
            <div className="bg-gray-900 border border-gray-600 rounded-lg p-4 text-center text-xl font-mono tracking-widest mb-4">
              {issuedCode}
            </div>
            <button
              onClick={() => navigate('/student-dashboard')}
              className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 font-semibold"
            >
              I've saved my code — Continue
            </button>
          </div>
        )}
      </div>
    </div>
  );
}