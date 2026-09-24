import { useNavigate } from 'react-router-dom'

export default function PortalSelection() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen relative overflow-hidden flex items-center justify-center">

      {/* Full bleed UE background */}
      <div
        className="absolute inset-0 bg-center bg-cover bg-no-repeat"
        style={{ backgroundImage: "url('https://www.ue.edu.ph/mla/wp-content/uploads/2023/04/uesocialogp.png')" }}
      />

      {/* White card */}
      <div className="relative z-10 bg-white rounded-2xl shadow-2xl p-10 w-full max-w-md mx-4">

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img
            src="https://www.ue.edu.ph/mla/wp-content/uploads/2020/12/UE_RED_SEAL_09.png"
            alt="University of the East"
            className="w-24 h-24 object-cover object-right rounded-full mb-4 shadow-lg border-4 border-red-700"
          />
          <h1 className="text-3xl font-bold text-gray-900">GAIDA</h1>
          <p className="text-gray-500 text-sm text-center mt-1">Guidance System with Multimodal Anxiety Detection</p>
        </div>

        {/* Portal buttons */}
        <div className="space-y-3">
          <button
            onClick={() => navigate('/student-login')}
            className="w-full flex items-center gap-4 px-5 py-4 rounded-xl border-2 border-gray-100 hover:border-red-600 hover:bg-red-50 transition-all duration-200 group"
          >
            <div className="w-12 h-12 bg-gradient-to-br from-orange-500 to-orange-600 rounded-full flex items-center justify-center flex-shrink-0 shadow group-hover:scale-105 transition-transform duration-200">
              <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="text-left flex-1">
              <h3 className="text-gray-900 font-semibold text-base">Student Portal</h3>
              <p className="text-gray-400 text-xs mt-0.5">Virtual agent support and anxiety detection</p>
            </div>
            <svg className="w-4 h-4 text-gray-300 group-hover:text-red-500 group-hover:translate-x-1 transition-all duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>

          <button
            onClick={() => navigate('/counselor-login')}
            className="w-full flex items-center gap-4 px-5 py-4 rounded-xl border-2 border-gray-100 hover:border-red-600 hover:bg-red-50 transition-all duration-200 group"
          >
            <div className="w-12 h-12 bg-gradient-to-br from-red-600 to-red-800 rounded-full flex items-center justify-center flex-shrink-0 shadow group-hover:scale-105 transition-transform duration-200">
              <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
              </svg>
            </div>
            <div className="text-left flex-1">
              <h3 className="text-gray-900 font-semibold text-base">Counselor Dashboard</h3>
              <p className="text-gray-400 text-xs mt-0.5">Monitor alerts and student sessions</p>
            </div>
            <svg className="w-4 h-4 text-gray-300 group-hover:text-red-500 group-hover:translate-x-1 transition-all duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>

          <button
            onClick={() => navigate('/research')}
            className="w-full flex items-center gap-4 px-5 py-4 rounded-xl border-2 border-gray-100 hover:border-red-600 hover:bg-red-50 transition-all duration-200 group"
          >
            <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-purple-700 rounded-full flex items-center justify-center flex-shrink-0 shadow group-hover:scale-105 transition-transform duration-200">
              <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="text-left flex-1">
              <h3 className="text-gray-900 font-semibold text-base">Research Participation</h3>
              <p className="text-gray-400 text-xs mt-0.5">Help improve GAIDA — student number or anonymous</p>
            </div>
            <svg className="w-4 h-4 text-gray-300 group-hover:text-red-500 group-hover:translate-x-1 transition-all duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        <p className="text-center text-gray-400 text-xs mt-6">University of the East — Guidance &amp; Counseling Office</p>
        <button
          onClick={() => navigate('/research/withdraw')}
          className="block w-full text-center text-gray-300 text-xs mt-2 underline hover:text-red-600"
        >
          Withdraw from the research study
        </button>
      </div>
    </div>
  );
}