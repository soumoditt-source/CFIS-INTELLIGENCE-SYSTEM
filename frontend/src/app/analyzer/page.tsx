'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText, Send, Loader2, AlertTriangle, Brain, Zap,
  ChevronDown, ChevronUp, User, MessageSquare, Activity,
  Building2, Tag
} from 'lucide-react';
import AppLayout from '@/components/AppLayout';
import { analyticsApi, getErrorMessage } from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────
interface GlobalMetrics {
  customer_satisfaction: number;
  agent_empathy: number;
  issue_resolution_efficiency: number;
  product_sentiment: number;
  brand_trust: number;
  communication_clarity: number;
  overall_experience: number;
}

interface SegmentParams {
  sentiment: string;
  emotion: string;
  intent: string;
  hesitation_level: number;
  frustration_level: number;
  satisfaction_level: number;
  sarcasm_probability: number;
  urgency_level: number;
  empathy_required: boolean;
  resolution_status: string;
  brand_loyalty_signal: string;
  purchase_intent: boolean;
  churn_risk_score: number;
  upsell_opportunity: boolean;
  competitor_comparison: string;
  actionability: string;
  feature_request_detected: boolean;
  bug_report_detected: boolean;
  demographic_signal: string;
  conflict_level: number;
}

interface Segment {
  segment_index: number;
  speaker: string;
  timestamp: string;
  twenty_parameters: SegmentParams;
  reasoning: string;
}

interface AnalysisResult {
  session_id: string;
  executive_summary: string;
  global_metrics_7_scale: GlobalMetrics;
  segment_by_segment_analysis: Segment[];
  model_used: string;
  latency_ms: number;
}

function safeSegments(value: Segment[] | null | undefined): Segment[] {
  return Array.isArray(value) ? value : [];
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const METRIC_LABELS: Record<keyof GlobalMetrics, string> = {
  customer_satisfaction: 'Customer Satisfaction',
  agent_empathy: 'Agent Empathy',
  issue_resolution_efficiency: 'Resolution Efficiency',
  product_sentiment: 'Product Sentiment',
  brand_trust: 'Brand Trust',
  communication_clarity: 'Communication Clarity',
  overall_experience: 'Overall Experience',
};

const METRIC_COLORS = [
  'from-indigo-500 to-purple-500',
  'from-pink-500 to-rose-500',
  'from-emerald-500 to-teal-500',
  'from-amber-500 to-orange-500',
  'from-blue-500 to-cyan-500',
  'from-violet-500 to-purple-500',
  'from-green-500 to-emerald-500',
];

function ScoreBar({ value, colorClass }: { value: number; colorClass: string }) {
  const pct = Math.min(Math.max(value, 0), 10) * 10;
  return (
    <div className="h-2 rounded-full bg-surface-100 overflow-hidden">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.9, ease: 'easeOut' }}
        className={`h-full rounded-full bg-gradient-to-r ${colorClass}`}
      />
    </div>
  );
}

