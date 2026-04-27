'use client';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Mic2, Brain, BarChart3, Shield, Zap, Users, ChevronRight, Play, ArrowRight } from 'lucide-react';
import NeuralCoreBackground from '@/components/NeuralCoreBackground';

const FEATURES = [
  { icon: Mic2, title: 'Audio Intelligence', desc: 'WhisperX-powered transcription with speaker diarization and word-level timestamps. Handles GB-sized files.', color: 'from-indigo-500 to-purple-600' },
  { icon: Brain, title: 'Behavioral Analysis', desc: '9-dimensional NLP: sentiment, emotions, intent, hesitation patterns, frustration signals, and confidence scoring.', color: 'from-purple-500 to-pink-600' },
  { icon: BarChart3, title: 'Product Intelligence', desc: 'Extract product-level feedback, brand mentions, aspect-based sentiment — per feature, per product, at scale.', color: 'from-blue-500 to-cyan-600' },
  { icon: Shield, title: 'Bayesian Confidence', desc: 'Monte Carlo Dropout uncertainty quantification. Every prediction comes with a calibrated confidence score.', color: 'from-emerald-500 to-teal-600' },
  { icon: Zap, title: 'Hybrid ML + LLM', desc: 'Local ML first (fast, free). LLM refinement only when confidence is low. Up to 70% cost reduction vs pure API.', color: 'from-amber-500 to-orange-600' },
  { icon: Users, title: 'Customer Profiles', desc: 'Longitudinal cross-session memory. Build behavioural profiles. Cluster customers into intelligence segments.', color: 'from-rose-500 to-red-600' },
];

const STATS = [
  { value: '90–97%', label: 'System Accuracy' },
  { value: '9x', label: 'Dimensions Extracted' },
  { value: '<3min', label: 'Processing per Session' },
  { value: '1GB+', label: 'Max File Support' },
];

const fade = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } };

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-5 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Shield className="w-4 h-4 text-white" />
          </div>
          <span className="text-lg font-bold tracking-tight text-white">CFIS</span>
          <span className="badge badge-pending text-[10px]">BETA</span>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/auth/login" className="btn-ghost text-sm">Sign In</Link>
          <Link href="/auth/register" className="btn-primary text-sm">Get Started <ChevronRight className="w-4 h-4" /></Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative z-10 max-w-6xl mx-auto px-8 pt-24 pb-20 text-center">
        <NeuralCoreBackground />
        <motion.div variants={fade} initial="hidden" animate="show" transition={{ duration: 0.6 }} className="relative z-10">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-sm font-medium mb-8">
            <Zap className="w-3.5 h-3.5" />
            Powered by Pytorch · Mistral · Gemini · GPT-4o
          </div>

          <h1 className="text-6xl md:text-7xl font-bold tracking-tight text-white mb-6">
            Customer Feedback <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">
              Intelligence System
            </span>
          </h1>

          <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            AegisCX transforms raw audio/video feedback recordings into deep behavioral insights —
            sentiment, emotion, product feedback, intent, and customer profiles. All in minutes.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/auth/register" className="btn-primary text-base px-8 py-4">
              Start Analyzing <ArrowRight className="w-5 h-5" />
            </Link>
            <Link href="/dashboard" className="btn-ghost text-base px-8 py-4">
              <Play className="w-4 h-4" /> View Demo
            </Link>
          </div>
        </motion.div>

        {/* Stats row */}
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-20"
          variants={{ show: { transition: { staggerChildren: 0.1 } } }}
          initial="hidden"
          animate="show"
        >
          {STATS.map((s) => (
            <motion.div key={s.label} variants={fade} className="glass-card p-5">
              <div className="text-3xl font-black text-white mb-1">{s.value}</div>
              <div className="text-sm text-slate-500">{s.label}</div>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* Pipeline Diagram */}
      <section className="relative z-10 max-w-5xl mx-auto px-8 py-16">
        <div className="text-center mb-12">
          <p className="section-title mb-3">How It Works</p>
          <h2 className="text-3xl font-bold text-white">End-to-End Intelligence Pipeline</h2>
        </div>
        <div className="flex flex-col md:flex-row items-center justify-center gap-3">
          {['Upload Audio', 'FFmpeg Clean', 'WhisperX STT', 'NLP Analysis', 'LLM Insights', 'Dashboard'].map((step, i) => (
            <div key={step} className="flex items-center gap-3">
              <div className="glass-card px-4 py-3 text-sm font-semibold text-white whitespace-nowrap">
                <span className="text-indigo-400 mr-2 font-mono text-xs">{i + 1}</span>
                {step}
              </div>
              {i < 5 && <ChevronRight className="w-4 h-4 text-slate-600 hidden md:block flex-shrink-0" />}
            </div>
          ))}
        </div>
      </section>

      {/* Features Grid */}
      <section className="relative z-10 max-w-6xl mx-auto px-8 py-16">
        <div className="text-center mb-12">
          <p className="section-title mb-3">Capabilities</p>
          <h2 className="text-3xl font-bold text-white">Built Different</h2>
          <p className="text-slate-400 mt-3 max-w-xl mx-auto">Not another meeting transcription tool. AegisCX goes 9 layers deep into every conversation.</p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              className="glass-card-hover p-6"
              variants={fade}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
            >
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${f.color} flex items-center justify-center mb-4`}>
                <f.icon className="w-5 h-5 text-white" />
              </div>
              <h3 className="text-base font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 max-w-3xl mx-auto px-8 py-24 text-center">
        <div className="glass-card p-12 relative overflow-hidden">
          <div className="orb w-64 h-64 bg-indigo-600/20 -top-20 -right-20" />
          <div className="orb w-48 h-48 bg-purple-600/15 -bottom-10 -left-10" />
          <div className="relative z-10">
            <h2 className="text-4xl font-black text-white mb-4">Ready to start?</h2>
            <p className="text-slate-400 mb-8">Upload your first recording and get insights in under 3 minutes.</p>
            <Link href="/auth/register" className="btn-primary text-base px-10 py-4">
              Create Free Account <ArrowRight className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 py-8 text-center text-sm text-slate-600">
        © 2026 AegisCX · Enterprise Customer Intelligence Platform · Built with WhisperX, FastAPI, Next.js
      </footer>
    </div>
  );
}
