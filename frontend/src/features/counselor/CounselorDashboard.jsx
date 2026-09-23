import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, ReferenceLine
} from 'recharts';

import { BACKEND_URL as BACKEND } from '../../config';
import apiFetch from '../../api';

// ── Shared palette ─────────────────────────────────────────────────────────
// Same cool-blue / soft-green identity as the student interface. Bright red
// is reserved for genuine crisis-level and overdue/unaddressed states, not
// used as a general UI color.
const P = {
  bg: '#F7FAF9',
  surface: '#FFFFFF',
  panel: '#EEF4F6',
  border: '#DCE7EA',
  navy: '#22303A',
  navyLight: '#33454F',
  accent: '#5E8FBD',
  accentDark: '#4A7699',
  accentSoft: '#DCEAF3',
  green: '#6BA187',
  greenDark: '#54896D',
  greenSoft: '#E2F0E4',
  amber: '#C98B3D',
  amberSoft: '#F5E9D6',
  teal: '#4C8F8F',
  tealSoft: '#DCEFEF',
  red: '#B0472F',
  redSoft: '#FBEDEA',
  redBorder: '#F0D2CA',
  textPrimary: '#2E3B44',
  textSecondary: '#5C6F78',
  textMuted: '#95A6AC',
};

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
// Crisis and overdue/urgent escalation are the only states that use the
// reserved emergency red. High is a strong amber so it still reads as
// distinct and important without pulling the alarm color.
const severityColor = (s) => {
  if (s === 'Crisis') return { bg: `bg-[${P.red}]`, text: 'text-white', dot: `bg-[${P.red}]`, border: `border-[${P.redBorder}]`, light: `bg-[${P.redSoft}]`, hex: P.red };
  if (s === 'High') return { bg: `bg-[${P.amber}]`, text: 'text-white', dot: `bg-[${P.amber}]`, border: `border-[${P.amberSoft}]`, light: `bg-[${P.amberSoft}]`, hex: P.amber };
  if (s === 'Requested') return { bg: `bg-[${P.accent}]`, text: 'text-white', dot: `bg-[${P.accent}]`, border: `border-[${P.accentSoft}]`, light: `bg-[${P.accentSoft}]`, hex: P.accent };
  if (s === 'Moderate') return { bg: `bg-[${P.teal}]`, text: 'text-white', dot: `bg-[${P.teal}]`, border: `border-[${P.tealSoft}]`, light: `bg-[${P.tealSoft}]`, hex: P.teal };
  if (s === 'Low') return { bg: `bg-[${P.green}]`, text: 'text-white', dot: `bg-[${P.green}]`, border: `border-[${P.greenSoft}]`, light: `bg-[${P.greenSoft}]`, hex: P.green };
  return { bg: `bg-[${P.textMuted}]`, text: 'text-white', dot: `bg-[${P.textMuted}]`, border: `border-[${P.border}]`, light: `bg-[${P.panel}]`, hex: P.textMuted };
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
  { id: 'overview',  label: 'Overview' },
  { id: 'alerts',    label: 'Alerts' },
  { id: 'welfare',   label: 'Welfare Checks' },
  { id: 'sessions',  label: 'Active Sessions' },
  { id: 'detection', label: 'Anxiety Detection' },
  { id: 'reports',   label: 'Reports' },
  { id: 'resolved',  label: 'Resolved Cases' },
];

