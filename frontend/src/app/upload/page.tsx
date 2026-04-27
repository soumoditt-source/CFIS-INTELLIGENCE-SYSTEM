'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, X, CheckCircle2, AlertCircle,
  Loader2, Music2, Video, ChevronRight
} from 'lucide-react';
import AppLayout from '@/components/AppLayout';
import { recordingsApi, getErrorMessage } from '@/lib/api';
import toast from 'react-hot-toast';
import clsx from 'clsx';

const ACCEPTED = {
  'audio/*': ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'],
  'video/*': ['.mp4', '.webm', '.mpeg'],
};

const MAX_SIZE_GB = 1;
const MAX_SIZE_BYTES = MAX_SIZE_GB * 1024 ** 3;

interface UploadFile {
  file: File;
  id: string;
  progress: number;
  status: 'pending' | 'uploading' | 'success' | 'error';
  error?: string;
  recordingId?: string;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export default function UploadPage() {
  const router = useRouter();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [meta, setMeta] = useState({ company_name: '', product_category: '', num_speakers: '' });
  const [uploading, setUploading] = useState(false);

  const onDrop = useCallback((accepted: File[], rejected: any[]) => {
    rejected.forEach((r) => {
      const msg = r.errors[0]?.message || 'Invalid file';
      toast.error(msg);
    });

    const newFiles: UploadFile[] = accepted.map((f) => ({
      file: f,
      id: Math.random().toString(36).slice(2),
      progress: 0,
      status: 'pending',
    }));
    setFiles((prev) => [...prev, ...newFiles]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: MAX_SIZE_BYTES,
    multiple: true,
  });

  function removeFile(id: string) {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }

  async function handleUploadAll() {
    const pending = files.filter((f) => f.status === 'pending');
    if (!pending.length) return;

    setUploading(true);
    const metaPayload = {
      company_name:     meta.company_name     || undefined,
      product_category: meta.product_category || undefined,
      num_speakers:     meta.num_speakers ? parseInt(meta.num_speakers) : undefined,
    };

    for (const uf of pending) {
      setFiles((prev) => prev.map((f) => f.id === uf.id ? { ...f, status: 'uploading', progress: 0 } : f));
      try {
        const res = await recordingsApi.upload(uf.file, metaPayload, (pct) => {
          setFiles((prev) => prev.map((f) => f.id === uf.id ? { ...f, progress: pct } : f));
        });
        setFiles((prev) => prev.map((f) =>
          f.id === uf.id ? { ...f, status: 'success', progress: 100, recordingId: res.data.recording_id } : f
        ));
        toast.success(`"${uf.file.name}" uploaded successfully`);
      } catch (e) {
        const msg = getErrorMessage(e);
        setFiles((prev) => prev.map((f) => f.id === uf.id ? { ...f, status: 'error', error: msg } : f));
        toast.error(msg);
      }
    }
    setUploading(false);
  }

  const allDone  = files.length > 0 && files.every((f) => f.status === 'success');
  const hasPending = files.some((f) => f.status === 'pending');
  const firstCompletedRecording = files.find((f) => f.recordingId)?.recordingId;

  return (
    <AppLayout>
      <div className="max-w-3xl mx-auto space-y-6 animate-fade-up">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-white">Upload Recordings</h1>
          <p className="text-sm text-slate-500 mt-1">
            MP3, MP4, WAV, M4A, WEBM, OGG, FLAC - Up to 1GB per file
          </p>
        </div>

        {/* Drop Zone */}
        <div
          {...getRootProps()}
          className={clsx('dropzone p-16 text-center', isDragActive && 'dropzone-active')}
        >
          <input {...getInputProps()} id="file-dropzone" />
          <div className="flex flex-col items-center gap-4 pointer-events-none">
            <div className={clsx('w-16 h-16 rounded-2xl flex items-center justify-center transition-all',
              isDragActive ? 'bg-indigo-500/20 border border-indigo-500/40' : 'bg-white/4 border border-white/8'
            )}>
              <Upload className={clsx('w-7 h-7', isDragActive ? 'text-indigo-400' : 'text-slate-500')} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">
                {isDragActive ? 'Drop files here' : 'Drag & drop audio or video files'}
              </p>
              <p className="text-xs text-slate-500 mt-1">or <span className="text-indigo-400">browse</span> to choose files</p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {['.mp3', '.mp4', '.wav', '.m4a', '.webm', '.flac'].map((ext) => (
                <span key={ext} className="badge badge-pending text-[10px] font-mono">{ext}</span>
              ))}
            </div>
          </div>
        </div>

        {/* Metadata Form */}
        <div className="glass-card p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white">Analysis Context <span className="text-slate-600 font-normal">(optional but improves accuracy)</span></h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1.5">Company Name</label>
              <input
                id="company-name-input"
                type="text"
                placeholder="e.g. Dabur India"
                value={meta.company_name}
                onChange={(e) => setMeta((m) => ({ ...m, company_name: e.target.value }))}
                className="input-field py-2.5"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1.5">Product Category</label>
              <input
                id="product-category-input"
                type="text"
                placeholder="e.g. Health & Wellness"
                value={meta.product_category}
                onChange={(e) => setMeta((m) => ({ ...m, product_category: e.target.value }))}
                className="input-field py-2.5"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1.5">Number of Speakers</label>
              <input
                id="num-speakers-input"
                type="number"
                min="1"
                max="10"
                placeholder="auto-detect"
                value={meta.num_speakers}
                onChange={(e) => setMeta((m) => ({ ...m, num_speakers: e.target.value }))}
                className="input-field py-2.5"
              />
            </div>
          </div>
        </div>

        {/* File Queue */}
        <AnimatePresence>
          {files.map((uf) => (
            <motion.div
              key={uf.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="glass-card p-4"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-white/4 flex items-center justify-center flex-shrink-0">
                  {uf.file.type.startsWith('video') ? (
                    <Video className="w-5 h-5 text-purple-400" />
                  ) : (
                    <Music2 className="w-5 h-5 text-indigo-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-white truncate">{uf.file.name}</span>
                    <span className="text-xs text-slate-500 flex-shrink-0">{formatBytes(uf.file.size)}</span>
                    {uf.status === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />}
                    {uf.status === 'error'   && <AlertCircle  className="w-4 h-4 text-red-400 flex-shrink-0" />}
                    {uf.status === 'uploading' && <Loader2 className="w-4 h-4 text-indigo-400 animate-spin flex-shrink-0" />}
                  </div>
                  {uf.status === 'uploading' ? (
                    <div className="space-y-1">
                      <div className="progress-bar">
                        <div
                          className="progress-fill transition-all duration-300"
                          style={{ width: `${uf.progress}%` }}
                        />
                      </div>
                      <p className="text-xs text-indigo-400">
                        Uploading... {uf.progress}% - tuned for slower connections
                      </p>
                    </div>
                  ) : uf.status === 'error' ? (
                    <p className="text-xs text-red-400">{uf.error}</p>
                  ) : uf.status === 'success' ? (
                    <p className="text-xs text-emerald-400">
                      Upload complete. Server-side transcript and AI analysis are still running - Recording ID:{' '}
                      <span className="font-mono">{uf.recordingId?.slice(0, 8)}...</span>
                    </p>
                  ) : (
                    <p className="text-xs text-slate-500">Ready to upload</p>
                  )}
                </div>
                {uf.status === 'pending' && (
                  <button onClick={() => removeFile(uf.id)} className="text-slate-600 hover:text-red-400 transition-colors p-1 flex-shrink-0">
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Actions */}
        {files.length > 0 && (
          <div className="flex items-center justify-between">
            <button
              onClick={() => setFiles([])}
              className="btn-ghost text-sm text-slate-500"
              disabled={uploading}
            >
              Clear all
            </button>
            <div className="flex gap-3">
              {allDone && (
                <>
                  <div className="hidden lg:flex items-center px-3 text-xs text-slate-500">
                    Upload finished. Open a recording to watch transcript and insight generation continue live.
                  </div>
                  {firstCompletedRecording && (
                    <button onClick={() => router.push(`/recording/${firstCompletedRecording}`)} className="btn-ghost text-sm">
                      Track Processing <ChevronRight className="w-4 h-4" />
                    </button>
                  )}
                  <button onClick={() => router.push('/dashboard')} className="btn-ghost text-sm">
                    Go to Dashboard <ChevronRight className="w-4 h-4" />
                  </button>
                </>
              )}
              {hasPending && (
                <button
                  id="upload-submit-btn"
                  onClick={handleUploadAll}
                  disabled={uploading}
                  className="btn-primary text-sm"
                >
                  {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                  {uploading ? 'Uploading...' : `Upload ${files.filter(f => f.status === 'pending').length} file(s)`}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
