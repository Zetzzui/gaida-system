import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import VoiceInput from "../voice/VoiceInput";
import ReactMarkdown from 'react-markdown';

// ─────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────

import { BACKEND_URL as BACKEND } from '../../config';
import apiFetch from '../../api';
const POLL_INTERVAL = 3000;
const TYPING_DEBOUNCE = 2000;

const THEMES = {
  purple: {
    name: 'purple',
    preview: '#7c6af7',
    bg: '#0d0b1a',
    sidebar: '#12102a',
    border: '#1e1a40',
    accent: '#7c6af7',
    accentDark: '#3d2fa0',
    textPrimary: '#a89cf7',
    textSecondary: '#6b5fd4',
    textMuted: '#3d3580',
    userBubble: '#3d2fa0',
    userText: '#e8e4ff',
    botBubble: '#12102a',
    botText: '#a89cf7',
  },
  navy: {
    name: 'navy',
    preview: '#378add',
    bg: '#0c1220',
    sidebar: '#101929',
    border: '#1a2f4a',
    accent: '#378add',
    accentDark: '#1a4a7a',
    textPrimary: '#93b4d9',
    textSecondary: '#4a7aaa',
    textMuted: '#1e3a5a',
    userBubble: '#1a4a7a',
    userText: '#e0eef8',
    botBubble: '#101929',
    botText: '#93b4d9',
  },
  charcoal: {
    name: 'charcoal',
    preview: '#ba7517',
    bg: '#111010',
    sidebar: '#1a1817',
    border: '#2d2520',
    accent: '#ba7517',
    accentDark: '#7c4a2a',
    textPrimary: '#d4b896',
    textSecondary: '#7a6050',
    textMuted: '#3d2e28',
    userBubble: '#7c4a2a',
    userText: '#fdf0e0',
    botBubble: '#1a1817',
    botText: '#d4b896',
  },
  forest: {
    name: 'forest',
    preview: '#5dcaa5',
    bg: '#0a1a14',
    sidebar: '#0f2318',
    border: '#1a3527',
    accent: '#5dcaa5',
    accentDark: '#1d6a4a',
    textPrimary: '#a8d9c0',
    textSecondary: '#3e7a5e',
    textMuted: '#2d5a45',
    userBubble: '#1d6a4a',
    userText: '#e8f5ee',
    botBubble: '#0f2318',
    botText: '#a8d9c0',
  },
};

