'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Eye, FileAudio2, RefreshCw, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import AppLayout from '@/components/AppLayout';
import { recordingsApi, getErrorMessage } from '@/lib/api';

interface RecordingItem {
  id: string;
  original_filename: string;
  status: string;
  duration_seconds?: number;
  file_size_bytes?: number;
  created_at: string;
  progress_message?: string;
  error_message?: string | null;
}

function formatRelativeTime(value?: string) {
  if (!value) return 'Unknown time';

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 'Unknown time';
  }

  return formatDistanceToNow(parsed, { addSuffix: true });
}

const STATUS_OPTIONS = ['ALL', 'PENDING', 'AUDIO_PROCESSING', 'TRANSCRIBING', 'ANALYZING', 'ANALYZED', 'FAILED'];

const STATUS_STYLES: Record<string, string> = {
  PENDING: 'badge badge-pending',
  AUDIO_PROCESSING: 'badge badge-processing',
  AUDIO_READY: 'badge badge-processing',
  TRANSCRIBING: 'badge badge-processing',
  TRANSCRIBED: 'badge badge-processing',
  ANALYZING: 'badge badge-processing',
  ANALYZED: 'badge badge-analyzed',
  FAILED: 'badge badge-failed',
};

function formatSize(bytes?: number) {
  if (!bytes) return 'Unknown size';
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export default function RecordingsPage() {
  const [items, setItems] = useState<RecordingItem[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void loadRecordings();
  }, [page, statusFilter]);

  async function loadRecordings() {
    setLoading(true);
    try {
      const response = await recordingsApi.list(
        page,
        20,
        statusFilter === 'ALL' ? undefined : statusFilter
      );
      setItems(Array.isArray(response.data?.items) ? response.data.items : []);
      setPages(Number.isFinite(response.data?.pages) ? response.data.pages : 1);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this recording and its intelligence report?')) return;
    try {
      await recordingsApi.delete(id);
      toast.success('Recording deleted');
      await loadRecordings();
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <AppLayout>
      <div className="space-y-6 animate-fade-up">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">Recording Library</h1>
            <p className="text-sm text-slate-500 mt-1">Track uploads, watch processing state, and open full intelligence reports.</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex rounded-xl overflow-hidden border border-white/8">
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option}
                  onClick={() => {
                    setStatusFilter(option);
                    setPage(1);
                  }}
                  className={clsx(
                    'px-3 py-2 text-xs font-medium transition-colors',
                    statusFilter === option ? 'bg-indigo-500/20 text-indigo-300' : 'text-slate-500 hover:text-slate-300'
                  )}
                >
                  {option === 'ALL' ? 'All' : option.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
            <button onClick={() => void loadRecordings()} className="btn-ghost text-sm">
              <RefreshCw className="w-4 h-4" /> Refresh
            </button>
          </div>
        </div>

        <div className="glass-card overflow-hidden">
          {loading ? (
            <div className="p-6 space-y-4">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="h-20 rounded-2xl shimmer" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mx-auto mb-4">
                <FileAudio2 className="w-6 h-6 text-indigo-400" />
              </div>
              <p className="text-white font-medium">No recordings found</p>
              <p className="text-sm text-slate-500 mt-2">Try a different status filter or upload a new session.</p>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {items.map((item) => (
                <div key={item.id} className="px-5 py-4 hover:bg-white/2 transition-colors">
                  <div className="flex flex-col xl:flex-row xl:items-center gap-4">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center flex-shrink-0">
                        <FileAudio2 className="w-4 h-4 text-indigo-400" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-white truncate">{item.original_filename}</span>
                          <span className={STATUS_STYLES[item.status] || 'badge badge-pending'}>
                            {item.status.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          {item.duration_seconds ? `${Math.round(item.duration_seconds)}s - ` : ''}
                          {formatSize(item.file_size_bytes)} - {formatRelativeTime(item.created_at)}
                        </p>
                        <p className="text-sm text-slate-400 mt-2">
                          {item.error_message || item.progress_message || 'Ready'}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 xl:justify-end">
                      <Link href={`/recording/${item.id}`} className="btn-ghost text-sm">
                        <Eye className="w-4 h-4" /> Open
                      </Link>
                      <button onClick={() => void handleDelete(item.id)} className="btn-danger text-sm">
                        <Trash2 className="w-4 h-4" /> Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={() => setPage((current) => Math.max(current - 1, 1))}
            disabled={page <= 1}
            className="btn-ghost text-sm disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-slate-500">Page {page} of {pages}</span>
          <button
            onClick={() => setPage((current) => Math.min(current + 1, pages))}
            disabled={page >= pages}
            className="btn-ghost text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </AppLayout>
  );
}
