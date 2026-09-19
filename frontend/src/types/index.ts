export type UserRole = 'customer' | 'agent' | 'admin' | 'system';

export type TicketStatus = 'open' | 'pending' | 'in_progress' | 'resolved' | 'closed';

export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent';

export type TicketCategory = 'technical' | 'billing' | 'account' | 'general';

/** Envelope returned by every paginated list endpoint. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface PageParams {
  limit?: number;
  offset?: number;
}

/** Runtime settings editable by an administrator (SMTP + notification policy). */
export interface AppSettings {
  smtp_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  /** The password itself is never returned, only whether one is stored. */
  smtp_password_set: boolean;
  smtp_use_tls: boolean;
  smtp_from: string;
  public_app_url: string;
  notify_new_ticket: boolean;
  notify_ticket_reply: boolean;
  notify_assignment: boolean;
  notify_status_change: boolean;
  support_email: string;
}

export type EmailSettingsUpdate = Partial<
  Pick<
    AppSettings,
    | 'smtp_enabled'
    | 'smtp_host'
    | 'smtp_port'
    | 'smtp_username'
    | 'smtp_use_tls'
    | 'smtp_from'
    | 'public_app_url'
  >
> & { smtp_password?: string };

export type NotificationSettingsUpdate = Partial<
  Pick<
    AppSettings,
    | 'notify_new_ticket'
    | 'notify_ticket_reply'
    | 'notify_assignment'
    | 'notify_status_change'
    | 'support_email'
  >
>;

export interface User {
  id: number;
  email: string;
  username: string;
  full_name: string;
  role: UserRole;
  avatar_url?: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
}

export interface AttachmentItem {
  name: string;
  url: string;
  file_type: 'image' | 'document';
  size: number;
}

export interface Message {
  id: number;
  ticket_id: number;
  sender_id?: number;
  sender_name: string;
  sender_role: UserRole;
  message_type: 'text' | 'whisper' | 'system' | 'action_card';
  content: string;
  attachments?: AttachmentItem[];
  created_at: string;
}

export interface ManagedApp {
  id: number;
  name: string;
  code: string;
  base_url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomFieldDefinition {
  key: string;
  label: string;
  type: 'text' | 'textarea' | 'select' | 'number' | 'switch' | 'url';
  required: boolean;
  placeholder?: string;
  options?: string[];
}

export interface TicketType {
  id: number;
  name: string;
  code: string;
  description?: string;
  fields_schema: CustomFieldDefinition[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FaqItem {
  id: number;
  category: string;
  question: string;
  answer: string;
  keywords?: string;
  quick_replies?: string[];
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FaqQueryResult {
  matches: FaqItem[];
  suggested_reply?: string;
  quick_options: string[];
  can_escalate_ticket: boolean;
}

export interface Ticket {
  id: number;
  ticket_code: string;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  category: TicketCategory;
  customer_id: number;
  assigned_agent_id?: number;
  customer?: User;
  assigned_agent?: User;
  app_id?: number;
  app?: ManagedApp;
  target_url?: string;
  ticket_type_id?: number;
  ticket_type?: TicketType;
  custom_fields?: Record<string, unknown>;
  first_response_due_at?: string;
  resolution_due_at?: string;
  first_responded_at?: string;
  resolved_at?: string;
  closed_at?: string;
  sla_first_response_status?: 'on_track' | 'breached' | 'fulfilled';
  sla_resolution_status?: 'on_track' | 'breached' | 'fulfilled';
  tags?: string;
  created_at: string;
  updated_at: string;
}

export interface CannedResponse {
  id: number;
  shortcut: string;
  title: string;
  content: string;
  category: string;
  created_at: string;
  updated_at: string;
}

export interface CSATRating {
  id: number;
  ticket_id: number;
  customer_id: number;
  score: number;
  comment?: string;
  created_at: string;
}

export interface AgentPerformanceItem {
  agent_id: number;
  name: string;
  assigned_count: number;
  resolved_count: number;
  avg_resolution_time_minutes: number | null;
  csat_avg: number | null;
}

export interface AnalyticsSummary {
  total_tickets: number;
  open_tickets: number;
  pending_tickets: number;
  in_progress_tickets: number;
  resolved_tickets: number;
  closed_tickets: number;
  sla_compliance_rate: number | null;
  sla_breached_count: number;
  csat_average_score: number | null;
  csat_total_reviews: number;
  category_distribution: Record<string, number>;
  priority_distribution: Record<string, number>;
  agents_performance: AgentPerformanceItem[];
}