// One consistent line-icon set for the sidebar (was a mix of emoji and
// symbol glyphs that rendered at different weights/sizes across browsers).
function NavIcon({ id, size = 19 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' };
  switch (id) {
    case 'overview':
      return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>;
    case 'alerts':
      return <svg {...common}><path d="M12 4L3 20h18L12 4z" /><path d="M12 10v4" /><circle cx="12" cy="17" r="0.5" fill="currentColor" /></svg>;
    case 'welfare':
      return <svg {...common}><path d="M6 4c0 8 6 14 14 14l1-4-5-2-2 2c-2.5-1.3-4.7-3.5-6-6l2-2-2-5-4 1z" /></svg>;
    case 'sessions':
      return <svg {...common}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" /></svg>;
    case 'detection':
      return <svg {...common}><path d="M2 12h4l2 7 3-14 2 9 2-4h7" /></svg>;
    case 'reports':
      return <svg {...common}><line x1="4" y1="7" x2="20" y2="7" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="17" x2="14" y2="17" /></svg>;
    case 'resolved':
      return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>;
    default:
      return null;
  }
}

// ── Small shared UI pieces ───────────────────────────────────────────────────
function Card({ children, className = '', style = {} }) {
  return (
    <div
      className={`rounded-2xl shadow-sm ${className}`}
      style={{ background: P.surface, border: `1px solid ${P.border}`, ...style }}
    >
      {children}
    </div>
  );
}

function EmptyState({ icon, title, sub }) {
  return (
    <div className="text-center py-20" style={{ color: P.textMuted }}>
      <p className="text-4xl mb-3">{icon}</p>
      <p className="text-sm font-semibold" style={{ color: P.textSecondary }}>{title}</p>
      {sub && <p className="text-xs mt-1">{sub}</p>}
    </div>
  );
}

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
    Low: P.green,
    Moderate: P.teal,
    High: P.amber,
    Normal: P.textMuted,
    Crisis: P.red,
  };

  const distributionData = analytics?.anxiety_distribution?.map(d => ({
    ...d,
    color: DISTRIBUTION_COLORS[d.name] || P.textMuted,
  })) || [
    { name: 'Low', value: 0, color: P.green },
    { name: 'Moderate', value: 0, color: P.teal },
    { name: 'High', value: 0, color: P.amber },
    { name: 'Normal', value: 0, color: P.textMuted },
    { name: 'Crisis', value: 0, color: P.red },
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
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Counselor Dashboard</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>University of the East - Guidance System Overview</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Active Sessions', value: sessions.length, sub: 'right now', color: P.accent },
          { label: 'Pending Alerts', value: pending, sub: 'need attention', color: pending > 0 ? P.red : P.textMuted },
          { label: 'High Anxiety', value: highSessions, sub: 'active sessions', color: P.amber },
          { label: 'Total Alerts', value: analytics?.total_alerts ?? alerts.length, sub: 'all time', color: P.navy },
        ].map((s) => (
          <Card key={s.label} className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs mb-1" style={{ color: P.textSecondary }}>{s.label}</p>
              <p className="text-2xl font-bold" style={{ color: P.textPrimary }}>{s.value}</p>
              <p className="text-xs mt-0.5" style={{ color: P.textMuted }}>{s.sub}</p>
            </div>
            <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: s.color }}>
              <span className="text-white text-lg font-bold">{s.value}</span>
            </div>
          </Card>
        ))}
      </div>
      {analyticsError && (
        <div className="mb-5 p-3 rounded-xl text-xs" style={{ background: P.amberSoft, border: `1px solid ${P.amber}`, color: '#7A5A28' }}>
          Could not load analytics: {analyticsError}
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 mb-5">
        <Card className="p-5">
          <h3 className="text-sm font-semibold mb-4" style={{ color: P.textPrimary }}>Anxiety Level Trends</h3>
          {!analytics ? (
            <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>Loading trends...</p>
          ) : !hasTrendData ? (
            <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>No trend data yet — appears once students have sessions</p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={P.border} />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: P.textSecondary }} />
                  <YAxis tick={{ fontSize: 11, fill: P.textSecondary }} allowDecimals={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="normal" stroke={P.textMuted} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="low" stroke={P.green} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="moderate" stroke={P.teal} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="high" stroke={P.amber} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="crisis" stroke={P.red} strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-3 mt-3">
                {[
                  { label: 'Normal',  color: P.textMuted },
                  { label: 'Low',     color: P.green },
                  { label: 'Moderate', color: P.teal },
                  { label: 'High',    color: P.amber },
                  { label: 'Crisis',  color: P.red },
                ].map(l => (
                  <div key={l.label} className="flex items-center gap-1">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: l.color }} />
                    <span className="text-xs" style={{ color: P.textSecondary }}>{l.label}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold mb-4" style={{ color: P.textPrimary }}>Sessions This Week</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weekData}>
              <CartesianGrid strokeDasharray="3 3" stroke={P.border} />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: P.textSecondary }} />
              <YAxis tick={{ fontSize: 11, fill: P.textSecondary }} />
              <Tooltip />
              <Bar dataKey="count" fill={P.accent} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Card className="p-5">
          <h3 className="text-sm font-semibold mb-4" style={{ color: P.textPrimary }}>Anxiety Distribution</h3>
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
                  <span className="text-xs" style={{ color: P.textSecondary }}>{d.name}</span>
                  <span className="text-xs font-semibold ml-auto pl-4" style={{ color: P.textPrimary }}>{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold mb-4" style={{ color: P.textPrimary }}>Recent Alerts</h3>
          {alerts.length === 0 ? (
            <p className="text-xs text-center py-6" style={{ color: P.textMuted }}>No alerts yet</p>
          ) : (
            <div className="space-y-3">
              {alerts.slice(0, 5).map((a, i) => {
                const sc = severityColor(a.severity);
                return (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ background: sc.hex }} />
                      <div>
                        <p className="text-xs font-semibold" style={{ color: P.textPrimary }}>{a.session_id.slice(0, 8)}...</p>
                        <p className="text-xs" style={{ color: P.textMuted }}>{a.severity} - {a.intent}</p>
                      </div>
                    </div>
                    <span className="text-xs" style={{ color: P.textMuted }}>{formatRelative(a.timestamp)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
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

  // Overdue/urgent are genuinely time-critical — this is the one place on
  // the dashboard that intentionally borrows the reserved emergency red.
  const borderColor =
    esc.level === 'overdue' ? P.red :
    esc.level === 'urgent'  ? P.red :
    esc.level === 'warning' ? P.amber :
    a.severity === 'Crisis' ? P.red :
    a.severity === 'High'   ? P.amber :
    a.severity === 'Requested' ? P.accent :
    P.amber;

  const bgColor =
    esc.level === 'overdue' ? '#F6DDD5' :
    esc.level === 'urgent'  ? P.redSoft :
    esc.level === 'warning' ? P.amberSoft :
    a.severity === 'Crisis' ? P.redSoft :
    a.severity === 'High'   ? P.amberSoft :
    a.severity === 'Requested' ? P.accentSoft :
    P.amberSoft;

  return (
    <div
      className="p-4 rounded-r-xl mb-3"
      style={{ borderLeft: `4px solid ${borderColor}`, background: bgColor }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.text}`} style={{ background: sc.hex }}>{a.severity}</span>
            <span className="text-xs" style={{ color: P.textSecondary }}>{a.intent}</span>
            <span className="text-xs" style={{ color: P.textMuted }}>{formatRelative(a.timestamp)}</span>

            {/* Escalation badge */}
            {esc.level === 'overdue' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-semibold text-white" style={{ background: P.red }}>
                Overdue {esc.ageMinutes}m
              </span>
            )}
            {esc.level === 'urgent' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-semibold text-white" style={{ background: P.red }}>
                Unattended {esc.ageMinutes}m
              </span>
            )}
            {esc.level === 'warning' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: P.amber }}>
                Waiting {esc.ageMinutes}m+
              </span>
            )}

            {/* Needs-supervisor badge (alert passed the overdue deadline) */}
            {a.needs_supervisor && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: P.navy }}>
                Needs supervisor
              </span>
            )}

            {/* Off-hours tag */}
            {esc.isOffHours && (
              <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: P.navyLight }}>
                Off-hours
              </span>
            )}
          </div>
          <p className="text-xs font-semibold mb-1" style={{ color: P.textSecondary }}>Session: {a.session_id.slice(0, 16)}...</p>
          <p className="text-xs truncate" style={{ color: P.textSecondary }}>"{a.message}"</p>
          {a.acknowledged && (
            <p className="text-xs mt-1" style={{ color: P.greenDark }}>
              Acknowledged{a.acknowledged_at ? ` ${formatRelative(a.acknowledged_at)}` : ''}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2 flex-shrink-0">
          <button
            onClick={() => onViewChat(a.session_id)}
            className="text-xs px-3 py-1.5 rounded-lg font-medium text-white transition-colors duration-200"
            style={{ background: P.navy }}
          >
            View Chat
          </button>
          {actionable && needsAck && !a.acknowledged && (
            <button
              onClick={() => onAcknowledge(a.session_id)}
              className="text-xs px-3 py-1.5 rounded-lg font-semibold text-white transition-colors duration-200"
              style={{ background: P.red }}
            >
              Acknowledge
            </button>
          )}
          {actionable && (!needsAck || a.acknowledged) && (
            <button
              onClick={() => onUpdateStatus(a.session_id, 'reviewed')}
              className="text-xs px-3 py-1.5 rounded-lg font-medium transition-colors duration-200"
              style={{ border: `1px solid ${P.border}`, color: P.textSecondary, background: P.surface }}
            >
              Mark Reviewed
            </button>
          )}
        </div>
      </div>

      {/* Urgent warning bar */}
      {(esc.level === 'urgent' || esc.level === 'overdue') && (
        <div className="mt-3 pt-3 flex items-center gap-2" style={{ borderTop: `1px solid ${P.redBorder}` }}>
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: P.red }} />
          <p className="text-xs font-medium" style={{ color: '#8C3A26' }}>
            This alert has been waiting {esc.ageMinutes} minutes without a response.
            {esc.isOffHours && ' Session occurred outside office hours.'}
          </p>
        </div>
      )}

      {/* Overdue → supervisor notice (server also re-notifies by email) */}
      {esc.level === 'overdue' && (
        <div className="mt-2 pt-2 flex items-start gap-2" style={{ borderTop: `1px solid ${P.redBorder}` }}>
          <div className="w-2 h-2 rounded-full flex-shrink-0 mt-0.5" style={{ background: P.red }} />
          <p className="text-xs font-semibold" style={{ color: '#8C3A26' }}>
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
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Alerts</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>High and Crisis level sessions requiring attention</p>
      </div>
      {pending.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full" style={{ background: P.red }} />
            <h3 className="text-sm font-semibold" style={{ color: P.textPrimary }}>Pending ({pending.length})</h3>
          </div>
          {pending.map((a) => <AlertRow key={a.session_id} a={a} onViewChat={onViewChat} onUpdateStatus={onUpdateStatus} onAcknowledge={onAcknowledge} />)}
        </div>
      )}
      {escalated.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full" style={{ background: P.accent }} />
            <h3 className="text-sm font-semibold" style={{ color: P.textPrimary }}>In Progress — Counselor Engaged ({escalated.length})</h3>
          </div>
          {escalated.map((a) => <AlertRow key={a.session_id} a={a} onViewChat={onViewChat} onUpdateStatus={onUpdateStatus} onAcknowledge={onAcknowledge} />)}
        </div>
      )}
      {resolved.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: P.textMuted }}>Reviewed / Resolved ({resolved.length})</h3>
          {resolved.map((a) => <AlertRow key={a.session_id} a={a} onViewChat={onViewChat} onUpdateStatus={onUpdateStatus} onAcknowledge={onAcknowledge} />)}
        </div>
      )}
      {alerts.length === 0 && <EmptyState icon="✓" title="No alerts" sub="High and Crisis sessions will appear here" />}
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
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Welfare Checks</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>
          High/Crisis sessions that went silent with no follow-up — worth a human check-in
        </p>
      </div>
      {welfare.length > 0 ? (
        welfare.map((w) => {
          const sc = severityColor(w.peak_severity);
          return (
            <div key={w.session_id} className="p-4 rounded-r-xl mb-3" style={{ borderLeft: `4px solid ${P.red}`, background: P.redSoft }}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: sc.hex }}>
                      Peak: {w.peak_severity}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: P.navyLight }}>
                      Silent {w.idle_minutes}m
                    </span>
                  </div>
                  <p className="text-xs font-semibold mb-1" style={{ color: P.textSecondary }}>Session: {w.session_id.slice(0, 16)}...</p>
                  {w.last_message && <p className="text-xs truncate" style={{ color: P.textSecondary }}>Last message: "{w.last_message}"</p>}
                </div>
                <div className="flex flex-col gap-2 flex-shrink-0">
                  <button onClick={() => onViewChat(w.session_id)} className="text-xs px-3 py-1.5 rounded-lg font-medium text-white" style={{ background: P.navy }}>View Chat</button>
                  <button onClick={() => onMarkChecked(w.session_id)} className="text-xs px-3 py-1.5 rounded-lg font-medium" style={{ border: `1px solid ${P.border}`, color: P.textSecondary, background: P.surface }}>Mark Checked</button>
                </div>
              </div>
            </div>
          );
        })
      ) : (
        <EmptyState icon="☎" title="No welfare checks needed" sub="Silent High/Crisis sessions will appear here" />
      )}
    </div>
  );
}

// ── Active Sessions Page ──────────────────────────────────────────────────────
function SessionsPage({ sessions, onViewChat, lastUpdated }) {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Active Sessions</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>Severity levels visible - chat content only shown for flagged sessions</p>
      </div>
      {sessions.length === 0 ? (
        <EmptyState icon="◉" title="No active sessions" sub="Sessions appear here when students are chatting" />
      ) : (
        <Card className="overflow-hidden">
          <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: `1px solid ${P.border}` }}>
            <span className="text-sm font-semibold" style={{ color: P.textPrimary }}>Sessions ({sessions.length})</span>
            <span className="text-xs" style={{ color: P.textMuted }}>
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Auto-refreshing...'}
            </span>
          </div>
          <div>
            {sessions.map((s, idx) => {
              const sc = severityColor(s.severity);
              return (
                <div
                  key={s.session_id}
                  className="px-5 py-4 flex items-center gap-4"
                  style={{ borderTop: idx === 0 ? 'none' : `1px solid ${P.panel}` }}
                >
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: sc.hex }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-sm font-semibold" style={{ color: P.textPrimary }}>{s.session_id.slice(0, 16)}...</span>
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: sc.hex }}>{s.severity}</span>
                      {s.has_alert && <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: P.redSoft, color: P.red }}>Alert</span>}
                      {s.assigned_counselor_id && <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: P.accentSoft, color: P.accentDark }}>Assigned</span>}
                    </div>
                    <p className="text-xs" style={{ color: P.textMuted }}>{s.message_count} messages • {formatDuration(s.started_at)} • intent: {s.intent}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="text-right mr-2">
                      <p className="text-xs" style={{ color: P.textMuted }}>Confidence</p>
                      <p className="text-sm font-bold" style={{ color: P.textPrimary }}>{(s.confidence * 100).toFixed(0)}%</p>
                    </div>
                    {(s.severity === 'High' || s.severity === 'Crisis' || s.has_alert) && (
                      <button
                        onClick={() => onViewChat(s.session_id)}
                        className="text-xs px-3 py-1.5 rounded-lg font-medium text-white"
                        style={{ background: P.accent }}
                      >
                        View Chat
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}

// ── Chat Modal ────────────────────────────────────────────────────────────────
function ChatModal({ sessionId, onClose }) {
  const [messages, setMessages] = useState([]);
  const messagesRef = useRef([]); // mirror used to dedupe realtime WS appends vs the 3s poll
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
    resolved:    { dot: P.green,  badge: { bg: P.greenSoft, color: P.greenDark } },
    false_alarm: { dot: P.textMuted, badge: { bg: P.panel, color: P.textSecondary } },
    referred:    { dot: P.accent, badge: { bg: P.accentSoft, color: P.accentDark } },
    follow_up:   { dot: P.amber,  badge: { bg: P.amberSoft, color: '#7A5A28' } },
    ongoing:     { dot: P.red,    badge: { bg: P.redSoft, color: P.red } },
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

  // Realtime live-chat updates: student messages, typing, and takeover state
  // arrive over the per-session WebSocket (same feed the student uses), so a
  // live conversation updates instantly instead of waiting for the 3s poll.
  // The poll stays as the fallback for dropped/reconnecting sockets.
  useEffect(() => {
    const token = localStorage.getItem('counselor_token');
    if (!token) return undefined;

    let ws = null;
    let closed = false;
    let retryDelay = 1000;
    let retryTimer = null;

    const handleRealtime = (msg) => {
      if (!msg || typeof msg !== 'object') return;
      switch (msg.type) {
        case 'interaction':
          // Mirror the new message (student, bot reply, system, or this
          // counselor's own echo — the dedupe in appendRealtimeMessage
          // prevents overlaps with the poll).
          appendRealtimeMessage(msg);
          break;
        case 'typing':
          if (msg.sender === 'student') setStudentTyping(!!msg.is_typing);
          break;
        case 'counselor_active':
          if (typeof msg.active === 'boolean') {
            const myId = getCounselorId();
            const mine = !msg.assigned_counselor_id || msg.assigned_counselor_id === myId;
            setTookOver(msg.active && mine);
          }
          break;
        default:
          break;
      }
    };

    const connect = () => {
      const wsUrl = `${BACKEND.replace(/^http/, 'ws')}/api/session/ws/${sessionId}?token=${encodeURIComponent(token)}`;
      try {
        ws = new WebSocket(wsUrl);
      } catch {
        scheduleRetry();
        return;
      }

      ws.onopen = () => { retryDelay = 1000; };

      ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        handleRealtime(msg);
      };

      ws.onclose = () => {
        ws = null;
        if (!closed) scheduleRetry();
      };

      ws.onerror = () => {
        try { if (ws) ws.close(); } catch { /* onclose schedules the retry */ }
      };
    };

    const scheduleRetry = () => {
      clearTimeout(retryTimer);
      retryTimer = setTimeout(() => {
        retryDelay = Math.min(retryDelay * 2, 15000);
        connect();
      }, retryDelay);
    };

    connect();

    return () => {
      closed = true;
      clearTimeout(retryTimer);
      if (ws) {
        try { ws.onclose = null; ws.close(); } catch { /* socket already gone */ }
        ws = null;
      }
    };
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

  // Append a message pushed over the realtime WebSocket, deduped against the
  // transcript the poll returns (matched by sender + timestamp + text, all
  // sourced from the same server-side entry, so keys are stable).
  const appendRealtimeMessage = (msg) => {
    if (!msg || !msg.text) return;
    const key = `${msg.sender}|${msg.timestamp}|${msg.text}`;
    if (messagesRef.current.some(m => `${m.sender}|${m.timestamp}|${m.text}` === key)) return;
    const next = [...messagesRef.current, {
      sender: msg.sender,
      text: msg.text,
      timestamp: msg.timestamp,
      intent: msg.analysis?.intent,
      confidence: msg.analysis?.confidence,
    }];
    messagesRef.current = next;
    setMessages(next);
  };

  const fetchChat = async () => {
    try {
      const res = await apiFetch(`${BACKEND}/api/counselor/chat/${sessionId}`);
      const data = await res.json();
      if (data.messages) {
        setMessages(data.messages);
        messagesRef.current = data.messages;
      }
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
    const colors = { Crisis: P.red, High: P.amber, Moderate: P.teal, Low: P.green, Normal: P.textMuted };
    return <circle cx={cx} cy={cy} r={4} fill={colors[payload.severity] || P.textMuted} stroke="white" strokeWidth={1.5} />;
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(34,48,58,0.55)' }}>
      <div className="rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-xl" style={{ background: P.surface }}>

        {/* Header */}
        <div className="px-5 py-4 flex items-center justify-between flex-shrink-0" style={{ borderBottom: `1px solid ${P.border}` }}>
          <div>
            {studentProfile ? (
              <>
                <p className="text-sm font-bold" style={{ color: P.textPrimary }}>{studentProfile.name}</p>
                <p className="text-xs" style={{ color: P.textSecondary }}>
                  {studentProfile.student_id}
                  {studentProfile.program && ` · ${studentProfile.program}`}
                  {studentProfile.year && `, Year ${studentProfile.year}`}
                </p>
              </>
            ) : (
              <>
                <h3 className="text-sm font-bold" style={{ color: P.textPrimary }}>Live Session</h3>
                <p className="text-xs" style={{ color: P.textSecondary }}>{sessionId.slice(0, 24)}...</p>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportSession}
              disabled={exporting}
              className="text-xs px-3 py-1.5 rounded-lg transition-colors duration-200 disabled:opacity-50 flex items-center gap-1.5"
              style={{ background: P.panel, color: P.textSecondary, border: `1px solid ${P.border}` }}
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
              <span className="text-xs font-medium" style={{ color: P.greenDark }}>Session resolved</span>
            ) : (
              <button
                onClick={handleResolve}
                disabled={resolving || !savedNote}
                title={!savedNote ? 'Save a case note before resolving' : undefined}
                className="text-xs px-3 py-1.5 rounded-lg text-white disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors duration-200"
                style={{ background: P.green }}
              >
                {resolving ? 'Resolving...' : 'Resolve session'}
              </button>
            )}
            <div className="w-2 h-2 rounded-full" style={{ background: P.green }} />
            <span className="text-xs mr-2" style={{ color: P.textMuted }}>Live</span>
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-sm font-bold transition-colors duration-200"
              style={{ border: `1px solid ${P.border}`, color: P.textSecondary }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex flex-shrink-0" style={{ borderBottom: `1px solid ${P.border}` }}>
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className="flex-1 py-2.5 text-xs font-medium transition-colors duration-200 relative"
              style={
                activeTab === t.id
                  ? { background: P.panel, color: P.textPrimary, borderBottom: `2px solid ${P.accent}` }
                  : { color: P.textMuted }
              }
            >
              {t.label}
              {t.id === 'notes' && savedNote && (
                <span className="absolute top-1.5 right-3 w-1.5 h-1.5 rounded-full" style={{ background: P.accent }} />
              )}
            </button>
          ))}
        </div>

        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0" style={{ background: P.bg }}>
            {loading ? (
              <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>Loading chat...</p>
            ) : messages.length === 0 ? (
              <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>No messages yet</p>
            ) : (
              messages
                .filter((m, i, arr) => {
                  if (i === 0) return true;
                  const prev = arr[i - 1];
                  return !(prev.sender === m.sender && prev.text === m.text);
                })
                .map((m, i) => (
                  <div key={i} className={`flex ${m.sender === 'student' || m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className="max-w-[75%] px-3 py-2 rounded-xl text-xs leading-relaxed"
                      style={
                        m.sender === 'student' || m.sender === 'user'
                          ? { background: P.navy, color: '#FFFFFF', borderTopRightRadius: '4px' }
                          : m.sender === 'counselor'
                          ? { background: P.accent, color: '#FFFFFF', borderTopLeftRadius: '4px' }
                          : { background: P.surface, color: P.textPrimary, border: `1px solid ${P.border}`, borderTopLeftRadius: '4px' }
                      }
                    >
                      {m.sender === 'counselor' && <p className="text-xs font-semibold mb-1" style={{ color: '#E3EEF6' }}>You (Counselor)</p>}
                      {m.sender === 'bot' && <p className="text-xs font-semibold mb-1" style={{ color: P.textMuted }}>GAIDA</p>}
                      <p>{m.text}</p>
                      {(m.sender === 'user' || m.sender === 'student') && m.confidence && (
                        <div className="flex items-center gap-1 mt-1">
                          <div className="w-1.5 h-1.5 rounded-full" style={{
                            background:
                              confidenceToSeverity(m.confidence) === 'High' ? P.amber :
                              confidenceToSeverity(m.confidence) === 'Moderate' ? P.teal :
                              confidenceToSeverity(m.confidence) === 'Low' ? P.green : P.textMuted
                          }} />
                          <p className="text-xs" style={{ color: '#C3CDD2' }}>{m.intent} • {(m.confidence * 100).toFixed(0)}% • {confidenceToSeverity(m.confidence)}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))
            )}
            {studentTyping && (
              <div className="flex justify-end">
                <div className="px-3 py-2 rounded-xl" style={{ background: P.navyLight, borderTopRightRadius: '4px' }}>
                  <div className="flex gap-1 items-center h-4">
                    <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#C3CDD2', animationDelay:'0ms'}}></div>
                    <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#C3CDD2', animationDelay:'150ms'}}></div>
                    <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#C3CDD2', animationDelay:'300ms'}}></div>
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
              <p className="text-xs font-semibold mb-1" style={{ color: P.textPrimary }}>Anxiety Confidence Over Session</p>
              <p className="text-xs" style={{ color: P.textMuted }}>Each point = one student message. Color = detected severity.</p>
            </div>
            {severityHistory.length === 0 ? (
              <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>No data yet - waiting for student messages</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={severityHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={P.border} />
                    <XAxis dataKey="msg" tick={{ fontSize: 10, fill: P.textSecondary }} label={{ value: 'Message #', position: 'insideBottom', offset: -2, fontSize: 10, fill: P.textSecondary }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: P.textSecondary }} tickFormatter={v => `${v}%`} />
                    <Tooltip
                      formatter={(val) => [`${val}%`, 'Confidence']}
                      labelFormatter={(label, payload) => payload?.[0]?.payload?.text || `Message ${label}`}
                    />
                    <ReferenceLine y={75} stroke={P.amber} strokeDasharray="3 3" label={{ value: 'High', fill: P.amber, fontSize: 10 }} />
                    <ReferenceLine y={60} stroke={P.teal} strokeDasharray="3 3" label={{ value: 'Moderate', fill: P.teal, fontSize: 10 }} />
                    <ReferenceLine y={45} stroke={P.green} strokeDasharray="3 3" label={{ value: 'Low', fill: P.green, fontSize: 10 }} />
                    <Line type="monotone" dataKey="confidence" stroke={P.textSecondary} strokeWidth={2} dot={<CustomDot />} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-3 mt-3">
                  {[
                    { label: 'Normal', color: P.textMuted },
                    { label: 'Low', color: P.green },
                    { label: 'Moderate', color: P.teal },
                    { label: 'High', color: P.amber },
                    { label: 'Crisis', color: P.red },
                  ].map(l => (
                    <div key={l.label} className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: l.color }} />
                      <span className="text-xs" style={{ color: P.textSecondary }}>{l.label}</span>
                    </div>
                  ))}
                </div>
                {severityHistory.length > 0 && (() => {
                  const last = severityHistory[severityHistory.length - 1];
                  const sc = severityColor(last.severity);
                  return (
                    <div className="mt-3 p-3 rounded-xl" style={{ background: sc.light, border: `1px solid ${sc.hex}33` }}>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs font-semibold" style={{ color: P.textPrimary }}>Current Status</p>
                          <p className="text-xs" style={{ color: P.textMuted }}>Based on latest message</p>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-bold px-3 py-1 rounded-full text-white" style={{ background: sc.hex }}>{last.severity}</span>
                          <p className="text-xs mt-1" style={{ color: P.textMuted }}>{last.confidence}% confidence</p>
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
              <div className="mb-4 p-3 rounded-xl flex items-center justify-between" style={{ background: P.accentSoft, border: `1px solid ${P.accent}55` }}>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium" style={{ color: P.accentDark }}>Note saved</span>
                  {(savedNote.updated_at || savedNote.created_at) && (
                    <span className="text-xs" style={{ color: P.accentDark, opacity: 0.7 }}>{formatRelative(savedNote.updated_at || savedNote.created_at)}</span>
                  )}
                </div>
                {savedNote.outcome && (() => {
                  const oc = OUTCOME_COLORS[savedNote.outcome];
                  const outcomeLabel = OUTCOMES.find(o => o.value === savedNote.outcome)?.label;
                  return (
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: oc?.badge.bg, color: oc?.badge.color }}>
                      {outcomeLabel}
                    </span>
                  );
                })()}
              </div>
            )}

            {/* Outcome selector */}
            <div className="mb-4">
              <p className="text-xs font-semibold mb-2" style={{ color: P.textPrimary }}>Outcome</p>
              <div className="space-y-2">
                {OUTCOMES.map(o => {
                  const oc = OUTCOME_COLORS[o.value];
                  const selected = noteOutcome === o.value;
                  return (
                    <button
                      key={o.value}
                      onClick={() => setNoteOutcome(o.value)}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors duration-200"
                      style={selected ? { border: `1px solid ${P.accent}`, background: P.accentSoft } : { border: `1px solid ${P.border}` }}
                    >
                      <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: oc.dot }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold" style={{ color: selected ? P.textPrimary : P.textSecondary }}>{o.label}</p>
                        <p className="text-xs" style={{ color: P.textMuted }}>{o.desc}</p>
                      </div>
                      {selected && <span className="text-xs flex-shrink-0" style={{ color: P.accentDark }}>✓</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Notes textarea */}
            <div className="mb-4">
              <p className="text-xs font-semibold mb-2" style={{ color: P.textPrimary }}>Notes</p>
              <textarea
                value={noteText}
                onChange={e => setNoteText(e.target.value)}
                placeholder="Document what happened, what was said, and any follow-up actions..."
                rows={5}
                className="w-full text-xs px-3 py-2 rounded-xl focus:outline-none resize-none leading-relaxed"
                style={{ border: `1px solid ${P.border}`, color: P.textPrimary }}
              />
            </div>

            {noteError && (
              <p className="text-xs mb-3" style={{ color: P.red }}>{noteError}</p>
            )}

            <button
              onClick={handleSaveNote}
              disabled={savingNote}
              className="w-full py-2.5 text-white text-xs font-medium rounded-xl disabled:opacity-50 transition-colors duration-200"
              style={{ background: P.navy }}
            >
              {savingNote ? 'Saving...' : savedNote ? 'Update note' : 'Save note'}
            </button>
          </div>
        )}

        {/* Quick Responses + Input — hidden on notes tab */}
        {activeTab !== 'notes' && (
          <div className="px-4 pt-3 flex-shrink-0" style={{ borderTop: `1px solid ${P.border}` }}>
            {actionError && (
              <p className="text-xs mb-2 rounded-lg px-3 py-2" style={{ color: P.red, background: P.redSoft, border: `1px solid ${P.redBorder}` }}>{actionError}</p>
            )}
            <p className="text-xs mb-2" style={{ color: P.textMuted }}>Quick responses:</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {QUICK_RESPONSES.map((r) => (
                <button
                  key={r.label}
                  onClick={() => sendTakeover(r.text)}
                  disabled={sending}
                  className="text-xs px-2.5 py-1 rounded-full transition-colors duration-200 disabled:opacity-50"
                  style={{ background: P.panel, color: P.textSecondary, border: `1px solid ${P.border}` }}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {tookOver && (
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium" style={{ color: P.accentDark }}>You have joined this session</p>
                <button
                  onClick={handleReturnToGaida}
                  disabled={returningToGaida}
                  className="text-xs px-3 py-1 rounded-full transition-colors duration-200 disabled:opacity-50"
                  style={{ background: P.panel, color: P.textSecondary, border: `1px solid ${P.border}` }}
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
                className="flex-1 text-xs px-3 py-2 rounded-lg focus:outline-none"
                style={{ border: `1px solid ${P.border}`, color: P.textPrimary }}
              />
              <button
                onClick={() => sendTakeover()}
                disabled={sending || !takeoverMsg.trim()}
                className="px-4 py-2 text-white text-xs rounded-lg disabled:opacity-50 font-medium transition-colors duration-200"
                style={{ background: P.accent }}
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
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Multimodal Anxiety Detection</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>Real-time anxiety monitoring using voice and text analysis</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        {[
          { label: 'Voice Analysis', sub: 'Pitch, Energy, Jitter, Speech Rate, Pauses', status: 'Active' },
          { label: 'Text Analysis', sub: 'ML Ensemble: LR + RF + Neural Network', status: 'Active' },
        ].map((m) => (
          <Card key={m.label} className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-2 h-2 rounded-full" style={{ background: P.green }} />
              <p className="text-xs" style={{ color: P.textSecondary }}>{m.label}</p>
            </div>
            <p className="text-xl font-bold mb-1" style={{ color: P.textPrimary }}>{m.status}</p>
            <p className="text-xs" style={{ color: P.textMuted }}>{m.sub}</p>
          </Card>
        ))}
      </div>
      <Card className="p-5">
        <h3 className="text-sm font-semibold mb-3" style={{ color: P.textPrimary }}>Anxiety Level Thresholds</h3>
        <div className="space-y-3">
          {[
            { level: 'Normal', range: '< 0.45', color: P.textMuted, desc: 'GPT responds freely' },
            { level: 'Low', range: '0.45 – 0.60', color: P.green, desc: 'Counselor protocol injected' },
            { level: 'Moderate', range: '0.60 – 0.75', color: P.teal, desc: 'Stronger protocol injected' },
            { level: 'High', range: '0.75 – 0.98', color: P.amber, desc: 'Counselor alert fired' },
            { level: 'Crisis', range: '0.99', color: P.red, desc: 'Immediate intervention' },
          ].map((t) => (
            <div key={t.level} className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: t.color }} />
              <span className="text-xs font-semibold w-16" style={{ color: P.textPrimary }}>{t.level}</span>
              <span className="text-xs w-24" style={{ color: P.textMuted }}>{t.range}</span>
              <span className="text-xs" style={{ color: P.textSecondary }}>{t.desc}</span>
            </div>
          ))}
        </div>
      </Card>
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
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Reports & Analytics</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>System performance and anxiety detection analytics</p>
      </div>
      {reportsError && (
        <div className="mb-5 p-3 rounded-xl text-xs" style={{ background: P.amberSoft, border: `1px solid ${P.amber}`, color: '#7A5A28' }}>
          Could not load reports: {reportsError}
        </div>
      )}
      <Card className="p-5 mb-5">
        <h3 className="text-sm font-semibold mb-4" style={{ color: P.textPrimary }}>Monthly Trends</h3>
        {!reports ? (
          <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>Loading trends...</p>
        ) : !hasTrendData ? (
          <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>No report data yet — appears once students have sessions</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke={P.border} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: P.textSecondary }} />
              <YAxis tick={{ fontSize: 11, fill: P.textSecondary }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="sessions" stroke={P.navy} strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="alerts" stroke={P.red} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>
      <Card className="p-5">
        <h3 className="text-sm font-semibold mb-4" style={{ color: P.textPrimary }}>Severity Breakdown by Month</h3>
        {!reports ? (
          <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>Loading breakdown...</p>
        ) : !hasTrendData ? (
          <p className="text-xs text-center py-8" style={{ color: P.textMuted }}>No breakdown data yet — appears once students have sessions</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom: `1px solid ${P.border}` }}>
                  <th className="text-left py-2 pr-4 font-semibold" style={{ color: P.textMuted }}>Month</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: P.textMuted }}>Sessions</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: P.textMuted }}>Alerts</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: P.textMuted }}>Normal</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: P.green }}>Low</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: P.teal }}>Moderate</th>
                  <th className="text-right py-2 px-3 font-semibold" style={{ color: P.amber }}>High</th>
                  <th className="text-right py-2 pl-3 font-semibold" style={{ color: P.red }}>Crisis</th>
                </tr>
              </thead>
              <tbody>
                {trendData.map((m, i) => (
                  <tr key={i} style={i < trendData.length - 1 ? { borderBottom: `1px solid ${P.panel}` } : {}}>
                    <td className="py-2 pr-4 font-medium" style={{ color: P.textPrimary }}>{m.month}</td>
                    <td className="py-2 px-3 text-right" style={{ color: P.textSecondary }}>{m.sessions || 0}</td>
                    <td className="py-2 px-3 text-right" style={{ color: P.textSecondary }}>{m.alerts || 0}</td>
                    <td className="py-2 px-3 text-right" style={{ color: P.textSecondary }}>{m.normal || 0}</td>
                    <td className="py-2 px-3 text-right" style={{ color: P.textSecondary }}>{m.low || 0}</td>
                    <td className="py-2 px-3 text-right" style={{ color: P.textSecondary }}>{m.moderate || 0}</td>
                    <td className="py-2 px-3 text-right" style={{ color: P.textSecondary }}>{m.high || 0}</td>
                    <td className="py-2 pl-3 text-right font-semibold" style={{ color: P.textPrimary }}>{m.crisis || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
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

  // Realtime push via SSE: the backend broadcasts named events when alerts,
  // active sessions, or welfare checks change, so an open dashboard updates —
  // and beeps/notifies on new alerts — without a reload, even in a background
  // tab (browsers throttle setInterval there but not live network streams).
  // The 2s poll above stays as a fallback for when SSE is unavailable.
  useEffect(() => {
    const token = localStorage.getItem('counselor_token');
    if (!token) return;
    let es = null;
    try {
      es = new EventSource(`${BACKEND}/api/counselor/events?token=${encodeURIComponent(token)}`);
      es.addEventListener('alerts', fetchAlerts);
      es.addEventListener('sessions', fetchSessions);
      es.addEventListener('welfare', fetchWelfare);
      // EventSource auto-reconnects on drop; re-sync on every (re)connect.
      es.onopen = () => {
        fetchAlerts();
        fetchSessions();
        fetchWelfare();
      };
    } catch {
      es = null;
    }
    return () => {
      if (es) es.close();
    };
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
            new Notification('GAIDA Alert', {
              body: `${freshIds.length} new alert${freshIds.length > 1 ? 's' : ''} need attention`,
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
    <div className="min-h-screen flex overflow-hidden" style={{ background: P.bg }}>
      {expanded && <div className="fixed inset-0 z-20" style={{ background: 'rgba(34,48,58,0.25)' }} onClick={() => setExpanded(false)} />}

      {/* Sidebar */}
      <style>{`
        .cdash-nav-btn { border-left: 3px solid transparent; }
        .cdash-nav-btn:hover:not(.cdash-active) { background: rgba(255,255,255,0.06); color: #E3EAEE; }
        .cdash-side-btn:hover { background: rgba(255,255,255,0.06); color: #E3EAEE; }
      `}</style>
      <aside
        className={`fixed top-0 left-0 h-full z-30 flex flex-col shadow-lg transition-all duration-300 ${expanded ? 'w-56' : 'w-16'}`}
        style={{ background: P.navy }}
      >
        <div className="h-14 flex items-center justify-center flex-shrink-0" style={{ borderBottom: `1px solid ${P.navyLight}` }}>
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
            style={{ background: P.accent, boxShadow: `0 0 0 3px ${P.navyLight}` }}
            title={counselor.name || 'Counselor'}
          >
            <span className="text-white text-xs font-bold">{initials}</span>
          </div>
          {expanded && <span className="text-white font-semibold text-sm tracking-wide ml-3 whitespace-nowrap">GAIDA</span>}
        </div>
        <nav className="flex-1 py-4 overflow-y-auto overflow-x-hidden space-y-0.5 px-2">
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
                className={`cdash-nav-btn w-full flex items-center px-3 py-2.5 rounded-lg transition-colors duration-200 relative group ${active ? 'cdash-active' : ''}`}
                style={active ? { background: 'rgba(255,255,255,0.08)', color: '#FFFFFF', borderLeftColor: P.accent } : { color: '#8FA3AC' }}
              >
                <span className="flex-shrink-0 relative flex items-center justify-center" style={{ width: 20, height: 20 }}>
                  <NavIcon id={navItem.id} />
                  {badgeCount > 0 && (
                    <span
                      className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full text-white flex items-center justify-center font-semibold"
                      style={{ fontSize: '9px', background: P.red }}
                    >
                      {badgeCount}
                    </span>
                  )}
                </span>
                {expanded && <span className="ml-3 text-sm font-medium whitespace-nowrap">{navItem.label}</span>}
                {!expanded && (
                  <span
                    className="absolute left-16 text-white text-xs px-2.5 py-1.5 rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-50 shadow-lg"
                    style={{ background: P.navyLight }}
                  >
                    {navItem.label}{badgeCount > 0 && ` (${badgeCount})`}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="flex-shrink-0 px-2 py-2 space-y-0.5" style={{ borderTop: `1px solid ${P.navyLight}` }}>
          <button
            onClick={() => setExpanded(!expanded)}
            className="cdash-side-btn w-full flex items-center px-3 py-2.5 rounded-lg transition-colors duration-200"
            style={{ color: '#8FA3AC' }}
          >
            <span
              className="flex-shrink-0 flex items-center justify-center transition-transform duration-300"
              style={{ width: 20, height: 20, transform: expanded ? 'rotate(180deg)' : 'none' }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 6 15 12 9 18" />
              </svg>
            </span>
            {expanded && <span className="ml-3 text-sm font-medium">Collapse</span>}
          </button>
          <button
            onClick={logout}
            className="cdash-side-btn w-full flex items-center px-3 py-2.5 rounded-lg transition-colors duration-200"
            style={{ color: '#8FA3AC' }}
            title={!expanded ? 'Logout' : undefined}
          >
            <span className="flex-shrink-0 flex items-center justify-center" style={{ width: 20, height: 20 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18.36 6.64a9 9 0 11-12.73 0" />
                <line x1="12" y1="2" x2="12" y2="12" />
              </svg>
            </span>
            {expanded && <span className="ml-3 text-sm font-medium">Logout</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden ml-16">
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
    resolved:    { bg: P.greenSoft, color: P.greenDark },
    false_alarm: { bg: P.panel, color: P.textSecondary },
    referred:    { bg: P.accentSoft, color: P.accentDark },
    follow_up:   { bg: P.amberSoft, color: '#7A5A28' },
    ongoing:     { bg: P.redSoft, color: P.red },
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
        <h1 className="text-2xl font-bold" style={{ color: P.textPrimary }}>Resolved Cases</h1>
        <p className="text-sm mt-0.5" style={{ color: P.textSecondary }}>Closed sessions with case notes and transcripts</p>
      </div>

      {loading ? (
        <p className="text-xs text-center py-20" style={{ color: P.textMuted }}>Loading...</p>
      ) : casesError ? (
        <div className="text-center py-20" style={{ color: P.textSecondary }}>
          <p className="text-sm font-medium">Could not load resolved cases.</p>
          <p className="text-xs mt-1">{casesError}</p>
        </div>
      ) : cases.length === 0 ? (
        <EmptyState icon="✓" title="No resolved cases yet" sub="Sessions marked as resolved will appear here" />
      ) : (
        <div className="space-y-3">
          {cases.map((c, i) => {
            const sc = severityColor(c.severity);
            const isOpen = expanded === i;
            const oc = OUTCOME_COLORS[c.note?.outcome];
            return (
              <Card key={i} className="overflow-hidden">
                {/* Case header */}
                <div
                  className="px-5 py-4 flex items-center gap-4 cursor-pointer transition-colors duration-200"
                  onClick={() => setExpanded(isOpen ? null : i)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {c.profile ? (
                        <span className="text-sm font-semibold" style={{ color: P.textPrimary }}>{c.profile.name}</span>
                      ) : (
                        <span className="text-sm font-semibold" style={{ color: P.textPrimary }}>{c.student_id || 'Unknown'}</span>
                      )}
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: sc.hex }}>{c.severity}</span>
                      {c.note?.outcome && (
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: oc?.bg, color: oc?.color }}>
                          {OUTCOME_LABELS[c.note.outcome]}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {c.profile && (
                        <span className="text-xs" style={{ color: P.textMuted }}>
                          {c.profile.student_id}
                          {c.profile.program && ` · ${c.profile.program}`}
                          {c.profile.year && `, Year ${c.profile.year}`}
                        </span>
                      )}
                      <span className="text-xs" style={{ color: P.textMuted }}>{formatRelative(c.timestamp)}</span>
                      <span className="text-xs" style={{ color: P.textMuted }}>{c.transcript?.length || 0} messages</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        downloadSessionPdf(c.session_id);
                      }}
                      className="text-xs px-2.5 py-1 rounded-lg transition-colors duration-200"
                      style={{ background: P.panel, color: P.textSecondary, border: `1px solid ${P.border}` }}
                    >
                      Export PDF
                    </button>
                    <button
                      onClick={(e) => handleDelete(c.session_id, e)}
                      className="text-xs px-2.5 py-1 rounded-lg transition-colors duration-200"
                      style={{ background: P.redSoft, color: P.red, border: `1px solid ${P.redBorder}` }}
                    >
                      Delete
                    </button>

                    <span className="text-sm" style={{ color: P.textMuted }}>{isOpen ? '▲' : '▼'}</span>
                  </div>
                </div>

                {/* Expanded content */}
                {isOpen && (
                  <div style={{ borderTop: `1px solid ${P.border}` }}>
                    {/* Case note */}
                    {c.note && (
                      <div className="px-5 py-4" style={{ borderBottom: `1px solid ${P.panel}` }}>
                        <p className="text-xs font-semibold mb-1" style={{ color: P.textPrimary }}>Case Note</p>
                        <p className="text-xs leading-relaxed" style={{ color: P.textSecondary }}>{c.note.note || '—'}</p>
                      </div>
                    )}

                    {/* Transcript */}
                    <div className="px-5 py-4 max-h-80 overflow-y-auto space-y-2" style={{ background: P.bg }}>
                      <p className="text-xs font-semibold mb-2" style={{ color: P.textPrimary }}>Transcript</p>
                      {c.transcript?.length === 0 ? (
                        <p className="text-xs" style={{ color: P.textMuted }}>No messages recorded</p>
                      ) : (
                        c.transcript?.map((m, j) => (
                          <div key={j} className={`flex ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div
                              className="max-w-[75%] px-3 py-2 rounded-xl text-xs leading-relaxed"
                              style={
                                m.sender === 'user'
                                  ? { background: P.navy, color: '#FFFFFF', borderTopRightRadius: '4px' }
                                  : m.sender === 'counselor'
                                  ? { background: P.accent, color: '#FFFFFF', borderTopLeftRadius: '4px' }
                                  : { background: P.surface, color: P.textPrimary, border: `1px solid ${P.border}`, borderTopLeftRadius: '4px' }
                              }
                            >
                              {m.sender === 'counselor' && <p className="text-xs font-semibold mb-1" style={{ color: '#E3EEF6' }}>Counselor</p>}
                              {m.sender === 'bot' && <p className="text-xs font-semibold mb-1" style={{ color: P.textMuted }}>GAIDA</p>}
                              {m.sender === 'system' && <p className="text-xs font-semibold mb-1" style={{ color: P.textMuted }}>System</p>}
                              <p>{m.message || m.text}</p>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}