'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle, RefreshCw, LayoutDashboard } from 'lucide-react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('AegisCX route error', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="glass-card max-w-xl w-full p-8 text-center">
        <div className="w-14 h-14 rounded-2xl mx-auto mb-5 bg-red-500/10 border border-red-500/20 flex items-center justify-center">
          <AlertTriangle className="w-6 h-6 text-red-400" />
        </div>
        <h1 className="text-2xl font-bold text-white">Something went wrong on this page</h1>
        <p className="text-sm text-slate-400 mt-3 leading-relaxed">
          The page hit a client-side error. Your data is still safe, and we can recover from here without restarting the whole workflow.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-6">
          <button onClick={reset} className="btn-primary text-sm">
            <RefreshCw className="w-4 h-4" /> Try Again
          </button>
          <Link href="/dashboard" className="btn-ghost text-sm">
            <LayoutDashboard className="w-4 h-4" /> Open Dashboard
          </Link>
        </div>

        {error?.digest && <p className="text-xs text-slate-600 mt-5">Ref: {error.digest}</p>}
      </div>
    </div>
  );
}
