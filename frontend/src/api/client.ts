import axios from 'axios';
import {
  User,
  Ticket,
  Message,
  CannedResponse,
  CSATRating,
  AnalyticsSummary,
  AttachmentItem,
  ManagedApp,
  TicketType,
  FaqItem,
  FaqQueryResult,
  CustomFieldDefinition,
  Page,
  PageParams,
  AppSettings,
  EmailSettingsUpdate,
  NotificationSettingsUpdate,
  SlaSettingsUpdate,
  InboxItem,
} from '../types';
import { API_BASE_URL } from './config';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/** Largest page the API will serve; used when a caller wants a whole catalogue. */
const MAX_PAGE_SIZE = 200;

/**
 * Walk every page of a list endpoint.
 *
 * Only for small catalogues used to populate dropdowns (apps, ticket types,
 * canned responses). Anything user-scalable must page explicitly instead.
 */
const collectAll = async <T>(fetchPage: (offset: number) => Promise<Page<T>>): Promise<T[]> => {
  const all: T[] = [];
  let offset = 0;

  for (;;) {
    const page = await fetchPage(offset);
    all.push(...page.items);
    offset += page.items.length;
    if (page.items.length === 0 || all.length >= page.total) break;
  }

  return all;
};

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('litechat_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Let the browser set multipart/form-data with a boundary. A hardcoded
  // Content-Type without one makes Litestar reject the upload.
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  return config;
});

/**
 * The response interceptor lives outside React, so it cannot call `logout()`
 * directly. AuthContext registers itself here on mount; the interceptor then
 * clears the session so the SPA falls back to the sign-in screen instead of
 * staying on a screen whose every request fails with 401.
 */
type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

export const setUnauthorizedHandler = (handler: UnauthorizedHandler | null) => {
  onUnauthorized = handler;
};

const AUTH_ENDPOINTS = [
  '/auth/login',
  '/auth/register',
  '/auth/setup-admin',
  '/auth/bootstrap-status',
  '/auth/logout',
];

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url: string | undefined = error.config?.url;
    const isAuthAttempt = Boolean(url && AUTH_ENDPOINTS.some((path) => url.includes(path)));

    // 401 = the session is gone (expired, revoked, or the account was disabled),
    // so drop it. 403 means "authenticated but not permitted" and must NOT log
    // the user out — a customer hitting an admin route should just see an error.
    if (status === 401 && !isAuthAttempt) {
      onUnauthorized?.();
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  /** Whether the instance still needs its very first administrator. */
  getBootstrapStatus: async () => {
    const res = await api.get<{ needs_setup: boolean }>('/auth/bootstrap-status');
    return res.data;
  },
  /** One-shot administrator bootstrap; the backend locks this once any user exists. */
  setupAdmin: async (email: string, username: string, full_name: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/auth/setup-admin', {
      email,
      username,
      full_name,
      password,
    });
    return res.data;
  },
  login: async (username_or_email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/auth/login', {
      username_or_email,
      password,
    });
    return res.data;
  },
  register: async (email: string, username: string, full_name: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/auth/register', {
      email,
      username,
      full_name,
      password,
    });
    return res.data;
  },
  getMe: async () => {
    const res = await api.get<User>('/auth/me');
    return res.data;
  },
  forgotPassword: async (email: string) => {
    const res = await api.post<{ detail: string }>('/auth/forgot-password', { email });
    return res.data;
  },
  resetPassword: async (token: string, new_password: string) => {
    const res = await api.post<{ detail: string }>('/auth/reset-password', { token, new_password });
    return res.data;
  },
  verifyEmail: async (token: string) => {
    const res = await api.post<{ detail: string }>('/auth/verify-email', { token });
    return res.data;
  },
  resendVerification: async () => {
    const res = await api.post<{ detail: string }>('/auth/resend-verification');
    return res.data;
  },
  changePassword: async (current_password: string, new_password: string) => {
    const res = await api.post<{ detail: string; access_token: string; user: User }>(
      '/auth/change-password',
      { current_password, new_password },
    );
    return res.data;
  },
  changeEmail: async (password: string, new_email: string) => {
    const res = await api.post<{ detail: string }>('/auth/change-email', { password, new_email });
    return res.data;
  },
  verifyEmailChange: async (token: string) => {
    const res = await api.post<{ detail: string }>('/auth/verify-email-change', { token });
    return res.data;
  },
  createWsTicket: async () => {
    const res = await api.post<{ token: string; expires_in: number }>('/auth/ws-ticket');
    return res.data;
  },
  logout: async () => {
    await api.post('/auth/logout');
  },
};

