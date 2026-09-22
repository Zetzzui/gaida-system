import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, ReferenceLine
} from 'recharts';

import { BACKEND_URL as BACKEND } from '../../config';
import apiFetch from '../../api';

// ── Quick response templates ──────────────────────────────────────────────────
const QUICK_RESPONSES = [
  { label: "I'm here", text: "I'm here with you. You're not alone in this." },
  { label: "Take a breath", text: "Let's take a slow breath together. Inhale for 4 counts, hold for 4, exhale for 4. I'm right here with you." },
  { label: "Help coming", text: "I'm a counselor and I'm here to help you. You reached out at the right time. Can you tell me more about what you're feeling right now?" },
  { label: "Call hotline", text: "Please call the National Crisis Hotline at 1553 right now - they are available 24/7 and can help you immediately. I'm staying with you." },
  { label: "Safe?", text: "I want to make sure you're safe right now. Are you in a safe place? Is there anyone with you?" },
  { label: "Follow up", text: "I'd like to schedule a follow-up session with you. You've shown a lot of courage today by reaching out." },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
const severityColor = (s) => {
  if (s === 'High' || s === 'Crisis') return { bg: 'bg-red-600', text: 'text-white', dot: 'bg-red-500', border: 'border-red-200', light: 'bg-red-50', hex: '#ef4444' };
  if (s === 'Requested') return { bg: 'bg-blue-600', text: 'text-white', dot: 'bg-blue-500', border: 'border-blue-200', light: 'bg-blue-50', hex: '#3b82f6' };
  if (s === 'Moderate') return { bg: 'bg-amber-500', text: 'text-white', dot: 'bg-amber-400', border: 'border-amber-200', light: 'bg-amber-50', hex: '#f59e0b' };
  if (s === 'Low') return { bg: 'bg-green-500', text: 'text-white', dot: 'bg-green-400', border: 'border-green-200', light: 'bg-green-50', hex: '#22c55e' };
  return { bg: 'bg-gray-400', text: 'text-white', dot: 'bg-gray-400', border: 'border-gray-200', light: 'bg-gray-50', hex: '#9ca3af' };
};

const formatRelative = (ts) => {
  if (!ts) return '';
  const diff = Math.floor((Date.now() - new Date(ts)) / 60000);
  if (diff < 1) return 'just now';
  if (diff < 60) return `${diff}m ago`;
  return `${Math.floor(diff / 60)}h ago`;
};

const formatDuration = (startedAt) => {
  if (!startedAt) return '—';
  const diff = Math.floor((Date.now() - new Date(startedAt)) / 1000);
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
  const s = (diff % 60).toString().padStart(2, '0');
  return h > 0 ? `${h}:${m}:${s}` : `${m}:${s}`;
};

const confidenceToSeverity = (c) => {
  if (c >= 0.99) return 'Crisis';
  if (c >= 0.75) return 'High';
  if (c >= 0.60) return 'Moderate';
  if (c >= 0.45) return 'Low';
  return 'Normal';
};

// ── Alert sound ───────────────────────────────────────────────────────────────
// Reuse a single AudioContext instead of constructing one per call — the old
// code spawned a new context on every beep, which browsers eventually gag on
// (and some throw "too many AudioContexts").
let _alertAudioCtx = null;
const playAlertSound = () => {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!_alertAudioCtx) _alertAudioCtx = new Ctx();
    const ctx = _alertAudioCtx;
    if (ctx.state === 'suspended') ctx.resume();
    [0, 150, 300].forEach((delay) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      osc.type = 'sine';
      gain.gain.setValueAtTime(0.3, ctx.currentTime + delay / 1000);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay / 1000 + 0.3);
      osc.start(ctx.currentTime + delay / 1000);
      osc.stop(ctx.currentTime + delay / 1000 + 0.3);
    });
  } catch (e) {}
};

// Which counselor is signed in (matches what /takeover uses).
const getCounselorId = () => {
  try {
    const d = JSON.parse(localStorage.getItem('counselorData') || '{}');
    return d.id || d.student_number || null;
  } catch {
    return null;
  }
};

