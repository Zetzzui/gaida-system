import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function InformedConsent() {
  const navigate = useNavigate();
  const [isChecked, setIsChecked] = useState(false);

const handleAccept = async (e) => {
  e.preventDefault();
  if (!isChecked) return;

  try {
    // Get session_id from localStorage (set during login)
    const sessionId = localStorage.getItem('session_id') || crypto.randomUUID();

    const response = await fetch(`${import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/api/auth/consent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        consent_given: true,
      }),
    });

    if (!response.ok) throw new Error('Failed to record consent');

    localStorage.setItem('consent_given', 'true');
    localStorage.setItem('session_id', sessionId);
    navigate('/student-dashboard');

  } catch (error) {
    console.error('Consent error:', error);
    alert('Failed to record consent. Please try again.');
  }
};

  const handleDecline = () => {
    // TODO: Log out user
    navigate('/');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 p-4 relative overflow-hidden">
      {/* Decorative Background Pattern */}
      <div className="absolute inset-0 opacity-5">
        <div className="absolute top-20 left-20 w-96 h-96 border-4 border-red-500 rotate-45"></div>
        <div className="absolute bottom-20 right-20 w-80 h-80 border-4 border-red-500 rotate-12"></div>
      </div>

      {/* Grid Pattern Overlay */}
      <div className="absolute inset-0 opacity-10">
        <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" strokeWidth="0.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      {/* Main Content */}
      <div className="relative z-10 bg-white rounded-2xl shadow-2xl p-8 w-full max-w-2xl">
        {/* Header */}
        <div className="flex justify-between items-start mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Informed Consent</h1>
          <div className="text-right">
            <p className="text-sm text-gray-600">User: <span className="font-medium">{localStorage.getItem('student_id') || 'Student'}</span></p>
          </div>
        </div>

        {/* Consent Content - Scrollable */}
        <div className="bg-gray-50 rounded-lg p-6 mb-6 max-h-96 overflow-y-auto border border-gray-200">
          <div className="space-y-4 text-sm text-gray-700">
            {/* Purpose */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Purpose:</h3>
              <p>
                GAIDA (Guidance System with Multimodal Anxiety Detection) uses voice, text, and behavioral analysis 
                to detect anxiety levels and provide guidance support. The system analyzes your interactions to 
                identify signs of anxiety and connect you with appropriate counseling resources.
              </p>
            </div>

            {/* Data Collection */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Data Collection:</h3>
              <p>
                We will collect your text messages, interaction patterns, and behavioral
                data during counseling sessions. All data is linked to your student ID for
                session tracking and counselor review. Data collected includes but is not
                limited to: text input, response times, interaction frequency, and detected
                emotional indicators. If you use voice input, your speech is analyzed for
                acoustic patterns (such as pitch and pacing) and transcribed to text in
                real time; the audio recording itself is not stored after this processing.
              </p>
            </div>

            {/* AI Processing */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">AI Processing:</h3>
              <p>
                To analyze your messages and generate responses, GAIDA sends your text
                input to OpenAI's API, a third-party AI service provider. This means your
                messages are processed on OpenAI's servers as part of how GAIDA works. This
                processing is used only to power the conversation and detection features
                described above, not for any other purpose.
              </p>
            </div>

            {/* Privacy */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Privacy:</h3>
              <p>
                Your data is stored using Supabase cloud infrastructure. At this stage of
                the system's development, access controls and encryption-at-rest for this
                data are still being implemented, so please avoid sharing information you
                would consider highly sensitive (such as account numbers or passwords).
                Your data will not be shared with third parties beyond the AI processing
                described above, without your explicit consent, except as required by law
                or in cases of imminent danger to yourself or others.
              </p>
            </div>

            {/* Limitations */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Limitations:</h3>
              <p>
                GAIDA is an assistive tool and does not replace professional mental health care. It is designed 
                to support early anxiety detection and facilitate counselor intervention, not provide medical 
                diagnosis or treatment. If you are experiencing a mental health emergency, please contact your 
                university counseling center immediately or call emergency services.
              </p>
            </div>

            {/* Session Recording */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Session Recording:</h3>
              <p>
                By accepting, you consent to text and interaction data being recorded during
                your session, and to voice input being analyzed and transcribed in real time
                if you choose to use it (the audio itself is not retained). This data may be
                reviewed by the research team and by authorized counselors for assessment
                and support purposes.
              </p>
            </div>

            {/* Counselor Alerts */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Counselor Alerts:</h3>
              <p>
                If GAIDA detects high anxiety levels or concerning patterns, an alert will be sent to counselors 
                who may reach out to provide support. This is for your safety and wellbeing. Response time may 
                vary based on counselor availability.
              </p>
            </div>

            {/* Rights */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Rights:</h3>
              <p>
                You may withdraw consent and end your session at any time without penalty. You have the right 
                to request access to your session data by contacting the guidance office. You may request 
                deletion of your data, subject to university record-keeping requirements. You can review what 
                data has been collected about you upon request by emailing guidance@ue.edu.ph.
              </p>
            </div>

            {/* Data Retention */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Data Retention:</h3>
              <p>
                Your session data is intended to be retained for counseling continuity and
                quality improvement purposes. Automatic, scheduled deletion after a fixed
                period is not yet implemented in the system; until it is, data is retained
                until you request deletion (see "Rights" above) or the guidance office
                removes it in line with university record-keeping policy.
              </p>
            </div>

            {/* Contact Information */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">Questions or Concerns:</h3>
              <p>
                If you have any questions about this consent form or GAIDA's data practices, please contact the 
                University Guidance Office at guidance@ue.edu.ph or visit the Guidance Office at [Building Name, 
                Room Number].
              </p>
            </div>
          </div>
        </div>

        {/* Consent Checkbox */}
        <div className="mb-6">
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={isChecked}
              onChange={(e) => setIsChecked(e.target.checked)}
              className="mt-1 w-5 h-5 text-red-600 border-gray-300 rounded focus:ring-red-500 cursor-pointer"
            />
            <span className="text-sm text-gray-700 select-none">
              I have read and understood the terms above. I consent to participate in this session 
              and agree to the collection, use, and storage of my data as described.
            </span>
          </label>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4">
          <button
            onClick={handleAccept}
            disabled={!isChecked}
            className={`flex-1 py-3 px-6 rounded-lg font-semibold transition-all duration-200 ${
              isChecked
                ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg hover:shadow-xl'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }`}
          >
            I Accept - Start Session
          </button>
          <button
            onClick={handleDecline}
            className="flex-1 py-3 px-6 rounded-lg font-semibold border-2 border-gray-300 text-gray-700 hover:bg-gray-100 transition-all duration-200"
          >
            Decline & Logout
          </button>
        </div>

        {/* Footer Note */}
        <p className="text-xs text-gray-500 text-center mt-4">
          By clicking "I Accept", you acknowledge that you have read and agree to the terms outlined above.
        </p>
      </div>
    </div>
  );
}