export const inboxApi = {
  list: async (params?: PageParams): Promise<Page<InboxItem>> => {
    const res = await api.get<Page<InboxItem>>('/notifications', { params });
    return res.data;
  },
  markRead: async (body: { ids?: number[]; all?: boolean }): Promise<{ updated: number }> => {
    const res = await api.post<{ updated: number }>('/notifications/read', body);
    return res.data;
  },
};

export const usersApi = {
  updateMe: async (data: { full_name?: string; avatar_url?: string }) => {
    const res = await api.patch<User>('/users/me', data);
    return res.data;
  },
  list: async (
    params?: { role?: string; search?: string } & PageParams
  ): Promise<Page<User>> => {
    const res = await api.get<Page<User>>('/users', { params });
    return res.data;
  },
  listAll: async (params?: { role?: string; search?: string }): Promise<User[]> =>
    collectAll((offset) => usersApi.list({ ...params, limit: MAX_PAGE_SIZE, offset })),
  /** Active staff an agent may assign tickets to (available to agent and admin). */
  listAssignable: async () => {
    const res = await api.get<User[]>('/users/assignable');
    return res.data;
  },
  updateRole: async (userId: number, role: 'customer' | 'agent' | 'admin') => {
    const res = await api.patch<User>(`/users/${userId}/role`, { role });
    return res.data;
  },
  updateStatus: async (userId: number, isActive: boolean) => {
    const res = await api.patch<User>(`/users/${userId}/status`, { is_active: isActive });
    return res.data;
  },
};

export const appsApi = {
  list: async (params?: { active_only?: boolean } & PageParams): Promise<Page<ManagedApp>> => {
    const res = await api.get<Page<ManagedApp>>('/apps', { params });
    return res.data;
  },
  listAll: async (activeOnly?: boolean): Promise<ManagedApp[]> =>
    collectAll((offset) =>
      appsApi.list({ active_only: activeOnly, limit: MAX_PAGE_SIZE, offset })
    ),
  create: async (data: { name: string; code: string; base_url?: string; is_active?: boolean }) => {
    const res = await api.post<ManagedApp>('/apps', data);
    return res.data;
  },
  update: async (id: number, data: Partial<ManagedApp>) => {
    const res = await api.put<ManagedApp>(`/apps/${id}`, data);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/apps/${id}`);
  },
};

export const ticketTypesApi = {
  list: async (params?: { active_only?: boolean } & PageParams): Promise<Page<TicketType>> => {
    const res = await api.get<Page<TicketType>>('/ticket-types', { params });
    return res.data;
  },
  listAll: async (activeOnly?: boolean): Promise<TicketType[]> =>
    collectAll((offset) =>
      ticketTypesApi.list({ active_only: activeOnly, limit: MAX_PAGE_SIZE, offset })
    ),
  create: async (data: {
    name: string;
    code: string;
    description?: string;
    fields_schema?: CustomFieldDefinition[];
    is_active?: boolean;
  }) => {
    const res = await api.post<TicketType>('/ticket-types', data);
    return res.data;
  },
  update: async (id: number, data: Partial<TicketType>) => {
    const res = await api.put<TicketType>(`/ticket-types/${id}`, data);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/ticket-types/${id}`);
  },
};