// Authenticated PDF export fallback for the Resolved Cases page — a bare
// window.open() can't carry the Bearer token, so it always got a 401.
const downloadSessionPdf = async (sessionId) => {
  try {
    const res = await apiFetch(`${BACKEND}/api/counselor/export-session/${sessionId}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Export failed');
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `GAIDA_Session_${sessionId.slice(0, 8)}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    return true;
  } catch (e) {
    alert(e.message || 'Could not export PDF.');
    return false;
  }
};

const NAV = [
  { id: 'overview',  label: 'Overview',         icon: '⊞' },
  { id: 'alerts',    label: 'Alerts',            icon: '⚠' },
  { id: 'welfare',   label: 'Welfare Checks',    icon: '☎' },
  { id: 'sessions',  label: 'Active Sessions',   icon: '◉' },
  { id: 'detection', label: 'Anxiety Detection', icon: '〜' },
  { id: 'reports',   label: 'Reports',           icon: '≡' },
  { id: 'resolved',  label: 'Resolved Cases',    icon: '✓' },
];

// ── Overview Page ─────────────────────────────────────────────────────────────
function OverviewPage({ alerts, sessions }) {
  const [analytics, setAnalytics] = useState(null);
  const [analyticsError, setAnalyticsError] = useState('');

  useEffect(() => {
    apiFetch(`${BACKEND}/api/counselor/analytics/overview`)
      .then(r => r.json())
      .then(data => {
        if (data && data.error) {
          setAnalyticsError(String(data.error));
        } else {
          setAnalytics(data);
        }
      })
      .catch(() => setAnalyticsError('Analytics are unavailable right now.'));
  }, []);

  const pending = alerts.filter(a => a.status === 'pending').length;
  const highSessions = sessions.filter(s => s.severity === 'High' || s.severity === 'Crisis').length;

  const DISTRIBUTION_COLORS = {
    Low: '#22c55e',
    Moderate: '#f59e0b',
    High: '#ef4444',
    Normal: '#9ca3af',
    Crisis: '#b91c1c',
  };

  const distributionData = analytics?.anxiety_distribution?.map(d => ({
    ...d,
    color: DISTRIBUTION_COLORS[d.name] || '#9ca3af',
  })) || [
    { name: 'Low', value: 0, color: '#22c55e' },
    { name: 'Moderate', value: 0, color: '#f59e0b' },
    { name: 'High', value: 0, color: '#ef4444' },
    { name: 'Normal', value: 0, color: '#9ca3af' },
    { name: 'Crisis', value: 0, color: '#b91c1c' },
  ];

  const weekData = analytics?.sessions_this_week || [
    { day: 'Mon', count: 0 }, { day: 'Tue', count: 0 },
    { day: 'Wed', count: 0 }, { day: 'Thu', count: 0 }, { day: 'Fri', count: 0 },
    { day: 'Sat', count: 0 }, { day: 'Sun', count: 0 },
  ];

  const trendData = analytics?.monthly_trends || [];
  const hasTrendData = trendData.some(m =>
    (m.normal || 0) + (m.low || 0) + (m.moderate || 0) + (m.high || 0) + (m.crisis || 0) > 0
  );
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Counselor Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">University of the East - Guidance System Overview</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Active Sessions', value: sessions.length, sub: 'right now', color: 'bg-red-600' },
          { label: 'Pending Alerts', value: pending, sub: 'need attention', color: pending > 0 ? 'bg-red-600' : 'bg-gray-700' },
          { label: 'High Anxiety', value: highSessions, sub: 'active sessions', color: 'bg-gray-900' },
          { label: 'Total Alerts', value: analytics?.total_alerts ?? alerts.length, sub: 'all time', color: 'bg-gray-900' },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-5 flex items-center justify-between shadow-sm">
            <div>
              <p className="text-xs text-gray-500 mb-1">{s.label}</p>
              <p className="text-2xl font-bold text-gray-900">{s.value}</p>
              <p className="text-xs text-gray-400 mt-0.5">{s.sub}</p>
            </div>
            <div className={`w-11 h-11 ${s.color} rounded-xl flex items-center justify-center flex-shrink-0`}>
              <span className="text-white text-lg font-bold">{s.value}</span>
            </div>
          </div>
        ))}
      </div>
      {analyticsError && (
        <div className="mb-5 p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
          Could not load analytics: {analyticsError}
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 mb-5">
        <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Anxiety Level Trends</h3>
          {!analytics ? (
            <p className="text-xs text-gray-400 text-center py-8">Loading trends...</p>
          ) : !hasTrendData ? (
            <p className="text-xs text-gray-400 text-center py-8">No trend data yet — appears once students have sessions</p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="normal" stroke="#9ca3af" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="low" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="moderate" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="high" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="crisis" stroke="#b91c1c" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-3 mt-3">
                {[
                  { label: 'Normal',  color: '#9ca3af' },
                  { label: 'Low',     color: '#22c55e' },
                  { label: 'Moderate', color: '#f59e0b' },
                  { label: 'High',    color: '#ef4444' },
                  { label: 'Crisis',  color: '#b91c1c' },
                ].map(l => (
                  <div key={l.label} className="flex items-center gap-1">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: l.color }} />
                    <span className="text-xs text-gray-500">{l.label}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Sessions This Week</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weekData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#dc2626" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Anxiety Distribution</h3>
          <div className="flex flex-col sm:flex-row items-center gap-4">
            <ResponsiveContainer width={160} height={160}>
              <PieChart>
                <Pie data={distributionData} cx="50%" cy="50%" innerRadius={45} outerRadius={70} dataKey="value">
                  {distributionData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2">
              {distributionData.map((d) => (
                <div key={d.name} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: d.color }} />
                  <span className="text-xs text-gray-600">{d.name}</span>
                  <span className="text-xs font-semibold text-gray-900 ml-auto pl-4">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Recent Alerts</h3>
          {alerts.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No alerts yet</p>
          ) : (
            <div className="space-y-3">
              {alerts.slice(0, 5).map((a, i) => {
                const sc = severityColor(a.severity);
                return (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${sc.dot}`} />
                      <div>
                        <p className="text-xs font-semibold text-gray-900">{a.session_id.slice(0, 8)}...</p>
                        <p className="text-xs text-gray-400">{a.severity} - {a.intent}</p>
                      </div>
                    </div>
                    <span className="text-xs text-gray-400">{formatRelative(a.timestamp)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Escalation helpers ────────────────────────────────────────────────────────
// Prefers the server-computed escalation state (which also drives re-notification
// emails); falls back to a client-side calculation for older payloads.
const getEscalationState = (a) => {
  if (a.escalation_level) {
    return { level: a.escalation_level, ageMinutes: a.age_minutes ?? 0, isOffHours: !!a.is_off_hours };
  }
  // Server not stamped yet (fresh alert, up to the monitor's next tick) —
  // approximate from the age anchor. first_alerted_at is the frozen creation
  // time; timestamp is refreshed on every student message.
  const timestamp = a.first_alerted_at || a.timestamp;
  const now = Date.now();
  const alertTime = new Date(timestamp).getTime();
  const ageMinutes = Math.floor((now - alertTime) / 60000);

  const hour = new Date().getHours();
  const day = new Date().getDay();
  const isOffHours = hour < 8 || hour >= 17 || day === 0 || day === 6;

  const warnThreshold    = isOffHours ? 5  : 10;
  const urgentThreshold  = isOffHours ? 15 : 30;
  const overdueThreshold = isOffHours ? 45 : 60;

  if (ageMinutes >= overdueThreshold) return { level: 'overdue',  ageMinutes, isOffHours };
  if (ageMinutes >= urgentThreshold)  return { level: 'urgent',   ageMinutes, isOffHours };
  if (ageMinutes >= warnThreshold)    return { level: 'warning',  ageMinutes, isOffHours };
  return { level: 'normal', ageMinutes, isOffHours };
};


// ── Alert Row ─────────────────────────────────────────────────────────────────
// Defined at module scope (not inside AlertsPage) so the 2-second polling
// re-render doesn't remount every row and drop mid-click button presses.
function AlertRow({ a, onViewChat, onUpdateStatus, onAcknowledge }) {
  const sc  = severityColor(a.severity);
  const esc = getEscalationState(a);
  const needsAck = a.severity === 'High' || a.severity === 'Crisis';
  // An escalated alert is one a counselor took over — it still needs the
  // same Acknowledge → Mark Reviewed flow, otherwise it deadlocks forever
  // (previous code only showed the buttons for status === 'pending').
  const actionable = a.status === 'pending' || a.status === 'escalated';

  const borderColor =
    esc.level === 'overdue' ? 'border-red-700' :
    esc.level === 'urgent'  ? 'border-red-500' :
    esc.level === 'warning' ? 'border-amber-400' :
    a.severity === 'High' || a.severity === 'Crisis' ? 'border-red-500' :
    a.severity === 'Requested' ? 'border-blue-500' :
    'border-amber-400';

  const bgColor =
    esc.level === 'overdue' ? 'bg-red-100' :
    esc.level === 'urgent'  ? 'bg-red-50' :
    esc.level === 'warning' ? 'bg-amber-50' :
    a.severity === 'High' || a.severity === 'Crisis' ? 'bg-red-50' :
    a.severity === 'Requested' ? 'bg-blue-50' :
    'bg-amber-50';

  return (
    <div className={`p-4 border-l-4 ${borderColor} ${bgColor} rounded-r-xl mb-3 ${
      esc.level === 'urgent' ? 'ring-1 ring-red-300 ring-offset-1' : ''
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.bg} ${sc.text}`}>{a.severity}</span>
            <span className="text-xs text-gray-500">{a.intent}</span>
            <span className="text-xs text-gray-400">{formatRelative(a.timestamp)}</span>

            {/* Escalation badge */}
            {esc.level === 'overdue' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-red-700 text-white animate-pulse">
                🚨 OVERDUE {esc.ageMinutes}m
              </span>
            )}
            {esc.level === 'urgent' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-red-600 text-white animate-pulse">
                ⚠ Unattended {esc.ageMinutes}m
              </span>
            )}
            {esc.level === 'warning' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-amber-500 text-white">
                Waiting {esc.ageMinutes}m+
              </span>
            )}

            {/* Needs-supervisor badge (alert passed the overdue deadline) */}
            {a.needs_supervisor && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-gray-900 text-white">
                Needs supervisor
              </span>
            )}

            {/* Off-hours tag */}
            {esc.isOffHours && (
              <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-700 text-gray-200">
                Off-hours
              </span>
            )}
          </div>
          <p className="text-xs font-semibold text-gray-700 mb-1">Session: {a.session_id.slice(0, 16)}...</p>
          <p className="text-xs text-gray-600 truncate">"{a.message}"</p>
          {a.acknowledged && (
            <p className="text-xs text-green-700 mt-1">
              ✓ Acknowledged{a.acknowledged_at ? ` ${formatRelative(a.acknowledged_at)}` : ''}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2 flex-shrink-0">
          <button onClick={() => onViewChat(a.session_id)} className="text-xs px-3 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-700 font-medium">View Chat</button>
          {actionable && needsAck && !a.acknowledged && (
            <button onClick={() => onAcknowledge(a.session_id)} className="text-xs px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 font-semibold">Acknowledge</button>
          )}
          {actionable && (!needsAck || a.acknowledged) && (
            <button onClick={() => onUpdateStatus(a.session_id, 'reviewed')} className="text-xs px-3 py-1.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-white font-medium">Mark Reviewed</button>
          )}
        </div>
      </div>

      {/* Urgent warning bar */}
      {(esc.level === 'urgent' || esc.level === 'overdue') && (
        <div className="mt-3 pt-3 border-t border-red-200 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
          <p className="text-xs text-red-700 font-medium">
            This alert has been waiting {esc.ageMinutes} minutes without a response.
            {esc.isOffHours && ' Session occurred outside office hours.'}
          </p>
        </div>
      )}

      {/* Overdue → supervisor notice (server also re-notifies by email) */}
      {esc.level === 'overdue' && (
        <div className="mt-2 pt-2 border-t border-red-300 flex items-start gap-2">
          <div className="w-2 h-2 rounded-full bg-red-700 animate-pulse flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-800 font-semibold">
            Past the escalation deadline — supervisor/backup has been notified by email. Acknowledge this alert immediately.
          </p>
        </div>
      )}
    </div>
  );
}

function AlertsPage({ alerts, onViewChat, onUpdateStatus, onAcknowledge }) {
  // Tick every 30 seconds so escalation badges update without a poll.
  const [, setNow] = useState(Date.now());
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(interval);
  }, []);

  // Three honest states instead of "everything that isn't pending is
  // resolved": pending (needs attention), escalated (a counselor took over
  // the conversation) and reviewed/resolved.
  const pending   = alerts.filter(a => a.status === 'pending');
  const escalated = alerts.filter(a => a.status === 'escalated');
  const resolved  = alerts.filter(a => a.status !== 'pending' && a.status !== 'escalated');

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Alerts</h1>
        <p className="text-sm text-gray-500 mt-0.5">High and Crisis level sessions requiring attention</p>
      </div>
      {pending.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <h3 className="text-sm font-semibold text-gray-900">Pending ({pending.length})</h3>
          </div>
          {pending.map((a) => <AlertRow key={a.session_id} a={a} onViewChat={onViewChat} onUpdateStatus={onUpdateStatus} onAcknowledge={onAcknowledge} />)}
        </div>
      )}
      {escalated.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-blue-500" />
            <h3 className="text-sm font-semibold text-gray-900">In Progress — Counselor Engaged ({escalated.length})</h3>
          </div>
          {escalated.map((a) => <AlertRow key={a.session_id} a={a} onViewChat={onViewChat} onUpdateStatus={onUpdateStatus} onAcknowledge={onAcknowledge} />)}
        </div>
      )}
      {resolved.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-500 mb-3">Reviewed / Resolved ({resolved.length})</h3>
          {resolved.map((a) => <AlertRow key={a.session_id} a={a} onViewChat={onViewChat} onUpdateStatus={onUpdateStatus} onAcknowledge={onAcknowledge} />)}
        </div>
      )}
      {alerts.length === 0 && (
        <div className="text-center py-20 text-gray-400">
          <p className="text-4xl mb-3">✓</p>
          <p className="text-sm font-medium">No alerts</p>
          <p className="text-xs mt-1">High and Crisis sessions will appear here</p>
        </div>
      )}
    </div>
  );
}

// ── Welfare Checks Page ───────────────────────────────────────────────────────
// Surfaces High/Crisis sessions that went silent (see
// get_sessions_needing_welfare_check in session_manager.py) — a student who
// hit a severe reading and then stopped responding, rather than one who
// calmly ended the session. Backend logic already existed; this page is
// what actually makes it visible to a counselor.
function WelfarePage({ welfare, onViewChat, onMarkChecked }) {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Welfare Checks</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          High/Crisis sessions that went silent with no follow-up — worth a human check-in
        </p>
      </div>
      {welfare.length > 0 ? (
        welfare.map((w) => {
          const sc = severityColor(w.peak_severity);
          return (
            <div key={w.session_id} className="p-4 border-l-4 border-red-500 bg-red-50 rounded-r-xl mb-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.bg} ${sc.text}`}>
                      Peak: {w.peak_severity}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-700 text-gray-200">
                      Silent {w.idle_minutes}m
                    </span>
                  </div>
                  <p className="text-xs font-semibold text-gray-700 mb-1">Session: {w.session_id.slice(0, 16)}...</p>
                  {w.last_message && <p className="text-xs text-gray-600 truncate">Last message: "{w.last_message}"</p>}
                </div>
                <div className="flex flex-col gap-2 flex-shrink-0">
                  <button onClick={() => onViewChat(w.session_id)} className="text-xs px-3 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-700 font-medium">View Chat</button>
                  <button onClick={() => onMarkChecked(w.session_id)} className="text-xs px-3 py-1.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-white font-medium">Mark Checked</button>
                </div>
              </div>
            </div>
          );
        })
      ) : (
        <div className="text-center py-20 text-gray-400">
          <p className="text-4xl mb-3">☎</p>
          <p className="text-sm font-medium">No welfare checks needed</p>
          <p className="text-xs mt-1">Silent High/Crisis sessions will appear here</p>
        </div>
      )}
    </div>
  );
}

// ── Active Sessions Page ──────────────────────────────────────────────────────
function SessionsPage({ sessions, onViewChat, lastUpdated }) {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Active Sessions</h1>
        <p className="text-sm text-gray-500 mt-0.5">Severity levels visible - chat content only shown for flagged sessions</p>
      </div>
      {sessions.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-4xl mb-3">◉</p>
          <p className="text-sm font-medium">No active sessions</p>
          <p className="text-xs mt-1">Sessions appear here when students are chatting</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-900">Sessions ({sessions.length})</span>
            <span className="text-xs text-gray-400">
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Auto-refreshing...'}
            </span>
          </div>
          <div className="divide-y divide-gray-50">
            {sessions.map((s) => {
              const sc = severityColor(s.severity);
              return (
                <div key={s.session_id} className="px-5 py-4 flex items-center gap-4">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${sc.dot} ${s.active ? 'animate-pulse' : ''}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-sm font-semibold text-gray-900">{s.session_id.slice(0, 16)}...</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.bg} ${sc.text}`}>{s.severity}</span>
                      {s.has_alert && <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-700">⚠ Alert</span>}
                      {s.assigned_counselor_id && <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-blue-100 text-blue-700">Assigned</span>}
                    </div>
                    <p className="text-xs text-gray-500">{s.message_count} messages • {formatDuration(s.started_at)} • intent: {s.intent}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="text-right mr-2">
                      <p className="text-xs text-gray-400">Confidence</p>
                      <p className="text-sm font-bold text-gray-900">{(s.confidence * 100).toFixed(0)}%</p>
                    </div>
                    {(s.severity === 'High' || s.severity === 'Crisis' || s.has_alert) && (
                      <button onClick={() => onViewChat(s.session_id)} className="text-xs px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium">View Chat</button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Chat Modal ────────────────────────────────────────────────────────────────
function ChatModal({ sessionId, onClose }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [takeoverMsg, setTakeoverMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [tookOver, setTookOver] = useState(false);
  const [activeTab, setActiveTab] = useState('chat');
  const [studentTyping, setStudentTyping] = useState(false);
  const [returningToGaida, setReturningToGaida] = useState(false);
  const bottomRef = useRef(null);
  const typingTimeoutRef = useRef(null);
  const [resolving, setResolving] = useState(false);
  const [resolved, setResolved] = useState(false);
  const [studentProfile, setStudentProfile] = useState(null);
  const [exporting, setExporting] = useState(false);

  // ── Case Notes state ──────────────────────────────────────────────────────
  const [noteText, setNoteText] = useState('');
  const [noteOutcome, setNoteOutcome] = useState('');
  const [savedNote, setSavedNote] = useState(null);
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState('');
  // Visible failure feedback for takeover/return-to-GAIDA (previously these
  // errors were only logged to the console or shown on the wrong tab).
  const [actionError, setActionError] = useState('');

  const OUTCOMES = [
    { value: 'resolved',          label: 'Resolved',           desc: 'Handled, no further action needed' },
    { value: 'false_alarm',       label: 'False alarm',        desc: 'Flagged by system but not concerning' },
    { value: 'referred',          label: 'Referred',           desc: 'Escalated to in-person guidance office' },
    { value: 'follow_up',         label: 'Follow-up scheduled',desc: 'Counselor will check in again' },
    { value: 'ongoing',           label: 'Ongoing',            desc: 'Still being monitored' },
  ];

  const OUTCOME_COLORS = {
    resolved:    { dot: 'bg-green-500',  badge: 'bg-green-100 text-green-800' },
    false_alarm: { dot: 'bg-gray-400',   badge: 'bg-gray-100 text-gray-700' },
    referred:    { dot: 'bg-blue-500',   badge: 'bg-blue-100 text-blue-800' },
    follow_up:   { dot: 'bg-amber-500',  badge: 'bg-amber-100 text-amber-800' },
    ongoing:     { dot: 'bg-red-500',    badge: 'bg-red-100 text-red-800' },
  };


  useEffect(() => {
    // get user_id from the session first, then fetch profile
    apiFetch(`${BACKEND}/api/counselor/chat/${sessionId}`)
      .then(r => r.json())
      .then(data => {
        const userId = data.user_id;
        if (userId) {
          return apiFetch(`${BACKEND}/api/counselor/student-profile/${userId}`)
            .then(r => r.json())
            .then(d => setStudentProfile(d.profile));
        }
      })
      .catch(() => {});
  }, [sessionId]);

  
  useEffect(() => {
    fetchChat();
    const interval = setInterval(fetchChat, 3000);
    return () => clearInterval(interval);
  }, [sessionId]);

  // Load existing note when modal opens
  useEffect(() => {
    apiFetch(`${BACKEND}/api/counselor/session-notes/${sessionId}`)
      .then(r => r.json())
      .then(data => {
        if (data.notes && data.notes.length > 0) {
          const latest = data.notes[0]; // already ordered desc
          setSavedNote(latest);
          setNoteText(latest.note || '');
          setNoteOutcome(latest.outcome || '');
        }
      })
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    if (activeTab === 'chat') {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeTab, studentTyping]);

  const fetchChat = async () => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/chat/${sessionId}`);
      const data = await res.json();
      if (data.messages) setMessages(data.messages);
      setStudentTyping(data.student_typing || false);

      // Keep the "you have joined" state truthful across modal re-opens:
      // taken over = a counselor (ideally this one) is actively chatting.
      if (typeof data.counselor_active === 'boolean') {
        const myId = getCounselorId();
        const mine = !data.assigned_counselor_id || data.assigned_counselor_id === myId;
        setTookOver(data.counselor_active && mine);
      }
    } catch (e) {} finally {
      setLoading(false);
    }
  };

  const fireCounselorTyping = (isTyping) => {
    apiFetch(`${BACKEND}/api/counselor/typing/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender: 'counselor', is_typing: isTyping }),
    }).catch(() => {});
  };

  // Add this ref at the top of ChatModal
const typingThrottleRef = useRef(null);

  const handleInputChange = (e) => {
    setTakeoverMsg(e.target.value);
    if (actionError) setActionError('');

    // Only fire typing signal if not already throttled
    if (!typingThrottleRef.current) {
      fireCounselorTyping(true);
      typingThrottleRef.current = setTimeout(() => {
        typingThrottleRef.current = null;
      }, 2000); // fire at most once every 2 seconds
    }

    // Reset the "stop typing" timer
    clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => {
      fireCounselorTyping(false);
      typingThrottleRef.current = null;
    }, 2000);
  };

  const sendTakeover = async (msg) => {
    const text = msg || takeoverMsg;
    if (!text.trim()) return;
    clearTimeout(typingTimeoutRef.current);
    fireCounselorTyping(false);
    setSending(true);
    setActionError('');
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/takeover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text, counselor_id: getCounselorId() }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        setTookOver(true);
        setTakeoverMsg('');
        fetchChat();
      } else if (data.error === 'already_assigned') {
        setActionError('Another counselor is already handling this session.');
      } else {
        setActionError(data.error || 'Could not send your message. Please try again.');
      }
    } catch (e) {
      setActionError('Connection error sending your message. Please try again.');
    } finally {
      setSending(false);
    }
  };

  const handleReturnToGaida = async () => {
    setReturningToGaida(true);
    setActionError('');
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/return-to-gaida`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, counselor_id: getCounselorId() }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        setTookOver(false);
        fetchChat();
      } else if (data.error === 'already_assigned') {
        setActionError('This session is being handled by another counselor — they need to return it to GAIDA first.');
      } else {
        setActionError(data.error || data.detail || 'Could not hand the session back to GAIDA.');
      }
    } catch (e) {
      setActionError('Connection error returning the session. Please try again.');
    } finally {
      setReturningToGaida(false);
    }
  };


  const handleSaveNote = async () => {
    if (!noteOutcome) { setNoteError('Please select an outcome.'); return; }
    setNoteError('');
    setSavingNote(true);
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/session-notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          note: noteText,
          outcome: noteOutcome,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        setSavedNote({ note: noteText, outcome: noteOutcome, updated_at: new Date().toISOString(), created_at: new Date().toISOString() });
      } else {
        setNoteError(data.error || 'Failed to save. Please try again.');
      }
    } catch (e) {
      setNoteError('Failed to save. Please try again.');
    } finally {
      setSavingNote(false);
    }
  };

  const severityHistory = messages
    .filter(m => m.sender === 'user' && m.confidence)
    .map((m, i) => ({
      msg: i + 1,
      confidence: Math.round((m.confidence || 0) * 100),
      severity: confidenceToSeverity(m.confidence || 0),
      text: m.text?.slice(0, 30) + (m.text?.length > 30 ? '...' : ''),
    }));

  const CustomDot = (props) => {
    const { cx, cy, payload } = props;
    const colors = { Crisis: '#b91c1c', High: '#ef4444', Moderate: '#f59e0b', Low: '#22c55e', Normal: '#9ca3af' };
    return <circle cx={cx} cy={cy} r={4} fill={colors[payload.severity] || '#9ca3af'} stroke="white" strokeWidth={1.5} />;
  };

  const TABS = [
    { id: 'chat',  label: 'Chat Transcript' },
    { id: 'graph', label: 'Anxiety Progression' },
    { id: 'notes', label: 'Case Notes' },
  ];
  
  const handleResolve = async () => {
    if (!window.confirm('Mark this session as resolved? It will be removed from active sessions.')) return;
    setResolving(true);
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/sessions/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json();
      if (data.ok) {
        setResolved(true);
        setTimeout(() => onClose(), 1500);
      } else if (!res.ok) {
        alert(data.detail || 'Could not resolve this session — it may need to be acknowledged first (Alerts tab).');
      }
    } catch (e) {} finally {
      setResolving(false);
    }
  };

  const handleExportSession = async () => {
    setExporting(true);
    try {
      await downloadSessionPdf(sessionId);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between flex-shrink-0">
          <div>
            {studentProfile ? (
              <>
                <p className="text-sm font-bold text-gray-900">{studentProfile.name}</p>
                <p className="text-xs text-gray-500">
                  {studentProfile.student_id}
                  {studentProfile.program && ` · ${studentProfile.program}`}
                  {studentProfile.year && `, Year ${studentProfile.year}`}
                </p>
              </>
            ) : (
              <>
                <h3 className="text-sm font-bold text-gray-900">Live Session</h3>
                <p className="text-xs text-gray-500">{sessionId.slice(0, 24)}...</p>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportSession}
              disabled={exporting}
              className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg border border-gray-200 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {exporting ? (
                '...'
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Export
                </>
              )}
            </button>
            {resolved ? (
              <span className="text-xs text-green-600 font-medium">✓ Session resolved</span>
            ) : (
              <button
                onClick={handleResolve}
                disabled={resolving || !savedNote}
                title={!savedNote ? 'Save a case note before resolving' : undefined}
                className="text-xs px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              >
                {resolving ? 'Resolving...' : 'Resolve session'}
              </button>
            )}
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-gray-400 mr-2">Live</span>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 text-sm font-bold">✕</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-100 flex-shrink-0">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex-1 py-2.5 text-xs font-medium transition-colors relative ${activeTab === t.id ? 'bg-gray-100 text-gray-900 border-b-2 border-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
            >
              {t.label}
              {t.id === 'notes' && savedNote && (
                <span className="absolute top-1.5 right-3 w-1.5 h-1.5 rounded-full bg-blue-500" />
              )}
            </button>
          ))}
        </div>

        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50 min-h-0">
            {loading ? (
              <p className="text-xs text-gray-400 text-center py-8">Loading chat...</p>
            ) : messages.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-8">No messages yet</p>
            ) : (
              messages
                .filter((m, i, arr) => {
                  if (i === 0) return true;
                  const prev = arr[i - 1];
                  return !(prev.sender === m.sender && prev.text === m.text);
                })
                .map((m, i) => (
                  <div key={i} className={`flex ${m.sender === 'student' || m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                      m.sender === 'student' || m.sender === 'user'
                        ? 'bg-gray-800 text-white rounded-tr-sm'
                        : m.sender === 'counselor'
                        ? 'bg-blue-600 text-white rounded-tl-sm'
                        : 'bg-white text-gray-800 border border-gray-200 rounded-tl-sm'
                    }`}>
                      {m.sender === 'counselor' && <p className="text-blue-200 text-xs font-semibold mb-1">You (Counselor)</p>}
                      {m.sender === 'bot' && <p className="text-gray-400 text-xs font-semibold mb-1">GAIDA</p>}
                      <p>{m.text}</p>
                      {(m.sender === 'user' || m.sender === 'student') && m.confidence && (
                        <div className="flex items-center gap-1 mt-1">
                          <div className={`w-1.5 h-1.5 rounded-full ${
                            confidenceToSeverity(m.confidence) === 'High' ? 'bg-red-400' :
                            confidenceToSeverity(m.confidence) === 'Moderate' ? 'bg-amber-400' :
                            confidenceToSeverity(m.confidence) === 'Low' ? 'bg-green-400' : 'bg-gray-400'
                          }`} />
                          <p className="text-gray-400 text-xs">{m.intent} • {(m.confidence * 100).toFixed(0)}% • {confidenceToSeverity(m.confidence)}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))
            )}
            {studentTyping && (
              <div className="flex justify-end">
                <div className="bg-gray-700 px-3 py-2 rounded-xl rounded-tr-sm">
                  <div className="flex gap-1 items-center h-4">
                    <div className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{animationDelay:'0ms'}}></div>
                    <div className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{animationDelay:'150ms'}}></div>
                    <div className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{animationDelay:'300ms'}}></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}

        {/* Severity Graph Tab */}
        {activeTab === 'graph' && (
          <div className="flex-1 overflow-y-auto p-4 min-h-0">
            <div className="mb-3">
              <p className="text-xs font-semibold text-gray-900 mb-1">Anxiety Confidence Over Session</p>
              <p className="text-xs text-gray-400">Each point = one student message. Color = detected severity.</p>
            </div>
            {severityHistory.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-8">No data yet - waiting for student messages</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={severityHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="msg" tick={{ fontSize: 10 }} label={{ value: 'Message #', position: 'insideBottom', offset: -2, fontSize: 10 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickFormatter={v => `${v}%`} />
                    <Tooltip
                      formatter={(val) => [`${val}%`, 'Confidence']}
                      labelFormatter={(label, payload) => payload?.[0]?.payload?.text || `Message ${label}`}
                    />
                    <ReferenceLine y={75} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'High', fill: '#ef4444', fontSize: 10 }} />
                    <ReferenceLine y={60} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: 'Moderate', fill: '#f59e0b', fontSize: 10 }} />
                    <ReferenceLine y={45} stroke="#22c55e" strokeDasharray="3 3" label={{ value: 'Low', fill: '#22c55e', fontSize: 10 }} />
                    <Line type="monotone" dataKey="confidence" stroke="#6b7280" strokeWidth={2} dot={<CustomDot />} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-3 mt-3">
                  {[
                    { label: 'Normal', color: '#9ca3af' },
                    { label: 'Low', color: '#22c55e' },
                    { label: 'Moderate', color: '#f59e0b' },
                    { label: 'High', color: '#ef4444' },
                    { label: 'Crisis', color: '#b91c1c' },
                  ].map(l => (
                    <div key={l.label} className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: l.color }} />
                      <span className="text-xs text-gray-500">{l.label}</span>
                    </div>
                  ))}
                </div>
                {severityHistory.length > 0 && (() => {
                  const last = severityHistory[severityHistory.length - 1];
                  const sc = severityColor(last.severity);
                  return (
                    <div className={`mt-3 p-3 rounded-lg ${sc.light} border ${sc.border}`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs font-semibold text-gray-900">Current Status</p>
                          <p className="text-xs text-gray-500">Based on latest message</p>
                        </div>
                        <div className="text-right">
                          <span className={`text-sm font-bold px-3 py-1 rounded-full ${sc.bg} ${sc.text}`}>{last.severity}</span>
                          <p className="text-xs text-gray-400 mt-1">{last.confidence}% confidence</p>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </>
            )}
          </div>
        )}

        {/* Case Notes Tab */}
        {activeTab === 'notes' && (
          <div className="flex-1 overflow-y-auto p-4 min-h-0">

            {/* Saved note banner */}
            {savedNote && (
              <div className="mb-4 p-3 bg-blue-50 border border-blue-100 rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-blue-500 text-xs">✓</span>
                  <span className="text-xs text-blue-700 font-medium">Note saved</span>
                  {(savedNote.updated_at || savedNote.created_at) && (
                    <span className="text-xs text-blue-400">{formatRelative(savedNote.updated_at || savedNote.created_at)}</span>
                  )}
                </div>
                {savedNote.outcome && (() => {
                  const oc = OUTCOME_COLORS[savedNote.outcome];
                  const outcomeLabel = OUTCOMES.find(o => o.value === savedNote.outcome)?.label;
                  return (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${oc?.badge}`}>
                      {outcomeLabel}
                    </span>
                  );
                })()}
              </div>
            )}

            {/* Outcome selector */}
            <div className="mb-4">
              <p className="text-xs font-semibold text-gray-900 mb-2">Outcome</p>
              <div className="space-y-2">
                {OUTCOMES.map(o => {
                  const oc = OUTCOME_COLORS[o.value];
                  const selected = noteOutcome === o.value;
                  return (
                    <button
                      key={o.value}
                      onClick={() => setNoteOutcome(o.value)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-colors ${
                        selected
                          ? 'border-gray-900 bg-gray-50'
                          : 'border-gray-100 hover:border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${oc.dot}`} />
                      <div className="flex-1 min-w-0">
                        <p className={`text-xs font-semibold ${selected ? 'text-gray-900' : 'text-gray-700'}`}>{o.label}</p>
                        <p className="text-xs text-gray-400">{o.desc}</p>
                      </div>
                      {selected && <span className="text-gray-900 text-xs flex-shrink-0">✓</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Notes textarea */}
            <div className="mb-4">
              <p className="text-xs font-semibold text-gray-900 mb-2">Notes</p>
              <textarea
                value={noteText}
                onChange={e => setNoteText(e.target.value)}
                placeholder="Document what happened, what was said, and any follow-up actions..."
                rows={5}
                className="w-full text-xs px-3 py-2 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 resize-none leading-relaxed text-gray-800 placeholder-gray-400"
              />
            </div>

            {noteError && (
              <p className="text-xs text-red-600 mb-3">{noteError}</p>
            )}

            <button
              onClick={handleSaveNote}
              disabled={savingNote}
              className="w-full py-2.5 bg-gray-900 text-white text-xs font-medium rounded-xl hover:bg-gray-700 disabled:opacity-50 transition-colors"
            >
              {savingNote ? 'Saving...' : savedNote ? 'Update note' : 'Save note'}
            </button>
          </div>
        )}

        {/* Quick Responses + Input — hidden on notes tab */}
        {activeTab !== 'notes' && (
          <div className="px-4 pt-3 border-t border-gray-100 flex-shrink-0">
            {actionError && (
              <p className="text-xs text-red-600 mb-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{actionError}</p>
            )}
            <p className="text-xs text-gray-400 mb-2">Quick responses:</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {QUICK_RESPONSES.map((r) => (
                <button
                  key={r.label}
                  onClick={() => sendTakeover(r.text)}
                  disabled={sending}
                  className="text-xs px-2.5 py-1 bg-gray-100 hover:bg-blue-100 hover:text-blue-700 text-gray-600 rounded-full border border-gray-200 hover:border-blue-300 transition-colors disabled:opacity-50"
                >
                  {r.label}
                </button>
              ))}
            </div>
            {tookOver && (
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-blue-600 font-medium">✓ You have joined this session</p>
                <button
                  onClick={handleReturnToGaida}
                  disabled={returningToGaida}
                  className="text-xs px-3 py-1 bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-full border border-gray-200 transition-colors disabled:opacity-50"
                >
                  {returningToGaida ? 'Returning...' : '← Return to GAIDA'}
                </button>
              </div>
            )}
            <div className="flex gap-2 pb-3">
              <input
                value={takeoverMsg}
                onChange={handleInputChange}
                onKeyDown={e => e.key === 'Enter' && sendTakeover()}
                placeholder="Type a message to the student..."
                className="flex-1 text-xs px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400"
              />
              <button
                onClick={() => sendTakeover()}
                disabled={sending || !takeoverMsg.trim()}
                className="px-4 py-2 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
              >
                {sending ? '...' : 'Send'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Detection Page ────────────────────────────────────────────────────────────
function DetectionPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Multimodal Anxiety Detection</h1>
        <p className="text-sm text-gray-500 mt-0.5">Real-time anxiety monitoring using voice and text analysis</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        {[
          { label: 'Voice Analysis', sub: 'Pitch, Energy, Jitter, Speech Rate, Pauses', status: 'Active', color: 'bg-gray-900' },
          { label: 'Text Analysis', sub: 'ML Ensemble: LR + RF + Neural Network', status: 'Active', color: 'bg-red-600' },
        ].map((m) => (
          <div key={m.label} className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <p className="text-xs text-gray-500">{m.label}</p>
            </div>
            <p className="text-xl font-bold text-gray-900 mb-1">{m.status}</p>
            <p className="text-xs text-gray-400">{m.sub}</p>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Anxiety Level Thresholds</h3>
        <div className="space-y-3">
          {[
            { level: 'Normal', range: '< 0.45', color: 'bg-gray-400', desc: 'GPT responds freely' },
            { level: 'Low', range: '0.45 – 0.60', color: 'bg-green-500', desc: 'Counselor protocol injected' },
            { level: 'Moderate', range: '0.60 – 0.75', color: 'bg-amber-500', desc: 'Stronger protocol injected' },
            { level: 'High', range: '0.75 – 0.98', color: 'bg-red-500', desc: 'Counselor alert fired' },
            { level: 'Crisis', range: '0.99', color: 'bg-red-700', desc: 'Immediate intervention' },
          ].map((t) => (
            <div key={t.level} className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full flex-shrink-0 ${t.color}`} />
              <span className="text-xs font-semibold text-gray-900 w-16">{t.level}</span>
              <span className="text-xs text-gray-400 w-24">{t.range}</span>
              <span className="text-xs text-gray-600">{t.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Reports Page ──────────────────────────────────────────────────────────────
function ReportsPage() {
  const [reports, setReports] = useState(null);
  const [reportsError, setReportsError] = useState('');

  useEffect(() => {
    apiFetch(`${BACKEND}/api/counselor/analytics/reports`)
      .then(r => r.json())
      .then(data => {
        if (data && data.error) {
          setReportsError(String(data.error));
        } else {
          setReports(data);
        }
      })
      .catch(() => setReportsError('Reports are unavailable right now.'));
  }, []);

  const trendData = reports?.monthly_reports || [];
  const hasTrendData = trendData.some(m => (m.sessions || 0) + (m.alerts || 0) > 0);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Reports & Analytics</h1>
        <p className="text-sm text-gray-500 mt-0.5">System performance and anxiety detection analytics</p>
      </div>
      {reportsError && (
        <div className="mb-5 p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
          Could not load reports: {reportsError}
        </div>
      )}
      <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm mb-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Monthly Trends</h3>
        {!reports ? (
          <p className="text-xs text-gray-400 text-center py-8">Loading trends...</p>
        ) : !hasTrendData ? (
          <p className="text-xs text-gray-400 text-center py-8">No report data yet — appears once students have sessions</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="sessions" stroke="#111827" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="alerts" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Severity Breakdown by Month</h3>
        {!reports ? (
          <p className="text-xs text-gray-400 text-center py-8">Loading breakdown...</p>
        ) : !hasTrendData ? (
          <p className="text-xs text-gray-400 text-center py-8">No breakdown data yet — appears once students have sessions</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2 pr-4 font-semibold text-gray-500">Month</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-500">Sessions</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-500">Alerts</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: '#9ca3af' }}>Normal</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: '#22c55e' }}>Low</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: '#f59e0b' }}>Moderate</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: '#ef4444' }}>High</th>
                  <th className="text-right py-2 pl-3 font-semibold" style={{ color: '#b91c1c' }}>Crisis</th>
                </tr>
              </thead>
              <tbody>
                {trendData.map((m, i) => (
                  <tr key={i} className={i < trendData.length - 1 ? 'border-b border-gray-50' : ''}>
                    <td className="py-2 pr-4 font-medium text-gray-900">{m.month}</td>
                    <td className="py-2 px-3 text-right text-gray-600">{m.sessions || 0}</td>
                    <td className="py-2 px-3 text-right text-gray-600">{m.alerts || 0}</td>
                    <td className="py-2 px-3 text-right text-gray-600">{m.normal || 0}</td>
                    <td className="py-2 px-3 text-right text-gray-600">{m.low || 0}</td>
                    <td className="py-2 px-3 text-right text-gray-600">{m.moderate || 0}</td>
                    <td className="py-2 px-3 text-right text-gray-600">{m.high || 0}</td>
                    <td className="py-2 pl-3 text-right font-semibold text-gray-900">{m.crisis || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function CounselorDashboard() {
  const navigate = useNavigate();

  // ── Auth guard ────────────────────────────────────────────────
  // Unlike StudentDashboard, this component previously had no check at
  // all — anyone could reach /counselor-dashboard directly by URL.
  useEffect(() => {
    const token = localStorage.getItem('counselor_token');
    if (!token) {
      navigate('/counselor-login');
    }
  }, [navigate]);
  const [activePage, setActivePage] = useState('overview');
  const [alerts, setAlerts] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [welfare, setWelfare] = useState([]);
  const [chatSessionId, setChatSessionId] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const prevPendingIdsRef = useRef(new Set());
  const alertsRef = useRef(alerts);
  alertsRef.current = alerts;
  const [lastUpdated, setLastUpdated] = useState(null);

  useEffect(() => {
    fetchAlerts();
    fetchSessions();
    fetchWelfare();
    const interval = setInterval(() => {
      fetchAlerts();
      fetchSessions();
      fetchWelfare();
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  const fetchAlerts = async () => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/alerts`);
      const data = await res.json();
      if (data.alerts) {
        // Detect NEW pending alerts by ID (count-based logic missed a replaced
        // alert with the same count, and re-beeped every poll because the
        // effect ran on every 2s fetch).
        const pendingNow = data.alerts.filter(a => a.status === 'pending');
        const pendingNowIds = pendingNow.map(a => a.session_id);
        const freshIds = pendingNowIds.filter(id => !prevPendingIdsRef.current.has(id));
        if (freshIds.length > 0) {
          playAlertSound();
          if (Notification.permission === 'granted') {
            new Notification('⚠ GAIDA Alert', {
              body: `${freshIds.length} new High/Crisis alert${freshIds.length > 1 ? 's' : ''} need attention`,
              icon: '/favicon.ico',
            });
          }
        }
        prevPendingIdsRef.current = new Set(pendingNowIds);
        setAlerts(data.alerts);
      }
    } catch (e) {}
  };

  // Every 5 minutes, re-remind with a sound while any pending alert is still
  // urgent or overdue (moved here from AlertsPage so it works on every tab and
  // doesn't double-beep with fetchAlerts above).
  useEffect(() => {
    const check = () => {
      const anyUrgent = alertsRef.current.some(a => {
        if (a.status !== 'pending') return false;
        const esc = getEscalationState(a);
        return esc.level === 'urgent' || esc.level === 'overdue';
      });
      if (anyUrgent) playAlertSound();
    };
    const interval = setInterval(check, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/sessions/active`);
      const data = await res.json();
      if (data.sessions) setSessions(data.sessions);
      setLastUpdated(new Date());
    } catch (e) {}
  };

  const handleUpdateStatus = async (sessionId, status) => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/alerts/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, status }),
      });
      const data = await res.json().catch(() => ({}));
      // The endpoint can return HTTP 200 with ok:false (e.g. not found, or a
      // High/Crisis alert that needs acknowledging first) — treat both the
      // same instead of silently doing nothing.
      if (!res.ok || data.ok === false) {
        alert(data.detail || data.error || 'This alert needs to be acknowledged first.');
        return;
      }
      fetchAlerts();
    } catch (e) {}
  };

  const handleAcknowledge = async (sessionId) => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/alerts/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        alert(data.detail || data.error || 'Could not acknowledge this alert.');
        return;
      }
      fetchAlerts();
    } catch (e) {}
  };

  const fetchWelfare = async () => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/sessions/welfare`);
      const data = await res.json();
      if (data.sessions) setWelfare(data.sessions);
    } catch (e) {}
  };

  const handleMarkWelfareChecked = async (sessionId) => {
    try {
      await apiFetch(`${BACKEND}/api/counselor/sessions/welfare-checked`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      setWelfare(prev => prev.filter(w => w.session_id !== sessionId));
    } catch (e) {}
  };

  const pendingCount = alerts.filter(a => a.status === 'pending').length;

  const logout = () => {
    localStorage.removeItem('counselor_token');
    localStorage.removeItem('counselorData');
    navigate('/counselor-login');
  };

  const counselor = JSON.parse(localStorage.getItem('counselorData') || '{}');
  const initials = counselor.name
    ? counselor.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'CR';

  return (
    <div className="min-h-screen bg-gray-50 flex overflow-hidden">
      {expanded && <div className="fixed inset-0 bg-black/20 z-20" onClick={() => setExpanded(false)} />}

      {/* Sidebar */}
      <aside className={`fixed top-0 left-0 h-full z-30 bg-gray-800 flex flex-col shadow-lg transition-all duration-300 ${expanded ? 'w-56' : 'w-14'}`}>
        <div className="h-14 flex items-center justify-center flex-shrink-0 border-b border-gray-700">
          <div className="w-8 h-8 bg-red-600 rounded-full flex items-center justify-center">
            <span className="text-white text-xs font-bold">{initials}</span>
          </div>
          {expanded && <span className="text-white font-bold text-sm tracking-wide ml-3 whitespace-nowrap">GAIDA</span>}
        </div>
        <nav className="flex-1 py-3 overflow-y-auto overflow-x-hidden">
          {NAV.map((navItem) => {
            const active = activePage === navItem.id;
            const isAlerts = navItem.id === 'alerts';
            const isWelfare = navItem.id === 'welfare';
            const badgeCount = isAlerts ? pendingCount : isWelfare ? welfare.length : 0;
            return (
              <button
                key={navItem.id}
                onClick={() => { setActivePage(navItem.id); setExpanded(false); }}
                title={!expanded ? navItem.label : undefined}
                className={`w-full flex items-center px-4 py-3 transition-colors relative group ${active ? 'bg-red-600 text-white' : 'text-gray-400 hover:bg-gray-700 hover:text-white'}`}
              >
                <span className="flex-shrink-0 text-base relative">
                  {navItem.icon}
                  {badgeCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full text-white flex items-center justify-center" style={{fontSize:'8px'}}>{badgeCount}</span>
                  )}
                </span>
                {expanded && <span className="ml-3 text-sm font-medium whitespace-nowrap">{navItem.label}</span>}
                {!expanded && (
                  <span className="absolute left-14 bg-gray-900 text-white text-xs px-2 py-1 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-lg">
                    {navItem.label}{badgeCount > 0 && ` (${badgeCount})`}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="border-t border-gray-700 flex-shrink-0">
          <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center px-4 py-3 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors">
            <span className={`flex-shrink-0 text-sm transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`}>›</span>
            {expanded && <span className="ml-3 text-sm font-medium">Collapse</span>}
          </button>
          <button onClick={logout} className="w-full flex items-center px-4 py-3 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors" title={!expanded ? 'Logout' : undefined}>
            <span className="flex-shrink-0 text-sm">⏻</span>
            {expanded && <span className="ml-3 text-sm font-medium">Logout</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden ml-14">
        <main className="flex-1 overflow-y-auto">
          <div className="w-full max-w-6xl mx-auto p-4 sm:p-6">
            {activePage === 'overview'  && <OverviewPage alerts={alerts} sessions={sessions} />}
            {activePage === 'alerts'    && <AlertsPage alerts={alerts} onViewChat={setChatSessionId} onUpdateStatus={handleUpdateStatus} onAcknowledge={handleAcknowledge} />}
            {activePage === 'welfare'   && <WelfarePage welfare={welfare} onViewChat={setChatSessionId} onMarkChecked={handleMarkWelfareChecked} />}
            {activePage === 'sessions' && <SessionsPage sessions={sessions} onViewChat={setChatSessionId} lastUpdated={lastUpdated} />}
            {activePage === 'detection' && <DetectionPage />}
            {activePage === 'reports'   && <ReportsPage />}
            {activePage === 'resolved'  && <ResolvedCasesPage />}
          </div>
        </main>
      </div>

      {chatSessionId && (
        <ChatModal sessionId={chatSessionId} onClose={() => setChatSessionId(null)} />
      )}
    </div>
  );
}

// ── Resolved Cases Page ───────────────────────────────────────────────────────
function ResolvedCasesPage() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [casesError, setCasesError] = useState('');

  const handleDelete = async (sessionId, e) => {
    e.stopPropagation();
    if (!window.confirm('Remove this case from the list? This can be undone from the database if needed.')) return;

    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/sessions/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json();
      if (data.ok) {
        setCases(prev => prev.filter(c => c.session_id !== sessionId));
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  const OUTCOME_COLORS = {
    resolved:    { badge: 'bg-green-100 text-green-800' },
    false_alarm: { badge: 'bg-gray-100 text-gray-700' },
    referred:    { badge: 'bg-blue-100 text-blue-800' },
    follow_up:   { badge: 'bg-amber-100 text-amber-800' },
    ongoing:     { badge: 'bg-red-100 text-red-800' },
  };

  const OUTCOME_LABELS = {
    resolved:    'Resolved',
    false_alarm: 'False alarm',
    referred:    'Referred',
    follow_up:   'Follow-up scheduled',
    ongoing:     'Ongoing',
  };

  useEffect(() => {
    apiFetch(`${BACKEND}/api/counselor/sessions/resolved`)
      .then(r => r.json())
      .then(data => {
        if (data && data.error) {
          setCasesError(String(data.error));
        } else if (data.sessions) {
          setCases(data.sessions);
        }
      })
      .catch(() => setCasesError('Resolved cases are unavailable right now.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Resolved Cases</h1>
        <p className="text-sm text-gray-500 mt-0.5">Closed sessions with case notes and transcripts</p>
      </div>

      {loading ? (
        <p className="text-xs text-gray-400 text-center py-20">Loading...</p>
      ) : casesError ? (
        <div className="text-center py-20 text-gray-500">
          <p className="text-sm font-medium">Could not load resolved cases.</p>
          <p className="text-xs mt-1">{casesError}</p>
        </div>
      ) : cases.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-4xl mb-3">✓</p>
          <p className="text-sm font-medium">No resolved cases yet</p>
          <p className="text-xs mt-1">Sessions marked as resolved will appear here</p>
        </div>
      ) : (
        <div className="space-y-3">
          {cases.map((c, i) => {
            const sc = severityColor(c.severity);
            const isOpen = expanded === i;
            const oc = OUTCOME_COLORS[c.note?.outcome];
            return (
              <div key={i} className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                {/* Case header */}
                <div
                  className="px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => setExpanded(isOpen ? null : i)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {c.profile ? (
                        <span className="text-sm font-semibold text-gray-900">{c.profile.name}</span>
                      ) : (
                        <span className="text-sm font-semibold text-gray-900">{c.student_id || 'Unknown'}</span>
                      )}
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.bg} ${sc.text}`}>{c.severity}</span>
                      {c.note?.outcome && (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${oc?.badge}`}>
                          {OUTCOME_LABELS[c.note.outcome]}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {c.profile && (
                        <span className="text-xs text-gray-400">
                          {c.profile.student_id}
                          {c.profile.program && ` · ${c.profile.program}`}
                          {c.profile.year && `, Year ${c.profile.year}`}
                        </span>
                      )}
                      <span className="text-xs text-gray-400">{formatRelative(c.timestamp)}</span>
                      <span className="text-xs text-gray-400">{c.transcript?.length || 0} messages</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        downloadSessionPdf(c.session_id);
                      }}
                      className="text-xs px-2.5 py-1 bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-lg border border-gray-200 transition-colors"
                    >
                      Export PDF
                    </button>
                    <button
                      onClick={(e) => handleDelete(c.session_id, e)}
                      className="text-xs px-2.5 py-1 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg border border-red-100 transition-colors"
                    >
                      Delete
                    </button>
                    
                    <span className="text-gray-400 text-sm">{isOpen ? '▲' : '▼'}</span>
                  </div>
                </div>

                {/* Expanded content */}
                {isOpen && (
                  <div className="border-t border-gray-100">
                    {/* Case note */}
                    {c.note && (
                      <div className="px-5 py-4 border-b border-gray-50">
                        <p className="text-xs font-semibold text-gray-900 mb-1">Case Note</p>
                        <p className="text-xs text-gray-600 leading-relaxed">{c.note.note || '—'}</p>
                      </div>
                    )}

                    {/* Transcript */}
                    <div className="px-5 py-4 bg-gray-50 max-h-80 overflow-y-auto space-y-2">
                      <p className="text-xs font-semibold text-gray-900 mb-2">Transcript</p>
                      {c.transcript?.length === 0 ? (
                        <p className="text-xs text-gray-400">No messages recorded</p>
                      ) : (
                        c.transcript?.map((m, j) => (
                          <div key={j} className={`flex ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[75%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                              m.sender === 'user'
                                ? 'bg-gray-800 text-white rounded-tr-sm'
                                : m.sender === 'counselor'
                                ? 'bg-blue-600 text-white rounded-tl-sm'
                                : 'bg-white text-gray-800 border border-gray-200 rounded-tl-sm'
                            }`}>
                              {m.sender === 'counselor' && <p className="text-blue-200 text-xs font-semibold mb-1">Counselor</p>}
                              {m.sender === 'bot' && <p className="text-gray-400 text-xs font-semibold mb-1">GAIDA</p>}
                              {m.sender === 'system' && <p className="text-gray-400 text-xs font-semibold mb-1">System</p>}
                              <p>{m.message || m.text}</p>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}