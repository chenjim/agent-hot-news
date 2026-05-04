import useSWR, { mutate as globalMutate } from 'swr';
import type { HotEvent, HotEventDetail, Category, Source, AdminStats, TaskLog, SourceFormData } from '@/types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:51180/api/v1';

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

async function postJson<T>(url: string, data?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

async function putJson<T>(url: string, data: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

async function deleteJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export function useHotEvents(category: Category = 'all', limit: number = 30) {
  const params = new URLSearchParams();
  if (category !== 'all') params.set('category', category);
  params.set('limit', String(limit));

  const { data, error, isLoading, mutate } = useSWR<HotEvent[]>(
    `${API_BASE}/hot-events?${params.toString()}`,
    fetcher,
    { refreshInterval: 60000, refreshWhenHidden: false }
  );

  return { events: data || [], error, isLoading, mutate };
}

export function useHotEventDetail(id: number | null) {
  const { data, error, isLoading } = useSWR<HotEventDetail>(
    id ? `${API_BASE}/hot-events/${id}` : null,
    fetcher
  );

  return { event: data, error, isLoading };
}

// Admin hooks
export function useAdminStats() {
  const { data, error, isLoading, mutate } = useSWR<AdminStats>(
    `${API_BASE}/admin/stats`,
    fetcher,
    { refreshInterval: 30000, refreshWhenHidden: false }
  );
  return { stats: data, error, isLoading, mutate };
}

export function useSources() {
  const { data, error, isLoading, mutate } = useSWR<Source[]>(
    `${API_BASE}/sources`,
    fetcher,
    { refreshInterval: 30000, refreshWhenHidden: false }
  );
  return { sources: data || [], error, isLoading, mutate };
}

export function useTaskLogs() {
  const { data, error, isLoading, mutate } = useSWR<TaskLog[]>(
    `${API_BASE}/admin/logs`,
    fetcher,
    { refreshInterval: 10000, refreshWhenHidden: false }
  );
  return { logs: data || [], error, isLoading, mutate };
}

export async function createSource(data: SourceFormData): Promise<Source> {
  return postJson<Source>(`${API_BASE}/sources`, data);
}

export async function updateSource(id: number, data: SourceFormData): Promise<Source> {
  return putJson<Source>(`${API_BASE}/sources/${id}`, data);
}

export async function deleteSource(id: number): Promise<unknown> {
  return deleteJson<unknown>(`${API_BASE}/sources/${id}`);
}

export async function triggerFetch(): Promise<unknown> {
  return postJson<unknown>(`${API_BASE}/admin/trigger-fetch`);
}

export async function triggerAI(): Promise<unknown> {
  return postJson<unknown>(`${API_BASE}/admin/trigger-ai`);
}

export async function triggerSourceFetch(id: number): Promise<unknown> {
  return postJson<unknown>(`${API_BASE}/sources/${id}/fetch`);
}

export { globalMutate };
