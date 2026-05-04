export interface HotEvent {
  id: number;
  title: string;
  summary: string | null;
  category: string | null;
  hot_score: number;
  trend: 'up' | 'down' | 'stable';
  sentiment: string | null;
  entities: string[] | null;
  articles_count: number;
  sources_count: number;
  first_seen_at: string | null;
  last_updated_at: string | null;
  cover_image: string | null;
  trend_data?: number[] | null;
}

export interface HotEventDetail extends HotEvent {
  timeline: TimelineItem[];
  sources: SourceItem[];
  related_events: RelatedEvent[];
}

export interface TimelineItem {
  time: string | null;
  source: string;
  title: string;
}

export interface SourceItem {
  name: string;
  url: string;
  title: string;
  hot_score: number;
}

export interface RelatedEvent {
  id: number;
  title: string;
}

export type Category = 'all' | 'tech' | 'finance' | 'social' | 'global' | 'other';

export const CATEGORY_LABELS: Record<Category, string> = {
  all: '全部',
  tech: '科技',
  finance: '财经',
  social: '社会',
  global: '国际',
  other: '其他',
};

// Admin types
export type SourceStatus = 'active' | 'error' | 'paused';

export interface Source {
  id: number;
  name: string;
  type: string;
  endpoint: string;
  status: SourceStatus;
  last_fetched_at: string | null;
  created_at: string;
}

export interface AdminStats {
  articles_today: number;
  events_today: number;
  active_sources: number;
  total_sources: number;
  uptime_seconds: number;
  sources_health?: Array<{
    name: string;
    type: string | null;
    status: string | null;
    last_fetched_at: string | null;
    last_error: string | null;
  }>;
  server_time?: string;
}

export interface TaskLog {
  id: string;
  task: string;
  status: 'success' | 'failed';
  message: string;
  created_at: string;
}

export interface SourceFormData {
  name: string;
  endpoint: string;
}
