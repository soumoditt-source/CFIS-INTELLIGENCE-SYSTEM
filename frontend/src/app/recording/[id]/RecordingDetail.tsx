'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import {
  ArrowLeft,
  Download,
  RefreshCw,
  Loader2,
  AlertCircle,
  CheckCircle2,
  MessageSquare,
  Brain,
  ShoppingBag,
  User,
  Mic2,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Clock,
  BadgeInfo,
  Sparkles,
  Activity,
  Flag,
} from 'lucide-react';
import AppLayout from '@/components/AppLayout';
import { recordingsApi, reportsApi, getErrorMessage } from '@/lib/api';

const SPEAKER_COLORS = ['speaker-0', 'speaker-1', 'speaker-2', 'speaker-3', 'speaker-4'];

const STATUS_STEPS = [
  { key: 'AUDIO_PROCESSING', label: 'Audio Cleaning' },
  { key: 'TRANSCRIBING', label: 'Transcription' },
  { key: 'ANALYZING', label: 'AI Analysis' },
  { key: 'ANALYZED', label: 'Complete' },
];

const EMOTION_LABELS: Record<string, string> = {
  joy: 'Joy',
  anger: 'Anger',
  sadness: 'Sadness',
  fear: 'Fear',
  disgust: 'Disgust',
  surprise: 'Surprise',
  neutral: 'Neutral',
  frustration: 'Frustration',
  satisfaction: 'Satisfaction',
};

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) {
    return '0:00';
  }

  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatPct(value?: number | null) {
  return `${Math.round((value || 0) * 100)}%`;
}

function safeArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function SignalMeter({
  label,
  value,
  tone = 'indigo',
}: {
  label: string;
  value?: number | null;
  tone?: 'indigo' | 'emerald' | 'amber' | 'red';
}) {
  const percentage = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  const toneClass =
    tone === 'emerald'
      ? 'bg-emerald-500'
      : tone === 'amber'
        ? 'bg-amber-500'
        : tone === 'red'
          ? 'bg-red-500'
          : 'bg-indigo-500';

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500">{label}</span>
        <span className="text-white font-semibold">{percentage}%</span>
      </div>
      <div className="progress-bar">
        <div className={clsx('h-full rounded-full transition-all duration-500', toneClass)} style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

function InsightCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string | number; sub?: string }) {
  return (
    <div className="metric-card">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-lg bg-white/4 flex items-center justify-center">{icon}</div>
        <span className="text-xs text-slate-500">{label}</span>
      </div>
      <div className="text-base font-bold text-white capitalize truncate">{value}</div>
      {sub && <div className="text-xs text-slate-600 mt-0.5 capitalize">{sub}</div>}
    </div>
  );
}

function SectionCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-white/4 flex items-center justify-center">{icon}</div>
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      {children}
    </div>
  );
}