function SentimentBadge({ value }: { value: string }) {
  const map: Record<string, string> = {
    positive: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    negative: 'bg-red-500/15 text-red-400 border-red-500/30',
    neutral:  'bg-slate-500/15 text-slate-400 border-slate-500/30',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border capitalize ${map[value?.toLowerCase()] ?? map.neutral}`}>
      {value}
    </span>
  );
}

function SegmentCard({ seg, index }: { seg: Segment; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const p = seg.twenty_parameters;

  const riskColor = p.churn_risk_score >= 0.7 ? 'text-red-400' : p.churn_risk_score >= 0.4 ? 'text-amber-400' : 'text-emerald-400';

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="bg-surface-100 border border-white/5 rounded-xl overflow-hidden"
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/3 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-full bg-indigo-500/20 flex items-center justify-center border border-indigo-500/30">
            {seg.speaker.toLowerCase().includes('agent') ? (
              <User className="w-3.5 h-3.5 text-indigo-400" />
            ) : (
              <MessageSquare className="w-3.5 h-3.5 text-purple-400" />
            )}
          </div>
          <div className="text-left">
            <div className="text-sm font-medium text-white">{seg.speaker}</div>
            <div className="text-xs text-slate-500">{seg.timestamp}</div>
          </div>
          <SentimentBadge value={p.sentiment} />
          <span className="text-xs text-slate-500 capitalize border border-white/5 px-2 py-0.5 rounded-full">
            {p.emotion}
          </span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-4 border-t border-white/5 pt-4">
              {/* Core Scores */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: 'Hesitation', val: p.hesitation_level, danger: true },
                  { label: 'Frustration', val: p.frustration_level, danger: true },
                  { label: 'Satisfaction', val: p.satisfaction_level, danger: false },
                  { label: 'Urgency', val: p.urgency_level, danger: true },
                ].map(({ label, val, danger }) => (
                  <div key={label} className="bg-surface-50 p-3 rounded-lg border border-white/5">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
                    <div className={`text-lg font-bold ${danger && val >= 0.7 ? 'text-red-400' : 'text-white'}`}>
                      {((val ?? 0) * 10).toFixed(1)}
                    </div>
                    <div className="h-1 rounded-full bg-surface-100 mt-1 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${(val ?? 0) * 100}%` }}
                        transition={{ duration: 0.7 }}
                        className={`h-full rounded-full ${danger ? 'bg-red-500' : 'bg-emerald-500'}`}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Flags Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {[
                  { label: 'Churn Risk', val: `${((p.churn_risk_score ?? 0) * 100).toFixed(0)}%`, color: riskColor },
                  { label: 'Intent', val: p.intent, color: 'text-indigo-400' },
                  { label: 'Actionability', val: p.actionability, color: 'text-amber-400' },
                  { label: 'Brand Loyalty', val: p.brand_loyalty_signal, color: 'text-blue-400' },
                  { label: 'Purchase Intent', val: p.purchase_intent ? 'Yes' : 'No', color: p.purchase_intent ? 'text-emerald-400' : 'text-slate-500' },
                  { label: 'Upsell Opp.', val: p.upsell_opportunity ? 'Yes' : 'No', color: p.upsell_opportunity ? 'text-emerald-400' : 'text-slate-500' },
                  { label: 'Feature Req.', val: p.feature_request_detected ? 'Yes' : 'No', color: p.feature_request_detected ? 'text-purple-400' : 'text-slate-500' },
                  { label: 'Bug Report', val: p.bug_report_detected ? 'Yes' : 'No', color: p.bug_report_detected ? 'text-red-400' : 'text-slate-500' },
                ].map(({ label, val, color }) => (
                  <div key={label} className="bg-surface-50 rounded-lg px-3 py-2 border border-white/5">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
                    <div className={`text-sm font-semibold capitalize ${color}`}>{val}</div>
                  </div>
                ))}
              </div>

              {/* Reasoning */}
              {seg.reasoning && (
                <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-lg p-3">
                  <div className="text-xs text-indigo-400 font-medium mb-1 uppercase tracking-wider">AI Reasoning</div>
                  <p className="text-sm text-slate-300 leading-relaxed">{seg.reasoning}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function AnalyzerPage() {
  const [text, setText] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [productCat, setProductCat] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');

  const handleAnalyze = async () => {
    if (!text.trim()) { setError('Please enter some feedback text to analyze.'); return; }
    setError('');
    setIsAnalyzing(true);
    setResult(null);
    try {
      const res = await analyticsApi.analyzeText(text, companyName || undefined, productCat || undefined);
      setResult(res.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const metrics = result?.global_metrics_7_scale
    ? (Object.entries(result.global_metrics_7_scale) as [keyof GlobalMetrics, number][])
    : [];
  const segments = safeSegments(result?.segment_by_segment_analysis);

  return (
    <AppLayout>
      <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <Brain className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Feedback Analyzer</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Paste any customer feedback — get full 7-scale intelligence + 20-parameter segment breakdown.
            </p>
          </div>
        </div>
        {result && (
          <div className="flex items-center gap-2 text-xs text-slate-500 bg-surface-50 border border-white/5 rounded-lg px-3 py-2">
            <Zap className="w-3 h-3" />
            <span>{result.model_used}</span>
            <span className="text-slate-600">-</span>
            <span>{Number(result.latency_ms || 0).toFixed(0)}ms</span>
          </div>
        )}
      </div>

      {/* Input Card */}
      <div className="bg-surface-50 border border-white/5 rounded-2xl p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="relative">
            <Building2 className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Company name (optional)"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full bg-surface-100 border border-white/5 rounded-xl pl-9 pr-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 text-sm transition-colors"
            />
          </div>
          <div className="relative">
            <Tag className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Product category (optional)"
              value={productCat}
              onChange={(e) => setProductCat(e.target.value)}
              className="w-full bg-surface-100 border border-white/5 rounded-xl pl-9 pr-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 text-sm transition-colors"
            />
          </div>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste customer feedback, call transcript, or any text here…"
          className="w-full h-44 bg-surface-100 border border-white/5 rounded-xl p-4 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 resize-none transition-colors text-sm leading-relaxed"
          disabled={isAnalyzing}
        />

        <div className="flex items-center justify-between">
          {error ? (
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          ) : (
            <div className="text-xs text-slate-600">{text.length > 0 ? `${text.length} characters` : 'Powered by Gemini Pro / GPT-4o'}</div>
          )}
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing || !text.trim()}
            className="btn-primary"
          >
            {isAnalyzing ? (
              <><Loader2 className="w-4 h-4 animate-spin" />Analyzing…</>
            ) : (
              <><Send className="w-4 h-4" />Analyze Feedback</>
            )}
          </button>
        </div>
      </div>

      {/* Results */}
      <AnimatePresence>
        {result && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-6"
          >
            {/* Executive Summary */}
            <div className="bg-surface-50 border border-indigo-500/20 rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider">Executive Summary</h2>
              </div>
              <p className="text-slate-200 leading-relaxed">{result.executive_summary}</p>
            </div>

            {/* 7-Scale Global Metrics */}
            <div className="bg-surface-50 border border-white/5 rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-5">
                <Activity className="w-4 h-4 text-purple-400" />
                <h2 className="text-sm font-semibold text-purple-400 uppercase tracking-wider">7-Scale Intelligence Dashboard</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {metrics.map(([key, value], i) => (
                  <div key={key} className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-slate-300">{METRIC_LABELS[key]}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-bold text-white">{value ?? 0}</span>
                        <span className="text-xs text-slate-500">/ 10</span>
                      </div>
                    </div>
                    <ScoreBar value={value ?? 0} colorClass={METRIC_COLORS[i % METRIC_COLORS.length]} />
                  </div>
                ))}
              </div>

              {/* Score Ring Summary */}
              <div className="mt-6 pt-6 border-t border-white/5 grid grid-cols-3 md:grid-cols-7 gap-3">
                {metrics.map(([key, value], i) => (
                  <div key={key} className="flex flex-col items-center gap-1">
                    <div
                      className={`w-12 h-12 rounded-full bg-gradient-to-br ${METRIC_COLORS[i]} flex items-center justify-center text-white font-bold text-sm shadow-lg`}
                      style={{ opacity: 0.6 + ((value ?? 0) / 10) * 0.4 }}
                    >
                      {value ?? 0}
                    </div>
                    <span className="text-[9px] text-slate-500 text-center leading-tight">
                      {METRIC_LABELS[key].split(' ')[0]}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Segment Analysis */}
            {segments.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-amber-400" />
                  <h2 className="text-sm font-semibold text-amber-400 uppercase tracking-wider">
                    Segment-by-Segment Analysis ({segments.length} segments)
                  </h2>
                </div>
                {segments.map((seg, i) => (
                  <SegmentCard key={seg.segment_index ?? i} seg={seg} index={i} />
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
      </div>
    </AppLayout>
  );
}
