'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0b0f] text-slate-100 flex items-center justify-center px-4">
        <div className="max-w-xl w-full rounded-2xl border border-white/10 bg-[#141720] p-8 text-center shadow-2xl">
          <h1 className="text-2xl font-bold">AegisCX hit a full-app error</h1>
          <p className="text-sm text-slate-400 mt-3 leading-relaxed">
            The interface failed while rendering. The backend can still be healthy, and the session can usually recover with a retry.
          </p>
          <div className="mt-6">
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center justify-center rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white"
            >
              Reload Interface
            </button>
          </div>
          {error?.digest && <p className="text-xs text-slate-600 mt-5">Ref: {error.digest}</p>}
        </div>
      </body>
    </html>
  );
}
