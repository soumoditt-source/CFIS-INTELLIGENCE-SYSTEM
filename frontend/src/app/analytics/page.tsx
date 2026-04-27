'use client';

import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, Cell, PieChart, Pie, Legend
} from 'recharts';
import AppLayout from '@/components/AppLayout';
import { analyticsApi, getErrorMessage } from '@/lib/api';
import toast from 'react-hot-toast';
import { TrendingUp, Package, Target, Brain, RefreshCw } from 'lucide-react';
import clsx from 'clsx';

const DAYS_OPTIONS = [7, 14, 30, 90];

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [overview, setOverview] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [intents, setIntents] = useState<any[]>([]);
  const [behavioral, setBehavioral] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, [days]);

  async function loadData() {
    setLoading(true);
    try {
      const [ov, prod, int_, beh] = await Promise.all([
        analyticsApi.overview(days),
        analyticsApi.products(days),
        analyticsApi.intents(days),
        analyticsApi.behavioral(days),
      ]);
      setOverview(ov.data);
      setProducts(prod.data.slice(0, 8));
      setIntents(int_.data);
      setBehavioral(beh.data);
    } catch (e) {
      toast.error(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  const PIE_COLORS = ['#10b981','#ef4444','#6b7280','#f59e0b','#818cf8','#f472b6'];

  const radarData = behavioral ? [
    { subject: 'Satisfaction',  A: Math.round(behavioral.avg_satisfaction * 100) },
    { subject: 'Hesitation',    A: Math.round(behavioral.avg_hesitation * 100) },
    { subject: 'Frustration',   A: Math.round(behavioral.avg_frustration * 100) },
  ] : [];

  return (
    <AppLayout>
      <div className="space-y-6 animate-fade-up">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Analytics</h1>
            <p className="text-sm text-slate-500 mt-0.5">Company-wide intelligence aggregates</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex rounded-xl overflow-hidden border border-white/8">
              {DAYS_OPTIONS.map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={clsx('px-3 py-2 text-xs font-medium transition-colors',
                    days === d ? 'bg-indigo-500/20 text-indigo-300' : 'text-slate-500 hover:text-slate-300'
                  )}
                >
                  {d}d
                </button>
              ))}
            </div>
            <button onClick={loadData} className="btn-ghost p-2.5"><RefreshCw className="w-4 h-4" /></button>
          </div>
        </div>

        {/* Overview Row */}
        {overview && !loading && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label:'Total Sessions', value: overview.total_recordings, icon: <TrendingUp className="w-4 h-4 text-indigo-400" /> },
              { label:'Analyzed', value: overview.analyzed_recordings, icon: <Brain className="w-4 h-4 text-purple-400" /> },
              { label:'Positive Ratio', value: `${overview.analyzed_recordings > 0 ? Math.round((overview.positive_sessions / overview.analyzed_recordings) * 100) : 0}%`, icon: <TrendingUp className="w-4 h-4 text-emerald-400" /> },
              { label:'Audio Hours', value: `${(overview.total_duration_minutes/60).toFixed(1)}h`, icon: <Target className="w-4 h-4 text-blue-400" /> },
            ].map((m) => (
              <div key={m.label} className="metric-card">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-500">{m.label}</span>
                  <div className="w-7 h-7 rounded-lg bg-white/4 flex items-center justify-center">{m.icon}</div>
                </div>
                <div className="text-3xl font-black text-white">{m.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Charts Row 1 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Product Sentiment Chart */}
          <div className="glass-card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Package className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-semibold text-white">Product Sentiment</h3>
            </div>
            {products.length === 0 ? (
              <div className="flex items-center justify-center h-44 text-slate-600 text-sm">No product data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={products} layout="vertical" margin={{ left: 0, right: 20 }}>
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="product_name" tick={{ fontSize: 11, fill: '#94a3b8' }} tickLine={false} axisLine={false} width={90} />
                  <Tooltip contentStyle={{ background: 'rgba(20,23,32,0.95)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', fontSize: 12 }} />
                  <Bar dataKey="positive_mentions" fill="#10b981" name="Positive" radius={[0,4,4,0]} />
                  <Bar dataKey="negative_mentions" fill="#ef4444" name="Negative" radius={[0,4,4,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Intent Distribution Pie */}
          <div className="glass-card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Target className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-semibold text-white">Customer Intent</h3>
            </div>
            {intents.length === 0 ? (
              <div className="flex items-center justify-center h-44 text-slate-600 text-sm">No intent data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={intents} dataKey="count" nameKey="intent" cx="45%" cy="50%" outerRadius={75} paddingAngle={2}>
                    {intents.map((_: any, i: number) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Legend
                    formatter={(v) => <span style={{ color:'#94a3b8', fontSize:11 }}>{v}</span>}
                    iconType="circle" iconSize={8}
                  />
                  <Tooltip contentStyle={{ background: 'rgba(20,23,32,0.95)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Behavioral Radar + Product Table */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Behavioral Radar */}
          <div className="glass-card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Brain className="w-4 h-4 text-purple-400" />
              <h3 className="text-sm font-semibold text-white">Behavioral Signals</h3>
              {behavioral && <span className="ml-auto text-xs text-slate-500">{behavioral.sample_size} sessions</span>}
            </div>
            {!behavioral || behavioral.sample_size === 0 ? (
              <div className="flex items-center justify-center h-44 text-slate-600 text-sm">No behavioral data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <RadarChart data={radarData} cx="50%" cy="50%" outerRadius={70}>
                  <PolarGrid stroke="rgba(255,255,255,0.06)" />
                  <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <Radar name="Avg" dataKey="A" stroke="#818cf8" fill="#818cf8" fillOpacity={0.2} strokeWidth={2} />
                  <Tooltip contentStyle={{ background: 'rgba(20,23,32,0.95)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', fontSize: 12 }} />
                </RadarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Top Products Table */}
          <div className="glass-card overflow-hidden">
            <div className="p-4 border-b border-white/5">
              <h3 className="text-sm font-semibold text-white">Top Products by Mentions</h3>
            </div>
            {products.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-slate-600 text-sm">No product data yet</div>
            ) : (
              <div className="divide-y divide-white/5">
                {products.slice(0,6).map((p: any, i: number) => (
                  <div key={p.product_name} className="flex items-center gap-3 px-4 py-3">
                    <span className="text-xs font-bold text-slate-600 w-4">{i+1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{p.product_name}</p>
                      <div className="progress-bar mt-1.5">
                        <div className="progress-fill" style={{ width: `${p.sentiment_ratio*100}%` }} />
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-semibold text-white">{p.total_mentions}</p>
                      <p className="text-xs text-emerald-400">{Math.round(p.sentiment_ratio*100)}% pos</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
