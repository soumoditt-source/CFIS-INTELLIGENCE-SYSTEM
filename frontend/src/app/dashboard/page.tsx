'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  TrendingUp, TrendingDown, Minus, Upload, Clock, CheckCircle2,
  AlertCircle, Mic2, BarChart3, Users, Eye, Trash2, RefreshCw
} from 'lucide-react';
import {
  AreaChart, Area, ResponsiveContainer, XAxis, YAxis,
  Tooltip, PieChart, Pie, Cell, Legend
} from 'recharts';
import AppLayout from '@/components/AppLayout';
import { analyticsApi, recordingsApi, getErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';

// ─── Types ────────────────────────────────────────────────────────────────────
interface Overview {
  total_recordings: number;
  analyzed_recordings: number;
  pending_recordings: number;
  failed_recordings: number;
  avg_sentiment_score: number;
  positive_sessions: number;
  negative_sessions: number;
  neutral_sessions: number;
  reviews_needed: number;
  total_duration_minutes: number;
}

interface Recording {
  id: string;
  original_filename: string;
  status: string;
  duration_seconds?: number;
  file_size_bytes?: number;
  created_at: string;
}

function formatRelativeTime(value?: string) {
  if (!value) return 'Unknown time';

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 'Unknown time';
  }

  return formatDistanceToNow(parsed, { addSuffix: true });
}

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  PENDING:           { label: 'Queued',        color: 'badge-pending',    dot: 'bg-slate-500' },
  AUDIO_PROCESSING:  { label: 'Processing',    color: 'badge-processing', dot: 'bg-amber-500 animate-pulse' },
  AUDIO_READY:       { label: 'Audio Ready',   color: 'badge-processing', dot: 'bg-amber-500 animate-pulse' },
  TRANSCRIBING:      { label: 'Transcribing',  color: 'badge-processing', dot: 'bg-amber-500 animate-pulse' },
  TRANSCRIBED:       { label: 'Transcribed',   color: 'badge-processing', dot: 'bg-amber-500 animate-pulse' },
  ANALYZING:         { label: 'Analyzing',     color: 'badge-processing', dot: 'bg-indigo-400 animate-pulse' },
  ANALYZED:          { label: 'Complete',      color: 'badge-analyzed',   dot: 'bg-emerald-500' },
  FAILED:            { label: 'Failed',        color: 'badge-failed',     dot: 'bg-red-500' },
};

const SENTIMENT_COLORS = ['#10b981', '#ef4444', '#6b7280'];