export default function RecordingDetail() {
  const params = useParams<{ id: string | string[] }>();
  const id = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const router = useRouter();

  const [recording, setRecording] = useState<any>(null);
  const [transcript, setTranscript] = useState<any>(null);
  const [insights, setInsights] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'insights' | 'transcript' | 'raw'>('insights');
  const [expandedSegments, setExpandedSegments] = useState<Set<number>>(new Set());
  const statusRef = useRef<string | null>(null);

  useEffect(() => {
    statusRef.current = recording?.status ?? null;
  }, [recording]);

  useEffect(() => {
    if (!id) return;
    void loadAll();
    const interval = setInterval(() => {
      if (!statusRef.current || !['ANALYZED', 'FAILED'].includes(statusRef.current)) {
        void loadAll();
      }
    }, 6000);
    return () => clearInterval(interval);
  }, [id]);

  async function loadAll() {
    try {
      const res = await recordingsApi.get(id as string);
      const nextRecording = res.data;
      setRecording(nextRecording);

      const requests: PromiseSettledResult<any>[] = await Promise.allSettled([
        nextRecording.transcript_ready ? recordingsApi.transcript(id as string) : Promise.resolve(null),
        nextRecording.insights_ready ? recordingsApi.insights(id as string) : Promise.resolve(null),
      ]);

      const transcriptResult = requests[0];
      const insightsResult = requests[1];

      if (transcriptResult.status === 'fulfilled' && transcriptResult.value) {
        setTranscript(transcriptResult.value.data);
      }
      if (insightsResult.status === 'fulfilled' && insightsResult.value) {
        setInsights(insightsResult.value.data);
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function downloadPdf() {
    try {
      const res = await reportsApi.pdf(id as string);
      const contentType = String(res.headers['content-type'] || 'application/pdf');
      const contentDisposition = String(res.headers['content-disposition'] || '');
      const fallbackExtension = contentType.includes('text/html') ? 'html' : 'pdf';
      const filenameMatch = /filename="?([^"]+)"?/i.exec(contentDisposition);
      const filename = filenameMatch?.[1] || `aegiscx-report-${(id as string).slice(0, 8)}.${fallbackExtension}`;
      const url = URL.createObjectURL(new Blob([res.data], { type: contentType }));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      if (contentType.includes('text/html')) {
        toast.success('HTML report downloaded. PDF runtime is unavailable in the current local environment.');
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  function handleBack() {
    if (window.history.length > 1) {
      router.back();
      return;
    }
    router.push('/recordings');
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-64 text-slate-500">
          <Loader2 className="w-6 h-6 animate-spin mr-3" /> Loading recording...
        </div>
      </AppLayout>
    );
  }

  const currentStep = STATUS_STEPS.findIndex((step) => step.key === recording?.status);
  const behavioralSignals = insights?.behavioral_signals || {};
  const fullAnalysis = insights?.full_analysis || {};
  const llmResult = fullAnalysis?.llm_result || {};
  const keyComplaints = safeArray<string>(fullAnalysis?.key_complaints || llmResult?.key_complaints);
  const keyPraises = safeArray<string>(fullAnalysis?.key_praises || llmResult?.key_praises);
  const emotionArc = safeArray<any>(insights?.emotion_arc);
  const productMentions = safeArray<any>(insights?.product_mentions);
  const transcriptSegments = safeArray<any>(transcript?.segments);
  const focusLabel =
    fullAnalysis?.conversation_overview?.top_focus ||
    productMentions[0]?.product_name ||
    fullAnalysis?.context?.product_category ||
    'General feedback';

  return (
    <AppLayout>
      <div className="space-y-5 animate-fade-up">
        <div className="flex flex-col lg:flex-row lg:items-start gap-4">
          <div className="flex items-start gap-4 flex-1 min-w-0">
            <button onClick={handleBack} className="btn-ghost p-2.5 mt-1">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex-1 min-w-0">
              <h1 className="text-lg lg:text-2xl font-bold text-white truncate">{recording?.original_filename}</h1>
              <div className="flex flex-wrap items-center gap-3 mt-2">
                {recording?.duration_seconds && (
                  <span className="flex items-center gap-1 text-xs text-slate-500">
                    <Clock className="w-3 h-3" /> {Math.round(recording.duration_seconds)}s
                  </span>
                )}
                <span className="badge badge-pending">{recording?.status?.replace(/_/g, ' ')}</span>
                {insights?.overall_sentiment && (
                  <span className={clsx(
                    insights.overall_sentiment === 'positive'
                      ? 'pill-positive'
                      : insights.overall_sentiment === 'negative'
                        ? 'pill-negative'
                        : insights.overall_sentiment === 'mixed'
                          ? 'pill-mixed'
                          : 'pill-neutral'
                  )}>
                    {insights.overall_sentiment}
                  </span>
                )}
                {insights?.requires_human_review && (
                  <span className="badge bg-amber-500/10 text-amber-400 border border-amber-500/25">
                    <AlertTriangle className="w-3 h-3" /> Review needed
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-3">
                {recording?.error_message || recording?.progress_message || 'Session loaded.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => void loadAll()} className="btn-ghost p-2.5">
              <RefreshCw className="w-4 h-4" />
            </button>
            {recording?.insights_ready && (
              <button onClick={downloadPdf} className="btn-primary text-sm">
                <Download className="w-4 h-4" /> Download Report
              </button>
            )}
          </div>
        </div>

        {recording?.status !== 'ANALYZED' && recording?.status !== 'FAILED' && (
          <div className="glass-card p-5">
            <div className="flex items-center gap-3 mb-4">
              <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
              <span className="text-sm font-medium text-white">Processing in progress...</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {STATUS_STEPS.map((step, index) => {
                const done = index < currentStep;
                const active = index === currentStep;
                return (
                  <div key={step.key} className="flex items-center gap-2">
                    <div
                      className={clsx(
                        'flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-all',
                        done
                          ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                          : active
                            ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 animate-pulse'
                            : 'bg-white/3 text-slate-600 border border-white/5'
                      )}
                    >
                      {done ? (
                        <CheckCircle2 className="w-3 h-3" />
                      ) : active ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <div className="w-3 h-3 rounded-full border border-current" />
                      )}
                      {step.label}
                    </div>
                    {index < STATUS_STEPS.length - 1 && <div className="w-4 h-px bg-white/10" />}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {recording?.status === 'FAILED' && (
          <div className="glass-card p-5 border border-red-500/20">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-400">Processing Failed</p>
                <p className="text-sm text-slate-500 mt-1">{recording.error_message || 'An unknown error occurred during processing.'}</p>
              </div>
            </div>
          </div>
        )}

        {insights && (
          <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
            <InsightCard icon={<Brain className="w-4 h-4 text-purple-400" />} label="Sentiment" value={formatPct(insights.sentiment_score)} sub={insights.overall_sentiment} />
            <InsightCard icon={<Sparkles className="w-4 h-4 text-blue-400" />} label="Emotion" value={EMOTION_LABELS[insights.dominant_emotion] || insights.dominant_emotion || 'Neutral'} sub="dominant tone" />
            <InsightCard icon={<Flag className="w-4 h-4 text-emerald-400" />} label="Intent" value={insights.customer_intent || 'General comment'} sub={`${formatPct(insights.intent_confidence)} confidence`} />
            <InsightCard icon={<ShoppingBag className="w-4 h-4 text-amber-400" />} label="Focus" value={focusLabel} sub={fullAnalysis?.context?.company_name || 'no extra company context'} />
            <InsightCard
              icon={<Mic2 className="w-4 h-4 text-indigo-400" />}
              label="Transcript"
              value={transcript?.num_speakers ?? '--'}
              sub={`${Number(transcript?.word_count || 0).toLocaleString()} words`}
            />
          </div>
        )}

        {(transcript || insights) && (
          <div className="glass-card overflow-hidden">
            <div className="flex flex-wrap border-b border-white/5">
              {[
                { key: 'insights', label: 'AI Insights', show: !!insights },
                { key: 'transcript', label: 'Transcript', show: !!transcript },
                { key: 'raw', label: 'Raw JSON', show: !!insights },
              ]
                .filter((tab) => tab.show)
                .map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key as 'insights' | 'transcript' | 'raw')}
                    className={clsx(
                      'px-5 py-3 text-sm font-medium transition-colors border-b-2 -mb-px',
                      activeTab === tab.key
                        ? 'text-indigo-400 border-indigo-500'
                        : 'text-slate-500 border-transparent hover:text-slate-300'
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
            </div>

            <div className="p-5">
              {activeTab === 'insights' && insights && (
                <div className="space-y-5">
                  <div className="p-4 rounded-xl bg-indigo-500/6 border border-indigo-500/15">
                    <p className="text-xs font-semibold text-indigo-400 mb-2 uppercase tracking-widest">Executive Summary</p>
                    <p className="text-sm text-slate-300 leading-relaxed">{insights.executive_summary}</p>
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    <SectionCard title="Conversation Overview" icon={<BadgeInfo className="w-4 h-4 text-indigo-400" />}>
                      <div className="space-y-3 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-slate-500">Analysis tier</span>
                          <span className="text-white font-medium">{insights.analysis_tier}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-slate-500">Primary focus</span>
                          <span className="text-white font-medium text-right">{focusLabel}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-slate-500">Confidence</span>
                          <span className="text-white font-medium">{formatPct(insights.confidence_score)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-slate-500">Human review</span>
                          <span className={insights.requires_human_review ? 'text-amber-400 font-medium' : 'text-emerald-400 font-medium'}>
                            {insights.requires_human_review ? 'Required' : 'Not required'}
                          </span>
                        </div>
                      </div>
                    </SectionCard>

                    <SectionCard title="Behavioral Signals" icon={<Activity className="w-4 h-4 text-purple-400" />}>
                      <div className="space-y-4">
                        <SignalMeter label="Satisfaction" value={behavioralSignals.satisfaction_level_score} tone="emerald" />
                        <SignalMeter label="Frustration" value={behavioralSignals.frustration_level_score} tone="red" />
                        <SignalMeter label="Hesitation" value={behavioralSignals.hesitation_level_score} tone="amber" />
                        <SignalMeter label="Overall stability" value={behavioralSignals.overall_behavioral_score} tone="indigo" />
                      </div>
                    </SectionCard>

                    <SectionCard title="Key Praises" icon={<Sparkles className="w-4 h-4 text-emerald-400" />}>
                      {keyPraises.length > 0 ? (
                        <div className="space-y-2">
                          {keyPraises.map((item: string, index: number) => (
                            <div key={index} className="rounded-xl border border-emerald-500/15 bg-emerald-500/5 p-3 text-sm text-slate-300">
                              {item}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-500">No clear praise segments were detected.</p>
                      )}
                    </SectionCard>

                    <SectionCard title="Key Complaints" icon={<AlertTriangle className="w-4 h-4 text-red-400" />}>
                      {keyComplaints.length > 0 ? (
                        <div className="space-y-2">
                          {keyComplaints.map((item: string, index: number) => (
                            <div key={index} className="rounded-xl border border-red-500/15 bg-red-500/5 p-3 text-sm text-slate-300">
                              {item}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-500">No major complaint segments were detected.</p>
                      )}
                    </SectionCard>
                  </div>

                  {productMentions.length > 0 && (
                    <SectionCard title="Products And Brand Mentions" icon={<ShoppingBag className="w-4 h-4 text-amber-400" />}>
                      <div className="space-y-3">
                        {productMentions.map((product: any, index: number) => (
                          <div key={`${product.product_name}-${index}`} className="rounded-xl border border-white/5 bg-white/3 p-4">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-semibold text-white">{product.product_name}</span>
                              <span className={clsx(
                                product.sentiment === 'positive'
                                  ? 'pill-positive'
                                  : product.sentiment === 'negative'
                                    ? 'pill-negative'
                                    : product.sentiment === 'mixed'
                                      ? 'pill-mixed'
                                      : 'pill-neutral'
                              )}>
                                {product.sentiment}
                              </span>
                              {product.aspect && <span className="badge badge-pending text-[10px]">{product.aspect}</span>}
                            </div>
                            {product.specific_feedback && <p className="text-sm text-slate-400 mt-3">{product.specific_feedback}</p>}
                          </div>
                        ))}
                      </div>
                    </SectionCard>
                  )}

                  {emotionArc.length > 0 && (
                    <SectionCard title="Emotion Arc" icon={<Brain className="w-4 h-4 text-blue-400" />}>
                      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                        {emotionArc.map((point: any) => (
                          <div key={point.segment_id} className="rounded-xl border border-white/5 bg-white/3 p-3">
                            <div className="text-xs text-slate-500">Segment {point.segment_index + 1}</div>
                            <div className="text-sm font-semibold text-white mt-1">{EMOTION_LABELS[point.emotion] || point.emotion}</div>
                            <div className="text-xs text-slate-500 mt-1 capitalize">{point.sentiment}</div>
                            <div className="text-xs text-indigo-300 mt-2">{formatPct(point.confidence)}</div>
                          </div>
                        ))}
                      </div>
                    </SectionCard>
                  )}
                </div>
              )}

              {activeTab === 'transcript' && transcript && (
                <div className="space-y-4">
                  <div className="rounded-xl border border-white/5 bg-white/3 p-4">
                    <p className="section-title mb-2">Verbatim Conversation</p>
                    <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                      {transcript.full_text || 'Transcript text is still being prepared.'}
                    </p>
                  </div>

                  <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
                    {transcriptSegments.map((segment: any, index: number) => {
                      const speakerIndex = parseInt(segment.speaker_label?.replace(/\D/g, '') || '0', 10) % SPEAKER_COLORS.length;
                      const isOpen = expandedSegments.has(index);
                      return (
                        <div key={index} className="transcript-segment">
                          <button
                            className="w-full flex items-start gap-3 text-left"
                            onClick={() => setExpandedSegments((current) => {
                              const next = new Set(current);
                              if (next.has(index)) next.delete(index);
                              else next.add(index);
                              return next;
                            })}
                          >
                            <div className="flex-shrink-0 text-xs font-mono text-slate-600 mt-0.5 w-16">
                              {formatTime(segment.start_time)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <span className={clsx('text-xs font-semibold mr-2', SPEAKER_COLORS[speakerIndex])}>
                                {segment.speaker_label || 'Speaker'}
                              </span>
                              <span className="text-sm text-slate-300">{segment.text}</span>
                            </div>
                            {isOpen ? (
                              <ChevronUp className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
                            )}
                          </button>
                          {isOpen && (
                            <div className="mt-2 ml-[4.75rem] text-xs text-slate-500 font-mono">
                              {formatTime(segment.start_time)} → {formatTime(segment.end_time)} · {segment.word_count} words
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {activeTab === 'raw' && insights && (
                <pre className="text-xs font-mono text-slate-400 bg-surface-100 rounded-xl p-4 overflow-auto max-h-[600px] leading-relaxed">
                  {JSON.stringify(insights.full_analysis, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
