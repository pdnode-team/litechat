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
} from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('litechat_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
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

const AUTH_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/setup-admin', '/auth/bootstrap-status'];

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
};

export const usersApi = {
  list: async (role?: string) => {
    const res = await api.get<User[]>('/users', { params: role ? { role } : undefined });
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
  list: async (activeOnly?: boolean) => {
    const res = await api.get<ManagedApp[]>('/apps', {
      params: activeOnly ? { active_only: true } : undefined,
    });
    return res.data;
  },
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
  list: async (activeOnly?: boolean) => {
    const res = await api.get<TicketType[]>('/ticket-types', {
      params: activeOnly ? { active_only: true } : undefined,
    });
    return res.data;
  },
  create: async (data: {
    name: string;
    code: string;
    description?: string;
    fields_schema?: any[];
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
  list: async (params?: { category?: string; search?: string; active_only?: boolean }) => {
    const res = await api.get<FaqItem[]>('/faq', { params });
    return res.data;
  },
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
  list: async (params?: {
    status?: string;
    priority?: string;
    category?: string;
    search?: string;
    assigned_to_me?: boolean;
  }) => {
    const res = await api.get<Ticket[]>('/tickets', { params });
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
    custom_fields?: Record<string, any>;
  }) => {
    const res = await api.post<Ticket>('/tickets', data);
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
  list: async (ticketId: number) => {
    const res = await api.get<Message[]>(`/tickets/${ticketId}/messages`);
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
    const res = await api.post<AttachmentItem>('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },
};

export const cannedApi = {
  list: async () => {
    const res = await api.get<CannedResponse[]>('/canned-responses');
    return res.data;
  },
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

export default api;