export default function DashboardPage() {
  const router = useRouter();
  const { isAuthenticated, isGuestSession, hasBootstrapped } = useAuthStore();

  const [overview, setOverview] = useState<Overview | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [trend, setTrend] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const recordingsRef = useRef<Recording[]>([]);

  useEffect(() => {
    recordingsRef.current = recordings;
  }, [recordings]);

  useEffect(() => {
    if (!hasBootstrapped) return;
    if (!isAuthenticated) { router.replace('/auth/login'); return; }
    void loadData();
  }, [hasBootstrapped, isAuthenticated, router]);

  useEffect(() => {
    if (!hasBootstrapped || !isAuthenticated) return;

    const interval = setInterval(() => {
      const hasPending = recordingsRef.current.some((recording) => !['ANALYZED', 'FAILED'].includes(recording.status));
      if (hasPending) {
        void loadRecordings();
      }
    }, 8000);

    return () => clearInterval(interval);
  }, [hasBootstrapped, isAuthenticated]);

  async function loadData() {
    setLoading(true);
    try {
      const [ovRes, recRes, trendRes] = await Promise.all([
        analyticsApi.overview(30),
        recordingsApi.list(1, 10),
        analyticsApi.sentiment(30),
      ]);
      setOverview(ovRes.data);
      setRecordings(Array.isArray(recRes.data?.items) ? recRes.data.items : []);
      setTrend(Array.isArray(trendRes.data) ? trendRes.data : []);
    } catch (e) {
      toast.error(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadRecordings() {
    try {
      const res = await recordingsApi.list(1, 10);
      setRecordings(Array.isArray(res.data?.items) ? res.data.items : []);
    } catch {}
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this recording and all analysis data?')) return;
    try {
      await recordingsApi.delete(id);
      toast.success('Recording deleted');
      loadData();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  }

  const pieData = overview ? [
    { name: 'Positive', value: overview.positive_sessions },
    { name: 'Negative', value: overview.negative_sessions },
    { name: 'Neutral',  value: overview.neutral_sessions },
  ] : [];

  const sentimentScore = overview?.avg_sentiment_score ?? 0;
  const SentimentIcon = sentimentScore > 0.6 ? TrendingUp : sentimentScore < 0.4 ? TrendingDown : Minus;
  const sentimentColor = sentimentScore > 0.6 ? 'text-emerald-400' : sentimentScore < 0.4 ? 'text-red-400' : 'text-slate-400';

  return (
    <AppLayout>
      <div className="space-y-6 animate-fade-up">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Intelligence Dashboard</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Last 30 days · Real-time updates
              {isGuestSession ? ' · Local guest workspace' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadData} className="btn-ghost text-sm">
              <RefreshCw className="w-4 h-4" /> Refresh
            </button>
            <Link href="/upload" className="btn-primary text-sm">
              <Upload className="w-4 h-4" /> Upload Recording
            </Link>
          </div>
        </div>

        {/* KPI Cards */}
        {loading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="metric-card h-28 shimmer" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              label="Total Recordings"
              value={overview?.total_recordings ?? 0}
              icon={<Mic2 className="w-5 h-5 text-indigo-400" />}
              sub={`${overview?.analyzed_recordings ?? 0} analyzed`}
            />
            <MetricCard
              label="Avg Sentiment"
              value={`${Math.round(sentimentScore * 100)}%`}
              icon={<SentimentIcon className={clsx('w-5 h-5', sentimentColor)} />}
              sub="Positive bias score"
              valueColor={sentimentColor}
            />
            <MetricCard
              label="Audio Processed"
              value={`${overview?.total_duration_minutes?.toFixed(0) ?? 0}m`}
              icon={<Clock className="w-5 h-5 text-blue-400" />}
              sub="Total analyzed"
            />
            <MetricCard
              label="Need Review"
              value={overview?.reviews_needed ?? 0}
              icon={<AlertCircle className="w-5 h-5 text-amber-400" />}
              sub="Low confidence flags"
              valueColor={overview?.reviews_needed ? 'text-amber-400' : undefined}
            />
          </div>
        )}

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Sentiment Trend */}
          <div className="lg:col-span-2 glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Sentiment Trend (30 days)</h3>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={trend} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gPos" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gNeg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: 'rgba(20,23,32,0.95)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', fontSize: 12 }} />
                <Area type="monotone" dataKey="positive" stroke="#10b981" strokeWidth={2} fill="url(#gPos)" name="Positive" />
                <Area type="monotone" dataKey="negative" stroke="#ef4444" strokeWidth={2} fill="url(#gNeg)" name="Negative" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Pie Chart */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Sentiment Distribution</h3>
            {pieData.every(d => d.value === 0) ? (
              <div className="flex items-center justify-center h-40 text-slate-600 text-sm">No data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={72} paddingAngle={3} dataKey="value">
                    {pieData.map((_, i) => <Cell key={i} fill={SENTIMENT_COLORS[i]} />)}
                  </Pie>
                  <Legend iconType="circle" iconSize={8} formatter={(v) => <span style={{ color: '#94a3b8', fontSize: 12 }}>{v}</span>} />
                  <Tooltip contentStyle={{ background: 'rgba(20,23,32,0.95)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Recent Recordings Table */}
        <div className="glass-card overflow-hidden">
          <div className="flex items-center justify-between p-5 border-b border-white/5">
            <h3 className="text-sm font-semibold text-white">Recent Recordings</h3>
            <Link href="/recordings" className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">View all →</Link>
          </div>
          {recordings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-4">
                <Upload className="w-6 h-6 text-indigo-400" />
              </div>
              <p className="text-sm font-medium text-white mb-1">No recordings yet</p>
              <p className="text-sm text-slate-500 mb-5">Upload your first audio or video feedback file</p>
              <Link href="/upload" className="btn-primary text-sm">Upload now</Link>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {recordings.map((rec) => {
                const cfg = STATUS_CONFIG[rec.status] ?? STATUS_CONFIG.PENDING;
                return (
                  <div key={rec.id} className="flex items-center gap-4 px-5 py-4 hover:bg-white/2 transition-colors group">
                    <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/15 flex items-center justify-center flex-shrink-0">
                      <Mic2 className="w-4 h-4 text-indigo-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white truncate">{rec.original_filename}</span>
                        <span className={clsx('badge', cfg.color)}>
                          <span className={clsx('w-1.5 h-1.5 rounded-full', cfg.dot)} />
                          {cfg.label}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {rec.duration_seconds ? `${Math.round(rec.duration_seconds)}s · ` : ''}
                        {formatRelativeTime(rec.created_at)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Link href={`/recording/${rec.id}`} className="btn-ghost text-xs py-1.5 px-3">
                        <Eye className="w-3.5 h-3.5" /> Open
                      </Link>
                      <button onClick={() => handleDelete(rec.id)} className="text-slate-600 hover:text-red-400 transition-colors p-1.5">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}

function MetricCard({ label, value, icon, sub, valueColor }: {
  label: string; value: string | number; icon: React.ReactNode; sub?: string; valueColor?: string;
}) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs text-slate-500 font-medium">{label}</span>
        <div className="w-8 h-8 rounded-lg bg-white/4 flex items-center justify-center">{icon}</div>
      </div>
      <div className={clsx('text-3xl font-black tracking-tight mb-1', valueColor ?? 'text-white')}>{value}</div>
      {sub && <div className="text-xs text-slate-600">{sub}</div>}
    </div>
  );
}