const SEVERITY_CONFIG = {
  Crisis:   { bar: 'bg-red-600',     text: 'text-red-400',     border: 'border-red-800',     width: 'w-full' },
  High:     { bar: 'bg-amber-500',   text: 'text-amber-400',   border: 'border-amber-800',   width: 'w-4/5' },
  Moderate: { bar: 'bg-teal-400',    text: 'text-teal-300',    border: 'border-teal-700',    width: 'w-2/4' },
  Low:      { bar: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-800', width: 'w-1/4' },
  Normal:   { bar: 'bg-slate-500',   text: 'text-slate-400',   border: 'border-slate-700',   width: 'w-0'   },
};

// Quick-start prompts shown when the conversation is empty.
// Lowers the barrier for a student who doesn't know how to start.
const QUICK_START_PROMPTS = [
  { icon: 'school',      text: "I'm stressed about my exams" },
  { icon: 'message-2',   text: "I just want to talk to someone" },
  { icon: 'cloud-rain',  text: "Things have been hard lately" },
];

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

const mapConfidenceToSeverity = (conf) => {
  if (conf >= 0.75) return 'High';
  if (conf >= 0.60) return 'Moderate';
  if (conf >= 0.45) return 'Low';
  return 'Normal';
};

const formatTime = (seconds) => {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
};

const formatMsgTime = (date) => {
  if (!date) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────

function TypingBubble({ color }) {
  return (
    <div className="flex gap-1 items-center h-4">
      {[0, 150, 300].map((delay) => (
        <div
          key={delay}
          className="w-1.5 h-1.5 rounded-full animate-bounce"
          style={{ background: color, animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

function Avatar({ role, accent }) {
  const isCounselor = role === 'counselor';
  const bg = isCounselor ? '#0e2a45' : 'transparent';
  const border = isCounselor ? '1px solid #1a4a6e' : `1px solid ${accent}`;
  const color = isCounselor ? '#7eb8d9' : accent;
  const label = isCounselor ? 'C' : 'G';

  return (
    <div
      className="w-6 h-6 sm:w-7 sm:h-7 rounded-full flex items-center justify-center flex-shrink-0 mb-0.5"
      style={{ background: bg, border }}
    >
      <span className="text-xs font-bold" style={{ color }}>{label}</span>
    </div>
  );
}

function MessageBubble({ message, theme, onFeedback, feedback }) {
  const { role, text, isVoice, acoustic, timestamp } = message;

  const bubbleStyle =
    role === 'user'
      ? { background: theme.userBubble, color: theme.userText, borderRadius: '16px 16px 4px 16px' }
      : role === 'counselor'
      ? { background: '#0e2a45', color: '#b5d4f4', border: '1px solid #1a4a6e', borderRadius: '4px 16px 16px 16px' }
      : { background: theme.botBubble, color: theme.botText, border: `1px solid ${theme.border}`, borderRadius: '4px 16px 16px 16px' };

  return (
    <div className={`flex flex-col gap-0.5 max-w-[78%] sm:max-w-[72%] lg:max-w-[65%] ${role === 'user' ? 'items-end' : 'items-start'}`}>
      <div className="px-4 sm:px-5 py-3 sm:py-3.5 text-sm leading-relaxed" style={{ ...bubbleStyle, lineHeight: 1.6 }}>
        {isVoice && (
          <div className="flex items-center gap-1 mb-1" style={{ opacity: 0.6 }}>
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1a4 4 0 014 4v6a4 4 0 01-8 0V5a4 4 0 014-4zm-1 17.93V21H9v2h6v-2h-2v-2.07A8.001 8.001 0 0020 11h-2a6 6 0 01-12 0H4a8.001 8.001 0 007 7.93z" />
            </svg>
            <span className="text-xs">Voice</span>
          </div>
        )}

        {role === 'user' ? (
          <span>{text}</span>
        ) : (
          <ReactMarkdown
            components={{
              p:      ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
              strong: ({ children }) => <strong className="font-bold" style={{ color: theme.userText }}>{children}</strong>,
              ul:     ({ children }) => <ul className="list-disc list-inside mt-1 space-y-0.5">{children}</ul>,
              li:     ({ children }) => <li className="text-sm">{children}</li>,
              h1: () => null,
              h2: () => null,
              h3: () => null,
            }}
          >
            {text}
          </ReactMarkdown>
        )}
      </div>

      {timestamp && (
        <span className="text-xs px-1" style={{ color: theme.textMuted }}>
          {formatMsgTime(timestamp)}
        </span>
      )}

      {role === 'bot' && acoustic && (
        <div className="flex items-center gap-2 px-1">
          <span className="text-xs" style={{ color: theme.textMuted }}>Voice detected:</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${
            acoustic.emotion === 'anxious'   ? 'text-yellow-400 border-yellow-800 bg-yellow-900/30' :
            acoustic.emotion === 'sad'       ? 'text-blue-400 border-blue-800 bg-blue-900/30' :
            acoustic.emotion === 'angry'     ? 'text-red-400 border-red-800 bg-red-900/30' :
            acoustic.emotion === 'stressed'  ? 'text-orange-400 border-orange-800 bg-orange-900/30' :
            acoustic.emotion === 'calm'      ? 'text-emerald-400 border-emerald-800 bg-emerald-900/30' :
            acoustic.emotion === 'withdrawn' ? 'text-purple-400 border-purple-800 bg-purple-900/30' :
                                               'text-gray-400 border-gray-700 bg-gray-800/30'
          }`}>
            {acoustic.emotion}
          </span>
          <span className="text-xs" style={{ color: theme.textMuted }}>{acoustic.severity}</span>
        </div>
      )}

      {role === 'bot' && onFeedback && (
        <div className="flex items-center gap-1.5 px-1 pt-1">
          {[
            { k: 'up', label: 'Helpful' },
            { k: 'down', label: 'Not helpful' },
          ].map((opt) => (
            <button
              key={opt.k}
              onClick={() => onFeedback(opt.k)}
              disabled={!!feedback}
              className="text-[11px] px-2 py-0.5 rounded-full border transition-colors disabled:opacity-45"
              style={{
                background: feedback === opt.k ? theme.accentDark : 'transparent',
                color: feedback === opt.k ? theme.userText : theme.textSecondary,
                border: `1px solid ${theme.border}`,
              }}
            >
              {feedback === opt.k ? '\u2713 ' : ''}{opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────

export default function StudentDashboard() {
  const navigate = useNavigate();

  // ── State ────────────────────────────────────────────────────
  const [messages,          setMessages]          = useState([]);
  const [input,             setInput]             = useState('');
  const [sending,           setSending]           = useState(false);
  const [severity,          setSeverity]          = useState('Normal');
  const [sessionTime,       setSessionTime]       = useState(0);
  const [sidebarOpen,       setSidebarOpen]       = useState(false);
  const [voiceStatus,       setVoiceStatus]       = useState('');
  const [counselorTyping,   setCounselorTyping]   = useState(false);
  const [counselorActive,   setCounselorActive]   = useState(false);
  const [ventMode,          setVentMode]          = useState(false);
  const [showSettings,      setShowSettings]      = useState(false);
  const [requestingCounselor, setRequestingCounselor] = useState(false);
  const [counselorRequested,  setCounselorRequested]  = useState(false);
  const [streamingStarted,    setStreamingStarted]    = useState(false);

  // ── Rating state ─────────────────────────────────────────────
  const [showRating,        setShowRating]        = useState(false);
  const [ratingSubmitted,   setRatingSubmitted]   = useState(false);
  const [hoveredRating,     setHoveredRating]     = useState(null);

  // Per-message helpfulness feedback: message index -> 'up' | 'down'
  const [messageRatings, setMessageRatings] = useState({});

  const [theme, setTheme] = useState(
    () => THEMES[localStorage.getItem('gaida_theme')] || THEMES.purple
  );

  // ── Refs ─────────────────────────────────────────────────────
  const containerRef       = useRef(null);
  const timerRef           = useRef(null);
  const inputRef           = useRef(null);
  const lastCounselorCount = useRef(0);
  const typingTimeout      = useRef(null);
  const wasCounselorActive = useRef(false);

  const severityConfig = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.Normal;

  // ── Wellbeing rating options ──────────────────────────────────
  const WELLBEING_OPTIONS = [
    { value: 1, emoji: '😔', label: 'Much worse' },
    { value: 2, emoji: '😐', label: 'About the same' },
    { value: 3, emoji: '🙂', label: 'A little better' },
    { value: 4, emoji: '😊', label: 'Much better' },
  ];

  // ── Auth + session reset on mount ────────────────────────────
  useEffect(() => {
    const token   = localStorage.getItem('session_token');
    // Feature 3: check-in prompt for returning High/Crisis students
    const studentId = localStorage.getItem('student_id');
    if (studentId) {
      apiFetch(`${BACKEND}/api/counselor/student/checkin/${studentId}`)
        .then(r => r.json())
        .then(data => {
          if (data.needs_checkin) {
            setMessages([{
              role: 'bot',
              text: data.peak_severity === 'Crisis'
                ? "Kumusta ka na? Last time we talked, you were going through something really heavy. How have you been feeling since then?"
                : "Hey, kumusta? It's been a few days since we last talked - just checking in. How are you feeling today?",
              timestamp: new Date(),
              isCheckin: true,
            }]);
          }
        })
        .catch(() => {});
    }
    const consent = localStorage.getItem('consent_given');
    if (!token)   { navigate('/student-login'); return; }
    if (!consent) { navigate('/consent');       return; }

    setSidebarOpen(window.innerWidth >= 1024);
    timerRef.current = setInterval(() => setSessionTime(t => t + 1), 1000);
    return () => clearInterval(timerRef.current);
  }, [navigate]);

  // ── Auto-scroll ───────────────────────────────────────────────
  useEffect(() => {
    containerRef.current?.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, voiceStatus, counselorTyping]);

  // ── Counselor poll ────────────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      const sessionId = localStorage.getItem('session_id');
      if (!sessionId) return;

      try {
        const res  = await apiFetch(`${BACKEND}/api/counselor/chat/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.messages) return;

        if (data.messages.some(m => m.sender === 'counselor')) setCounselorActive(true);
        setCounselorTyping(data.counselor_typing || false);

        // ── Detect counselor returning control to GAIDA ───────
        const isCounselorActiveNow = data.counselor_active || false;
        if (wasCounselorActive.current && !isCounselorActiveNow) {
          setCounselorActive(false);
          setMessages(prev => [...prev, { role: 'system', text: 'GAIDA has resumed the conversation.' }]);
        }
        wasCounselorActive.current = isCounselorActiveNow;

        const counselorMsgs = data.messages.filter(m => m.sender === 'counselor');
        if (counselorMsgs.length > lastCounselorCount.current) {
          if (lastCounselorCount.current === 0) {
            setMessages(prev => [...prev, { role: 'system', text: 'A counselor has joined your session.' }]);
          }
          setMessages(prev => [
            ...prev,
            ...counselorMsgs.slice(lastCounselorCount.current).map(m => ({
              role: 'counselor', text: m.text, timestamp: new Date(),
            })),
          ]);
          lastCounselorCount.current = counselorMsgs.length;
        }
      } catch (e) {
        console.error('Poll chat error:', e);
      }
    };

    const interval = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  // ── PWA offline queue sync ────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.response?.response) {
        setMessages(prev => [...prev, {
          role: 'bot', text: e.detail.response.response,
          timestamp: new Date(), synced: true,
        }]);
      }
    };
    window.addEventListener('gaida:queue-synced', handler);
    return () => window.removeEventListener('gaida:queue-synced', handler);
  }, []);

  // ── Handlers ─────────────────────────────────────────────────
  const fireTyping = useCallback((isTyping) => {
    const sessionId = localStorage.getItem('session_id');
    if (!sessionId) return;
    apiFetch(`${BACKEND}/api/counselor/typing/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender: 'student', is_typing: isTyping }),
    }).catch((e) => { console.error('Typing indicator error:', e); });
  }, []);

  const handleInputChange = (e) => {
    setInput(e.target.value);
    fireTyping(true);
    clearTimeout(typingTimeout.current);
    typingTimeout.current = setTimeout(() => fireTyping(false), TYPING_DEBOUNCE);
  };

  const handleEndSession = () => {
    setShowRating(true);
  };

  const submitRating = async (rating) => {
    const sessionId = localStorage.getItem('session_id');
    if (sessionId) {
      try {
        await apiFetch(`${BACKEND}/api/counselor/session/rate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            wellbeing_rating: rating,
            severity_at_end: severity,
          }),
        });
      } catch (e) {
        console.error('Submit rating error:', e);
      }
    }
    confirmEndSession();
  };

  const sendMessage = async (textOverride) => {
    const text = (textOverride ?? input).trim();
    if (!text || sending) return;

    clearTimeout(typingTimeout.current);
    fireTyping(false);

    setMessages(prev => [...prev, { role: 'user', text, timestamp: new Date() }]);
    setInput('');
    setSending(true);
    setStreamingStarted(false);
    if (window.innerWidth < 1024) setSidebarOpen(false);

    const sessionId = localStorage.getItem('session_id');
    const token     = localStorage.getItem('session_token');

    try {
      const res = await apiFetch(`${BACKEND}/virtual-agent/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { Authorization: `Bearer ${token}` }),
        },
        body: JSON.stringify({
          message:    text,
          session_id: sessionId,
          user_id: localStorage.getItem('student_id'),
          intent:     ventMode ? 'venting' : 'unknown',
          vent_mode:  ventMode,
        }),
      });

      if (!res.ok || !res.body) {
        const err = await res.text().catch(() => String(res.status));
        setMessages(prev => [...prev, { role: 'bot', text: `Error: ${err || res.status}`, timestamp: new Date() }]);
        return;
      }

      let botMsg = null;

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const appendOrUpdateBot = (next) => {
        if (!botMsg) {
          botMsg = next;
          setMessages(prev => [...prev, botMsg]);
        } else {
          botMsg = next;
          setMessages(prev => [...prev.slice(0, -1), botMsg]);
        }
      };

      const processLine = (line) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        let event;
        try { event = JSON.parse(trimmed); } catch { return; }

        if (event.type === 'delta') {
          setStreamingStarted(true);
          const prevText = botMsg ? botMsg.text : '';
          appendOrUpdateBot({
            role: 'bot',
            text: prevText + event.text,
            timestamp: botMsg ? botMsg.timestamp : new Date(),
          });
        } else if (event.type === 'done') {
          const result = event.result || {};
          if (result.session_id)       localStorage.setItem('session_id', result.session_id);
          if (result.severity)         setSeverity(result.severity);
          if (result.counselor_active) setCounselorActive(true);

          if (!result.counselor_active && (!botMsg || !botMsg.text) && result.response) {
            appendOrUpdateBot({ role: 'bot', text: result.response, timestamp: new Date() });
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep the incomplete last line for the next chunk
        lines.forEach(processLine);
      }

      // Body may end without a trailing newline (e.g. SW offline reply) — parse the tail.
      if (buffer.trim()) processLine(buffer);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'bot', text: `Connection error: ${err.message}`, timestamp: new Date(),
      }]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const handleRequestCounselor = async () => {
    const sessionId = localStorage.getItem('session_id');
    if (!sessionId) return;
    setRequestingCounselor(true);
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/request-counselor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json();
      if (data.ok) {
        setCounselorRequested(true);
        setMessages(prev => [...prev, {
          role: 'system',
          text: 'A counselor has been notified and will join shortly.',
        }]);
      }
    } catch (e) {
      console.error('Request counselor error:', e);
    } finally {
      setRequestingCounselor(false);
    }
  };

  // ── Per-message helpfulness feedback ─────────────────────────
  const rateMessage = useCallback((index, value) => {
    if (messageRatings[index]) return;
    const m = messages[index];
    const sessionId = localStorage.getItem('session_id');
    setMessageRatings(prev => ({ ...prev, [index]: value }));
    apiFetch(`${BACKEND}/api/session/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message_index: index,
        message_text: m?.text || '',
        rating: value === 'up' ? 'helpful' : 'not_helpful',
      }),
    }).catch(() => {});
  }, [messageRatings, messages]);

  // ── Session end + wellbeing rating ───────────────────────────
  const endSession = () => {
    if (messages.length > 0) {
      setShowRating(true);
    } else {
      confirmEndSession();
    }
  };

  const confirmEndSession = async () => {
    const sessionId = localStorage.getItem('session_id');
    if (sessionId) {
      try {
        await apiFetch(`${BACKEND}/api/session/${sessionId}/end`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
      } catch (e) {
        console.error('End session error:', e);
      }
    }
    const wasResearchSession = localStorage.getItem('is_research_session') === 'true';

    // For a research session, session_id AND session_token are deliberately
    // kept — the post-session SUS usability survey (ResearchSUS.jsx) needs
    // session_id to know which session its answers belong to, and needs
    // session_token so its apiFetch call to /api/research/sus can still
    // authenticate (that endpoint requires a bearer token, same as
    // /api/research/gad7). ResearchSUS.jsx clears both itself once the
    // participant finishes or skips that page. A real (non-research)
    // student session still clears everything immediately, as before.
    const keysToClear = wasResearchSession
      ? ['student_id', 'consent_given', 'is_research_session']
      : ['session_token', 'student_id', 'consent_given', 'session_id', 'is_research_session'];
    keysToClear.forEach(k => localStorage.removeItem(k));

    navigate(wasResearchSession ? '/research-sus' : '/student-login');
  };

  const handleWellbeingRating = async (value) => {
    setRatingSubmitted(true);
    const sessionId = localStorage.getItem('session_id');
    if (sessionId) {
      try {
        await apiFetch(`${BACKEND}/api/counselor/session/rate`, {  
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            wellbeing_rating: value,
            severity_at_end: severity,
          }),
        });
      } catch (e) {
        console.error('Wellbeing rating error:', e);
      }
    }
    setTimeout(() => confirmEndSession(), 1800);
  };

  const switchTheme = (key) => {
    setTheme(THEMES[key]);
    localStorage.setItem('gaida_theme', key);
  };

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────
  return (
    <div
      className="min-h-screen max-h-screen flex overflow-hidden font-sans"
      style={{ background: theme.bg }}
    >
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 lg:hidden"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ──────────────────────────────────────────── */}
      <aside
        className={`
          fixed lg:relative z-30 lg:z-auto top-0 left-0
          transition-transform duration-300 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          w-64 flex flex-col flex-shrink-0 h-full min-h-screen
        `}
        style={{ background: theme.sidebar, borderRight: `1px solid ${theme.border}` }}
      >
        {/* Logo */}
        <div className="p-5 flex items-center justify-between" style={{ borderBottom: `1px solid ${theme.border}` }}>
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: `linear-gradient(135deg, ${theme.accentDark}, ${theme.sidebar})` }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M9 2C5 2 2 6 2 9c0 4 3 7 7 7s7-3 7-7c0-3-3-7-7-7z" fill="none" stroke={theme.accent} strokeWidth="1.2" />
                <path d="M9 5v8M6 8l3-3 3 3" stroke={theme.accent} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div>
              <p className="font-bold tracking-widest text-sm" style={{ color: theme.textPrimary }}>GAIDA</p>
              <p className="text-xs" style={{ color: theme.textMuted }}>Guidance System</p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1"
            style={{ color: theme.textMuted }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Session stats */}
        <div className="p-4" style={{ borderBottom: `1px solid ${theme.border}` }}>
          <p className="text-xs uppercase tracking-widest mb-3" style={{ color: theme.textMuted }}>Session</p>
          <div className="space-y-2">
            {[['Duration', formatTime(sessionTime)], ['Messages', messages.length]].map(([label, value]) => (
              <div key={label} className="flex justify-between items-center">
                <span className="text-xs" style={{ color: theme.textSecondary }}>{label}</span>
                <span className="text-xs font-bold" style={{ color: theme.textPrimary }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Anxiety Level */}
        <div className="p-4" style={{ borderBottom: `1px solid ${theme.border}` }}>
          <p className="text-xs uppercase tracking-widest mb-3" style={{ color: theme.textMuted }}>Anxiety Level</p>
          <div
            className={`p-3 rounded-lg border ${severityConfig.border}`}
            style={{ background: theme.bg }}
          >
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs" style={{ color: theme.textSecondary }}>Detected</span>
              <span className={`text-xs font-bold ${severityConfig.text}`}>{severity}</span>
            </div>
            <div className="w-full rounded-full h-1.5" style={{ background: theme.border }}>
              <div className={`${severityConfig.bar} ${severityConfig.width} h-1.5 rounded-full transition-all duration-700`} />
            </div>
          </div>
        </div>

        {/* Vent Mode Toggle */}
        <div className="p-4" style={{ borderBottom: `1px solid ${theme.border}` }}>
          <p className="text-xs uppercase tracking-widest mb-3" style={{ color: theme.textMuted }}>Mode</p>
          <div className="flex rounded-lg overflow-hidden" style={{ border: `1px solid ${theme.border}` }}>
            <button
              onClick={() => setVentMode(false)}
              className="flex-1 py-1.5 text-xs font-bold transition-all duration-200"
              style={{
                background: !ventMode ? theme.accentDark : 'transparent',
                color: !ventMode ? theme.userText : theme.textSecondary,
              }}
            >
              💬 Talk
            </button>
            <button
              onClick={() => setVentMode(true)}
              className="flex-1 py-1.5 text-xs font-bold transition-all duration-200"
              style={{
                background: ventMode ? theme.accentDark : 'transparent',
                color: ventMode ? theme.userText : theme.textSecondary,
              }}
            >
              🗣️ Vent
            </button>
          </div>
          {ventMode && (
            <p className="text-xs mt-2" style={{ color: theme.textMuted }}>
              GAIDA will just listen — no advice, no redirects.
            </p>
          )}
        </div>

        {/* Talk to a Counselor */}
        <div className="p-4" style={{ borderBottom: `1px solid ${theme.border}` }}>
          {counselorRequested || counselorActive ? (
            <div
              className="w-full py-2 px-3 text-xs rounded-lg text-center font-medium"
              style={{ background: theme.border, color: theme.textSecondary }}
            >
              {counselorActive ? '✓ Counselor is with you' : '⏳ Counselor notified'}
            </div>
          ) : (
            <button
              onClick={handleRequestCounselor}
              disabled={requestingCounselor}
              className="w-full py-2 px-3 text-xs font-bold rounded-lg tracking-wide transition-all duration-200 disabled:opacity-50"
              style={{ background: theme.accentDark, color: theme.userText, border: `1px solid ${theme.accent}` }}
            >
              {requestingCounselor ? 'Requesting...' : '🧑‍⚕️ Talk to a Counselor'}
            </button>
          )}
        </div>

        {/* Crisis resources — always visible, not conditional on detected severity */}
        <div className="p-4" style={{ borderBottom: `1px solid ${theme.border}` }}>
          <p className="text-xs uppercase tracking-widest mb-2" style={{ color: theme.textMuted }}>
            In Crisis?
          </p>
          <div
            className="rounded-lg p-3 text-xs leading-relaxed"
            style={{ background: theme.bg, border: `1px solid ${theme.border}`, color: theme.textSecondary }}
          >
            <p>National Crisis Hotline: <strong style={{ color: theme.textPrimary }}>1553</strong> (24/7)</p>
            <p className="mt-1">In Touch Crisis Line: <strong style={{ color: theme.textPrimary }}>(02) 893-7603</strong></p>
            <p className="mt-1">If in immediate danger, call <strong style={{ color: theme.textPrimary }}>911</strong>.</p>
          </div>
        </div>

        {/* Settings */}
        <div className="p-4 flex-1">
          <button
            onClick={() => setShowSettings(p => !p)}
            className="flex items-center justify-between w-full"
          >
            <p className="text-xs uppercase tracking-widest" style={{ color: theme.textMuted }}>Settings</p>
            <svg
              className={`w-3 h-3 transition-transform ${showSettings ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
              style={{ color: theme.textMuted }}
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showSettings && (
            <div className="mt-3 space-y-4">
              {/* Theme Picker */}
              <div>
                <p className="text-xs mb-2" style={{ color: theme.textSecondary }}>Theme</p>
                <div className="flex gap-2">
                  {Object.entries(THEMES).map(([key, t]) => (
                    <button
                      key={key}
                      onClick={() => switchTheme(key)}
                      title={key}
                      style={{
                        width: '22px', height: '22px', borderRadius: '50%',
                        background: t.preview,
                        border: theme.name === key ? `2px solid ${theme.textPrimary}` : '2px solid transparent',
                        outline: theme.name === key ? `2px solid ${t.preview}` : 'none',
                        outlineOffset: '2px', cursor: 'pointer', transition: 'all 0.2s',
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Quick Tips */}
              <div>
                <p className="text-xs mb-2" style={{ color: theme.textSecondary }}>Tips</p>
                <div className="space-y-1.5 text-xs leading-relaxed" style={{ color: theme.textMuted }}>
                  <p>Press Enter to send a message.</p>
                  <p>Use the mic button for voice input.</p>
                  <p>This conversation is kept confidential to help your counselor support you.</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* End Session */}
        <div className="p-4" style={{ borderTop: `1px solid ${theme.border}` }}>
          <button
            onClick={endSession}
            className="w-full py-2 px-4 text-xs font-bold rounded-lg tracking-widest uppercase transition-all duration-200"
            style={{ background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textSecondary }}
            onMouseEnter={e => { e.currentTarget.style.background = theme.border; e.currentTarget.style.color = theme.textPrimary; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = theme.textSecondary; }}
          >
            End Session
          </button>
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 h-screen">

        {/* Topbar */}
        <div
          className="h-14 flex items-center px-4 gap-3 flex-shrink-0"
          style={{ background: theme.sidebar, borderBottom: `1px solid ${theme.border}` }}
        >
          <button
            onClick={() => setSidebarOpen(p => !p)}
            className="flex-shrink-0 p-1 transition-colors"
            style={{ color: theme.textSecondary }}
            onMouseEnter={e => e.currentTarget.style.color = theme.textPrimary}
            onMouseLeave={e => e.currentTarget.style.color = theme.textSecondary}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <span className="text-xs sm:text-sm font-bold tracking-widest truncate" style={{ color: theme.textPrimary }}>
            VIRTUAL COUNSELOR
          </span>

          <div
            className={`ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-bold ${severityConfig.text} ${severityConfig.border}`}
            style={{ background: theme.bg }}
          >
            <div className={`w-1.5 h-1.5 rounded-full ${severityConfig.bar}`} />
            <span className="hidden sm:inline">{severity}</span>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: theme.accent }} />
            <span className="text-xs hidden sm:inline" style={{ color: theme.accent }}>
              {ventMode ? '🗣️ Vent Mode' : counselorActive ? '🧑‍⚕️ Counselor Active' : 'Online'}
            </span>
          </div>
        </div>

        {/* Chat */}
        <div
          ref={containerRef}
          className="flex-1 overflow-y-auto px-3 sm:px-6 py-4 space-y-3"
          style={{ background: theme.bg }}
        >
          {/* Empty state */}
          {messages.length === 0 && !voiceStatus && (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <div
                className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
                style={{ background: theme.sidebar, border: `1px solid ${theme.border}` }}
              >
                <svg className="w-7 h-7" fill="none" stroke={theme.textSecondary} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-sm" style={{ color: theme.textPrimary }}>Start the conversation.</p>
              <p className="text-xs mt-1" style={{ color: theme.textSecondary }}>This conversation stays between you and the Guidance Office.</p>
            </div>
          )}

          {/* Message list */}
          {messages.map((m, i) => {
            if (m.role === 'system') {
              return (
                <div key={i} className="flex justify-center">
                  <span
                    className="text-xs italic px-3 py-1 rounded-full"
                    style={{ color: theme.textSecondary, background: theme.sidebar, border: `1px solid ${theme.border}` }}
                  >
                    {m.text}
                  </span>
                </div>
              );
            }
            return (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} items-end gap-2`}>
                {(m.role === 'bot' || m.role === 'counselor') && (
                  <Avatar role={m.role} accent={theme.accent} />
                )}
                <MessageBubble
                  message={m}
                  theme={theme}
                  onFeedback={m.role === 'bot' ? (v) => rateMessage(i, v) : undefined}
                  feedback={messageRatings[i]}
                />
              </div>
            );
          })}

          {/* Counselor typing */}
          {counselorTyping && (
            <div className="flex justify-start items-end gap-2">
              <Avatar role="counselor" accent={theme.accent} />
              <div
                className="px-4 py-3"
                style={{ background: '#0e2a45', border: '1px solid #1a4a6e', borderRadius: '4px 16px 16px 16px' }}
              >
                <TypingBubble color="#7eb8d9" />
              </div>
            </div>
          )}

          {/* Bot typing */}
          {sending && !counselorActive && !streamingStarted && (
            <div className="flex justify-start items-end gap-2">
              <Avatar role="bot" accent={theme.accent} />
              <div
                className="px-4 py-3"
                style={{ background: theme.botBubble, border: `1px solid ${theme.border}`, borderRadius: '4px 16px 16px 16px' }}
              >
                <TypingBubble color={theme.accent} />
              </div>
            </div>
          )}

          {/* Voice status */}
          {voiceStatus && (
            <div className="flex justify-center">
              <span
                className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full"
                style={{ color: theme.textSecondary, background: theme.sidebar, border: `1px solid ${theme.border}` }}
              >
                <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: theme.accent }} />
                {voiceStatus}
              </span>
            </div>
          )}
        </div>

        {/* Input */}
        <div
          className="px-3 sm:px-4 py-3 flex-shrink-0"
          style={{ background: theme.sidebar, borderTop: `1px solid ${theme.border}` }}
        >
          <div
            className="flex items-end gap-2 rounded-2xl px-3 py-2"
            style={{ background: theme.bg, border: `1px solid ${theme.border}` }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              rows={1}
              className="flex-1 resize-none py-1 text-sm leading-relaxed focus:outline-none"
              style={{ minHeight: '32px', maxHeight: '96px', background: 'transparent', color: theme.textPrimary }}
            />
            <div className="flex items-center gap-1.5 flex-shrink-0 pb-0.5">
              <VoiceInput
                sessionId={localStorage.getItem('session_id')}
                onTranscript={(text) => { setInput(text); sendMessage(text); }}
                onStatusChange={setVoiceStatus}
              />
              <button
                onClick={sendMessage}
                disabled={sending || !input.trim()}
                className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl flex items-center justify-center transition-all duration-200 flex-shrink-0"
                style={
                  input.trim()
                    ? { background: theme.userBubble, color: theme.userText }
                    : { background: theme.sidebar, color: theme.border, cursor: 'not-allowed' }
                }
                onMouseEnter={e => { if (input.trim()) e.currentTarget.style.background = theme.accent; }}
                onMouseLeave={e => { if (input.trim()) e.currentTarget.style.background = theme.userBubble; }}
              >
                {sending ? (
                  <div
                    className="w-3.5 h-3.5 border-2 rounded-full animate-spin"
                    style={{ borderColor: theme.textSecondary, borderTopColor: theme.accent }}
                  />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </div>
          </div>
          <p className="text-xs text-center mt-1.5 hidden sm:block" style={{ color: theme.textMuted }}>
            Press Enter to send. Shift+Enter for new line.
          </p>
        </div>
      </div>

      {/* ── Post-Session Wellbeing Rating Modal ───────────────── */}
      {showRating && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.75)' }}
        >
          <div
            className="w-full max-w-sm mx-4 rounded-2xl p-6 flex flex-col items-center gap-5"
            style={{ background: theme.sidebar, border: `1px solid ${theme.border}` }}
          >
            {ratingSubmitted ? (
              /* ── Thank you state ── */
              <div className="flex flex-col items-center gap-3 py-2">
                <div className="text-4xl">🙏</div>
                <p className="text-sm font-bold text-center" style={{ color: theme.textPrimary }}>
                  Thank you for sharing.
                </p>
                <p className="text-xs text-center" style={{ color: theme.textSecondary }}>
                  Take care of yourself.
                </p>
              </div>
            ) : (
              /* ── Rating state ── */
              <>
                <div className="text-center">
                  <p className="text-sm font-bold mb-1" style={{ color: theme.textPrimary }}>
                    Before you go
                  </p>
                  <p className="text-xs leading-relaxed" style={{ color: theme.textSecondary }}>
                    How are you feeling right now compared to when we started?
                  </p>
                </div>

                <div className="flex gap-3 w-full justify-center">
                  {WELLBEING_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => handleWellbeingRating(opt.value)}
                      onMouseEnter={() => setHoveredRating(opt.value)}
                      onMouseLeave={() => setHoveredRating(null)}
                      className="flex flex-col items-center gap-1.5 p-2 rounded-xl transition-all duration-150 flex-1"
                      style={{
                        background: hoveredRating === opt.value ? theme.border : 'transparent',
                        border: `1px solid ${hoveredRating === opt.value ? theme.accent : theme.border}`,
                        transform: hoveredRating === opt.value ? 'translateY(-2px)' : 'none',
                      }}
                    >
                      <span className="text-2xl">{opt.emoji}</span>
                      <span className="text-xs text-center leading-tight" style={{ color: theme.textSecondary }}>
                        {opt.label}
                      </span>
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => handleWellbeingRating(0)}
                  className="text-xs transition-colors"
                  style={{ color: theme.textMuted }}
                  onMouseEnter={e => e.currentTarget.style.color = theme.textSecondary}
                  onMouseLeave={e => e.currentTarget.style.color = theme.textMuted}
                >
                  Skip
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}