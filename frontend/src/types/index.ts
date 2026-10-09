export interface HotEvent {
  id: number;
  title: string;
  summary: string | null;
  detail: string | null;
  category: string | null;
  hot_score: number;
  trend: 'up' | 'down' | 'stable';
  sentiment: string | null;
  entities: string[] | null;
  articles_count: number;
  sources_count: number;
  first_seen_at: string | null;
  last_updated_at: string | null;
  /** 聚合发布时间：达标瞬间写入、永不更新，列表按它倒序，卡片显示它 */
  aggregated_at: string | null;
  cover_image: string | null;
  trend_data?: number[] | null;
}

export interface HotEventDetail extends HotEvent {
  sources: SourceItem[];
  related_events: RelatedEvent[];
}

export interface SourceItem {
  name: string;
  url: string;
  title: string;
  hot_score: number;
  /** 链接能否在浏览器打开；false 时前端用标题做搜索兜底 */
  browsable?: boolean;
}

export interface RelatedEvent {
  id: number;
  title: string;
}

export type Category =
  | 'all'
  | 'tech'
  | 'finance'
  | 'social'
  | 'global'
  | 'sports'
  | 'entertainment'
  | 'health'
  | 'other';

export const CATEGORY_LABELS: Record<Category, string> = {
  all: '全部',
  tech: '科技',
  finance: '财经',
  social: '社会',
  global: '国际',
  sports: '体育',
  entertainment: '娱乐',
  health: '健康',
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
  fetched_today?: number;
}

export interface AdminStats {
  articles_today: number;
  events_today: number;
  active_sources: number;
  total_sources: number;
  uptime_seconds: number;
  /** 系统首次上线时间（跨重启累计的起点） */
  first_started_at?: string;
  sources_health?: SourceHealth[];
  server_time?: string;
}

export interface TaskLog {
  id: string;
  task: string;
  status: 'success' | 'failed';
  message: string;
  created_at: string;
}

/** admin/stats 返回的来源健康度（只读看板用） */
export interface SourceHealth {
  name: string;
  type: string | null;
  status: string | null;
  last_fetched_at: string | null;
  last_error: string | null;
  fetched_today?: number;
}