export const faqApi = {
  list: async (
    params?: { category?: string; search?: string; active_only?: boolean } & PageParams
  ): Promise<Page<FaqItem>> => {
    const res = await api.get<Page<FaqItem>>('/faq', { params });
    return res.data;
  },
  listAll: async (params?: {
    category?: string;
    search?: string;
    active_only?: boolean;
  }): Promise<FaqItem[]> =>
    collectAll((offset) => faqApi.list({ ...params, limit: MAX_PAGE_SIZE, offset })),
  query: async (query: string, category?: string) => {
    const res = await api.post<FaqQueryResult>('/faq/query', { query, category });
    return res.data;
  },
  create: async (data: {
    category: string;
    question: string;
    answer: string;
    keywords?: string;
    quick_replies?: string[];
    sort_order?: number;
    is_active?: boolean;
  }) => {
    const res = await api.post<FaqItem>('/faq', data);
    return res.data;
  },
  update: async (id: number, data: Partial<FaqItem>) => {
    const res = await api.put<FaqItem>(`/faq/${id}`, data);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/faq/${id}`);
  },
};

export const ticketsApi = {
  list: async (
    params?: {
      status?: string;
      priority?: string;
      priority_in?: string;
      category?: string;
      search?: string;
      assigned_to_me?: boolean;
      unassigned?: boolean;
      tag?: string;
      ticket_type_id?: number;
      app_id?: number;
      created_from?: string;
      created_to?: string;
    } & PageParams
  ): Promise<Page<Ticket>> => {
    const res = await api.get<Page<Ticket>>('/tickets', { params });
    return res.data;
  },
  get: async (ticketId: number) => {
    const res = await api.get<Ticket>(`/tickets/${ticketId}`);
    return res.data;
  },
  create: async (data: {
    title: string;
    description: string;
    priority: string;
    category: string;
    tags?: string;
    app_id?: number;
    target_url?: string;
    ticket_type_id?: number;
    custom_fields?: Record<string, unknown>;
  }) => {
    const res = await api.post<Ticket>('/tickets', data);
    return res.data;
  },
  update: async (
    ticketId: number,
    data: {
      title?: string;
      description?: string;
      category?: string;
      tags?: string;
      target_url?: string;
    }
  ) => {
    const res = await api.patch<Ticket>(`/tickets/${ticketId}`, data);
    return res.data;
  },
  updateStatus: async (ticketId: number, status: string) => {
    const res = await api.patch<Ticket>(`/tickets/${ticketId}/status`, { status });
    return res.data;
  },
  assign: async (ticketId: number, agentId: number | null) => {
    const res = await api.patch<Ticket>(`/tickets/${ticketId}/assign`, { agent_id: agentId });
    return res.data;
  },
  updatePriority: async (ticketId: number, priority: string) => {
    const res = await api.patch<Ticket>(`/tickets/${ticketId}/priority`, { priority });
    return res.data;
  },
};

export const messagesApi = {
  /**
   * Page 0 holds the newest messages, each page still in chronological order,
   * so a page can be prepended directly when loading older history.
   */
  list: async (ticketId: number, params?: PageParams): Promise<Page<Message>> => {
    const res = await api.get<Page<Message>>(`/tickets/${ticketId}/messages`, { params });
    return res.data;
  },
  send: async (
    ticketId: number,
    data: { content: string; message_type?: string; attachments?: AttachmentItem[] }
  ) => {
    const res = await api.post<Message>(`/tickets/${ticketId}/messages`, data);
    return res.data;
  },
  upload: async (file: File) => {
    const formData = new FormData();
    formData.append('data', file);
    const res = await api.post<AttachmentItem>('/upload', formData);
    return res.data;
  },
};

export const cannedApi = {
  list: async (params?: PageParams): Promise<Page<CannedResponse>> => {
    const res = await api.get<Page<CannedResponse>>('/canned-responses', { params });
    return res.data;
  },
  listAll: async (): Promise<CannedResponse[]> =>
    collectAll((offset) => cannedApi.list({ limit: MAX_PAGE_SIZE, offset })),
  create: async (data: { shortcut: string; title: string; content: string; category: string }) => {
    const res = await api.post<CannedResponse>('/canned-responses', data);
    return res.data;
  },
  update: async (id: number, data: Partial<CannedResponse>) => {
    const res = await api.patch<CannedResponse>(`/canned-responses/${id}`, data);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/canned-responses/${id}`);
  },
};

export const csatApi = {
  get: async (ticketId: number) => {
    const res = await api.get<CSATRating | null>(`/tickets/${ticketId}/csat`);
    return res.data;
  },
  submit: async (ticketId: number, data: { score: number; comment?: string }) => {
    const res = await api.post<CSATRating>(`/tickets/${ticketId}/csat`, data);
    return res.data;
  },
};

export const analyticsApi = {
  getSummary: async () => {
    const res = await api.get<AnalyticsSummary>('/analytics/summary');
    return res.data;
  },
};

export const settingsApi = {
  get: async (): Promise<AppSettings> => {
    const res = await api.get<AppSettings>('/settings');
    return res.data;
  },
  updateEmail: async (data: EmailSettingsUpdate): Promise<AppSettings> => {
    const res = await api.put<AppSettings>('/settings/email', data);
    return res.data;
  },
  updateNotifications: async (data: NotificationSettingsUpdate): Promise<AppSettings> => {
    const res = await api.put<AppSettings>('/settings/notifications', data);
    return res.data;
  },
  sendTestEmail: async (to: string): Promise<{ sent: boolean; detail: string }> => {
    const res = await api.post<{ sent: boolean; detail: string }>('/settings/email/test', { to });
    return res.data;
  },
  updateSla: async (data: SlaSettingsUpdate): Promise<AppSettings> => {
    const res = await api.put<AppSettings>('/settings/sla', data);
    return res.data;
  },
};

export default api;
