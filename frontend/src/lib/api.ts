/**
 * AegisCX API client
 *
 * Keeps auth handling in one place, adds light retry behavior for reads,
 * and returns friendlier messages when slow networks or long-running
 * processing make the app feel unstable.
 */

import axios, { AxiosError, AxiosResponse } from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
const DEFAULT_TIMEOUT_MS = 75_000;

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: DEFAULT_TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
});

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriableAxiosError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) {
    return false;
  }

  if (!error.response) {
    return true;
  }

  return [408, 425, 429, 500, 502, 503, 504].includes(error.response.status);
}

async function withRetry<T>(
  task: () => Promise<T>,
  options?: { attempts?: number; baseDelayMs?: number },
): Promise<T> {
  const attempts = options?.attempts ?? 2;
  const baseDelayMs = options?.baseDelayMs ?? 1_000;

  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await task();
    } catch (error) {
      lastError = error;

      if (attempt >= attempts || !isRetriableAxiosError(error)) {
        throw error;
      }

      await sleep(baseDelayMs * attempt);
    }
  }

  throw lastError;
}

function createUploadId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
}

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => Promise.reject(error),
);

export const authApi = {
  register: (data: { email: string; name: string; password: string; company_name?: string }) =>
    api.post('/auth/register', data),

  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data),

  me: () => withRetry(() => api.get('/auth/me'), { attempts: 2 }),
};

export const recordingsApi = {
  upload: async (
    file: File,
    meta?: { company_name?: string; product_category?: string; num_speakers?: number },
    onProgress?: (pct: number) => void,
  ) => {
    const uploadId = createUploadId();
    const chunkSizeBytes = 1 * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / chunkSizeBytes);

    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
      const start = chunkIndex * chunkSizeBytes;
      const end = Math.min(start + chunkSizeBytes, file.size);
      const chunk = file.slice(start, end);

      const form = new FormData();
      form.append('upload_id', uploadId);
      form.append('chunk_index', String(chunkIndex));
      form.append('total_chunks', String(totalChunks));
      form.append('file', chunk, `chunk_${chunkIndex}`);

      await withRetry(
        () =>
          api.post('/recordings/upload/chunk', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 90_000,
          }),
        { attempts: 3, baseDelayMs: 1_500 },
      );

      if (onProgress) {
        onProgress(Math.round(((chunkIndex + 1) / totalChunks) * 90));
      }
    }

    if (onProgress) {
      onProgress(95);
    }

    const response = await withRetry(
      () =>
        api.post(
          '/recordings/upload/finalize',
          {
            upload_id: uploadId,
            filename: file.name,
            company_name: meta?.company_name,
            product_category: meta?.product_category,
            num_speakers: meta?.num_speakers,
          },
          { timeout: 180_000 },
        ),
      { attempts: 2, baseDelayMs: 2_000 },
    );

    if (onProgress) {
      onProgress(100);
    }

    return response;
  },

  list: (page = 1, per_page = 20, status?: string) =>
    withRetry(
      () => api.get('/recordings/', { params: { page, per_page, status_filter: status } }),
      { attempts: 3, baseDelayMs: 900 },
    ),

  get: (id: string) =>
    withRetry(() => api.get(`/recordings/${id}`), { attempts: 3, baseDelayMs: 900 }),

  status: (id: string) =>
    withRetry(() => api.get(`/recordings/${id}/status`), { attempts: 3, baseDelayMs: 900 }),

  transcript: (id: string) =>
    withRetry(() => api.get(`/recordings/${id}/transcript`), { attempts: 3, baseDelayMs: 900 }),

  insights: (id: string) =>
    withRetry(() => api.get(`/recordings/${id}/insights`), { attempts: 3, baseDelayMs: 900 }),

  delete: (id: string) => api.delete(`/recordings/${id}`),
};

export const analyticsApi = {
  overview: (days = 30) =>
    withRetry(() => api.get('/analytics/overview', { params: { days } }), { attempts: 3 }),

  sentiment: (days = 30) =>
    withRetry(() => api.get('/analytics/sentiment', { params: { days } }), { attempts: 3 }),

  products: (days = 30) =>
    withRetry(() => api.get('/analytics/products', { params: { days } }), { attempts: 3 }),

  intents: (days = 30) =>
    withRetry(() => api.get('/analytics/intents', { params: { days } }), { attempts: 3 }),

  behavioral: (days = 30) =>
    withRetry(() => api.get('/analytics/behavioral', { params: { days } }), { attempts: 3 }),

  analyzeText: (text: string, company_name?: string, product_category?: string) =>
    api.post('/analytics/analyze_text', { text, company_name, product_category }, { timeout: 120_000 }),
};

export const reportsApi = {
  json: (id: string) =>
    withRetry(() => api.get(`/reports/${id}/json`, { timeout: 120_000 }), { attempts: 3 }),

  pdf: (id: string) =>
    withRetry(
      () => api.get(`/reports/${id}/pdf`, { responseType: 'blob', timeout: 120_000 }),
      { attempts: 2, baseDelayMs: 1_500 },
    ),
};

export const adminApi = {
  jobs: (page = 1, status?: string) =>
    withRetry(() => api.get('/admin/jobs', { params: { page, status_filter: status } }), { attempts: 3 }),

  submitCorrection: (data: {
    insight_id: string;
    field_name: string;
    original_value: object;
    corrected_value: object;
    reason?: string;
  }) => api.post('/admin/corrections', data),
};

export const healthApi = {
  check: () => withRetry(() => api.get('/health'), { attempts: 2 }),
};

export type ApiError = { detail: string | { msg: string }[] };

function extractValidationMessage(detail: { msg: string }[]): string {
  return detail.map((item) => item.msg).join(', ');
}

function extractAxiosMessage(error: AxiosError<ApiError>): string {
  const response = error.response;

  if (!response) {
    if (error.code === 'ECONNABORTED') {
      return 'The request took too long. Slow network or server processing may still be in progress. Please wait a moment and try again.';
    }

    return 'Could not reach the server. Your upload or analysis may still be processing. Please retry in a moment.';
  }

  const detail = response.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return extractValidationMessage(detail);
  }

  if (response.status === 401) {
    return 'Your session is no longer valid. Please sign in again or continue in local guest mode.';
  }

  if (response.status === 404) {
    return 'The requested item was not found. It may still be processing or may have been removed.';
  }

  if (response.status === 413) {
    return 'The selected file is too large for the current upload settings.';
  }

  if (response.status === 422) {
    return 'The request payload was incomplete or invalid. Please review the form and try again.';
  }

  if (response.status >= 500) {
    return 'The server hit an unexpected error while processing the request. Please retry shortly.';
  }

  return error.message || 'An unexpected API error occurred.';
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiError>(error)) {
    return extractAxiosMessage(error);
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'An unexpected error occurred.';
}

export type ApiResponse<T> = Promise<AxiosResponse<T>>;
