import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  analyticsApi,
  cannedApi,
  usersApi,
  appsApi,
  ticketTypesApi,
  faqApi,
} from '../../api/client';
import {
  AnalyticsSummary,
  CannedResponse,
  User,
  ManagedApp,
  TicketType,
  CustomFieldDefinition,
  FaqItem,
} from '../../types';
import { UserAvatar } from '../common/UserAvatar';
import { Modal } from '../common/Modal';
import { apiErrorMessage } from '../../utils/errors';
import { CustomFieldBuilder } from './CustomFieldBuilder';
import {
  Star,
  AlertTriangle,
  Plus,
  Trash2,
  Shield,
  Search,
  Check,
  Globe,
  Sliders,
  HelpCircle,
  ExternalLink,
  X,
  Pencil,
  ServerCog,
} from 'lucide-react';
import { formatUtc } from '../../utils/datetime';
import { useRealtimeEvent } from '../../context/RealtimeContext';
import { EmailSettingsPanel } from './EmailSettingsPanel';

/** Rows fetched per user-table page. */
const PAGE_SIZE = 25;

export const AdminDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<
    'overview' | 'users' | 'canned' | 'apps' | 'types' | 'faq' | 'settings'
  >('overview');

  // Existing states
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [cannedList, setCannedList] = useState<CannedResponse[]>([]);
  const [usersList, setUsersList] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);  const [userSearch, setUserSearch] = useState('');
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Macros modal state
  const [isAddCannedOpen, setIsAddCannedOpen] = useState(false);
  const [shortcut, setShortcut] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('general');
  const [editingCanned, setEditingCanned] = useState<CannedResponse | null>(null);
  const [editShortcut, setEditShortcut] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editCategory, setEditCategory] = useState('general');

  // Apps state
  const [appsList, setAppsList] = useState<ManagedApp[]>([]);
  const [isAddAppOpen, setIsAddAppOpen] = useState(false);
  const [appName, setAppName] = useState('');
  const [appCode, setAppCode] = useState('');
  const [appBaseUrl, setAppBaseUrl] = useState('');
  const [appFormError, setAppFormError] = useState<string | null>(null);
  const [editingApp, setEditingApp] = useState<ManagedApp | null>(null);
  const [editAppName, setEditAppName] = useState('');
  const [editAppCode, setEditAppCode] = useState('');
  const [editAppBaseUrl, setEditAppBaseUrl] = useState('');
  const [editAppActive, setEditAppActive] = useState(true);

  // Ticket Types & Custom Fields state
  const [typesList, setTypesList] = useState<TicketType[]>([]);
  const [isAddTypeOpen, setIsAddTypeOpen] = useState(false);
  const [typeName, setTypeName] = useState('');
  const [typeCode, setTypeCode] = useState('');
  const [typeDescription, setTypeDescription] = useState('');
  const [typeFields, setTypeFields] = useState<CustomFieldDefinition[]>([]);

  // Ticket Type Editing state
  const [editingType, setEditingType] = useState<TicketType | null>(null);
  const [editTypeName, setEditTypeName] = useState('');
  const [editTypeCode, setEditTypeCode] = useState('');
  const [editTypeDescription, setEditTypeDescription] = useState('');
  const [editTypeFields, setEditTypeFields] = useState<CustomFieldDefinition[]>([]);
  const [editTypeActive, setEditTypeActive] = useState(true);

  // FAQ state
  const [faqList, setFaqList] = useState<FaqItem[]>([]);
  const [isAddFaqOpen, setIsAddFaqOpen] = useState(false);
  const [faqCategory, setFaqCategory] = useState('technical');
  const [faqQuestion, setFaqQuestion] = useState('');
  const [faqAnswer, setFaqAnswer] = useState('');
  const [faqKeywords, setFaqKeywords] = useState('');
  const [faqQuickRepliesStr, setFaqQuickRepliesStr] = useState('');

  // FAQ Editing state
  const [editingFaq, setEditingFaq] = useState<FaqItem | null>(null);
  const [editFaqCategory, setEditFaqCategory] = useState('technical');
  const [editFaqQuestion, setEditFaqQuestion] = useState('');
  const [editFaqAnswer, setEditFaqAnswer] = useState('');
  const [editFaqKeywords, setEditFaqKeywords] = useState('');
  const [editFaqQuickRepliesStr, setEditFaqQuickRepliesStr] = useState('');
  const [editFaqActive, setEditFaqActive] = useState(true);

  const [fetchError, setFetchError] = useState<string | null>(null);
  // A form submit that is already in flight must not be sent again. A double
  // click used to insert the row twice and the second insert was rejected by a
  // unique index, which the user saw as a confusing error about a row they had
  // just created. The ref is what actually blocks re-entry: state updates are
  // asynchronous, so a second click can arrive before the re-render.
  const submittingRef = useRef<string | null>(null);
  const [submittingAction, setSubmittingAction] = useState<string | null>(null);

  const beginSubmit = (action: string): boolean => {
    if (submittingRef.current) return false;
    submittingRef.current = action;
    setSubmittingAction(action);
    return true;
  };

  const endSubmit = (): void => {
    submittingRef.current = null;
    setSubmittingAction(null);
  };


  const [usersTotal, setUsersTotal] = useState(0);
  const [loadingMoreUsers, setLoadingMoreUsers] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setFetchError(null);
    try {
      // Catalogues are small, so load them whole; the user table is paginated
      // separately because it grows with the customer base.
      const [sumRes, cannedRes, usersRes, appsRes, typesRes, faqsRes] = await Promise.allSettled([
        analyticsApi.getSummary(),
        cannedApi.listAll(),
        usersApi.list({ limit: PAGE_SIZE, offset: 0 }),
        appsApi.listAll(),
        ticketTypesApi.listAll(),
        faqApi.listAll(),
      ]);

      const failedModules: string[] = [];
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value);
      else failedModules.push('Analytics');

      if (cannedRes.status === 'fulfilled') setCannedList(cannedRes.value);
      else failedModules.push('Macros');

      if (usersRes.status === 'fulfilled') {
        setUsersList(usersRes.value.items);
        setUsersTotal(usersRes.value.total);
      } else failedModules.push('Users');

      if (appsRes.status === 'fulfilled') setAppsList(appsRes.value);
      else failedModules.push('Apps');

      if (typesRes.status === 'fulfilled') setTypesList(typesRes.value);
      else failedModules.push('Ticket Types');

      if (faqsRes.status === 'fulfilled') setFaqList(faqsRes.value);
      else failedModules.push('FAQ Articles');

      if (failedModules.length > 0) {
        setFetchError(`Failed to load: ${failedModules.join(', ')}`);
      }
    } catch (err) {
      console.error('Failed to load admin data', err);
      setFetchError('Unexpected error loading administrative data');
    } finally {
      setLoading(false);
    }
  };

  /** Server-side user search: the table only holds one page at a time. */
  const searchUsers = useCallback(async (term: string) => {
    setLoadingMoreUsers(true);
    try {
      const page = await usersApi.list({ search: term.trim() || undefined, limit: PAGE_SIZE, offset: 0 });
      setUsersList(page.items);
      setUsersTotal(page.total);
    } catch (err) {
      console.error('Failed to search users', err);
    } finally {
      setLoadingMoreUsers(false);
    }
  }, []);

  const loadMoreUsers = async () => {
    setLoadingMoreUsers(true);
    try {
      const page = await usersApi.list({
        search: userSearch.trim() || undefined,
        limit: PAGE_SIZE,
        offset: usersList.length,
      });
      setUsersList((prev) => {
        const seen = new Set(prev.map((u) => u.id));
        return [...prev, ...page.items.filter((u) => !seen.has(u.id))];
      });
      setUsersTotal(page.total);
    } catch (err) {
      console.error('Failed to load more users', err);
    } finally {
      setLoadingMoreUsers(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Live console: account, catalogue and rating changes arrive over the
  // notification socket, so the tables and analytics stay current without a
  // manual refresh. Debounced because one action can emit several events.
  const liveRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleDataRefresh = useCallback(() => {
    if (liveRefreshTimer.current) clearTimeout(liveRefreshTimer.current);
    liveRefreshTimer.current = setTimeout(() => {
      void fetchData();
    }, 400);
  }, []);

  useEffect(
    () => () => {
      if (liveRefreshTimer.current) clearTimeout(liveRefreshTimer.current);
    },
    []
  );

  useRealtimeEvent(['user_updated', 'catalog_changed', 'csat_submitted', 'ticket_created'], (event) => {
    if (event.type === 'user_updated') {
      const actor = typeof event.actor_name === 'string' ? event.actor_name : 'An administrator';
      triggerToast(`Account updated by ${actor}`);
    } else if (event.type === 'catalog_changed') {
      const resource = typeof event.resource === 'string' ? event.resource.replace('_', ' ') : 'catalogue';
      triggerToast(`${resource} changed`);
    }
    scheduleDataRefresh();
  });

  const triggerToast = (msg: string) => {
    setActionMessage(msg);
    setTimeout(() => setActionMessage(null), 3500);
  };

  // Role management
  const handleRoleChange = async (targetUser: User, newRole: 'customer' | 'agent' | 'admin') => {
    if (targetUser.role === newRole) return;
    setUpdatingUserId(targetUser.id);
    try {
      const updated = await usersApi.updateRole(targetUser.id, newRole);
      setUsersList((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      triggerToast(`Updated role for ${targetUser.full_name} to ${newRole.toUpperCase()}`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update user role'));
    } finally {
      setUpdatingUserId(null);
    }
  };

  // User active toggle
  const handleToggleUserActive = async (targetUser: User) => {
    setUpdatingUserId(targetUser.id);
    try {
      const updated = await usersApi.updateStatus(targetUser.id, !targetUser.is_active);
      setUsersList((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      triggerToast(`User ${targetUser.full_name} is now ${updated.is_active ? 'ACTIVE' : 'DEACTIVATED'}`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update user status'));
    } finally {
      setUpdatingUserId(null);
    }
  };

  // Macros
  const handleAddCanned = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!shortcut || !title || !content) return;
    if (!beginSubmit('canned:create')) return;

    try {
      const created = await cannedApi.create({
        shortcut: shortcut.startsWith('/') ? shortcut : `/${shortcut}`,
        title,
        content,
        category,
      });
      setCannedList((prev) => [...prev, created]);
      setIsAddCannedOpen(false);
      setShortcut('');
      setTitle('');
      setContent('');
      triggerToast(`Macro "${created.shortcut}" added`);
    } catch (err) {
      console.error('Failed to create canned response', err);
    } finally {
      endSubmit();
    }
  };

  const handleDeleteCanned = async (id: number) => {
    try {
      await cannedApi.delete(id);
      setCannedList((prev) => prev.filter((c) => c.id !== id));
      triggerToast('Macro deleted');
    } catch (err) {
      console.error('Failed to delete canned response', err);
    }
  };

  // Apps Management
  const handleAddApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appName.trim() || !appCode.trim()) return;

    // The full catalogue is already loaded, so an obvious clash is caught here
    // instead of as a round trip that ends in "already exists".
    const normalisedCode = appCode.trim().toLowerCase();
    if (appsList.some((existing) => existing.code === normalisedCode)) {
      setAppFormError(`The code "${normalisedCode}" is already used by another application.`);
      return;
    }

    if (!beginSubmit('app:create')) return;
    setAppFormError(null);

    try {
      const created = await appsApi.create({
        name: appName.trim(),
        code: normalisedCode,
        base_url: appBaseUrl.trim() || undefined,
        is_active: true,
      });
      setAppsList((prev) => [...prev, created]);
      setIsAddAppOpen(false);
      setAppName('');
      setAppCode('');
      setAppBaseUrl('');
      setAppFormError(null);
      triggerToast(`Application "${created.name}" registered`);
    } catch (err) {
      // Shown inside the dialog: an alert() loses the field the user has to fix.
      setAppFormError(apiErrorMessage(err, 'Failed to register app'));
    } finally {
      endSubmit();
    }
  };

  const handleDeleteApp = async (id: number) => {
    if (!confirm('Are you sure you want to remove this application?')) return;
    try {
      await appsApi.delete(id);
      setAppsList((prev) => prev.filter((a) => a.id !== id));
      triggerToast('Application removed');
    } catch (err) {
      console.error('Failed to delete app', err);
    }
  };

  // Ticket Types & Custom Fields
  const handleAddTicketType = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!typeName.trim() || !typeCode.trim()) return;
    if (!beginSubmit('type:create')) return;

    try {
      const created = await ticketTypesApi.create({
        name: typeName.trim(),
        code: typeCode.trim().toLowerCase(),
        description: typeDescription.trim(),
        fields_schema: typeFields,
        is_active: true,
      });
      setTypesList((prev) => [...prev, created]);
      setIsAddTypeOpen(false);
      setTypeName('');
      setTypeCode('');
      setTypeDescription('');
      setTypeFields([]);
      triggerToast(`Ticket type "${created.name}" created`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to create ticket type'));
    } finally {
      endSubmit();
    }
  };

  const handleDeleteTicketType = async (id: number) => {
    if (!confirm('Are you sure you want to remove this ticket type?')) return;
    try {
      await ticketTypesApi.delete(id);
      setTypesList((prev) => prev.filter((t) => t.id !== id));
      triggerToast('Ticket type removed');
    } catch (err) {
      console.error('Failed to delete ticket type', err);
    }
  };

  // FAQ Management
  const handleAddFaq = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!faqQuestion.trim() || !faqAnswer.trim()) return;
    if (!beginSubmit('faq:create')) return;

    try {
      const replies = faqQuickRepliesStr
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const created = await faqApi.create({
        category: faqCategory,
        question: faqQuestion.trim(),
        answer: faqAnswer.trim(),
        keywords: faqKeywords.trim(),
        quick_replies: replies,
      });
      setFaqList((prev) => [...prev, created]);
      setIsAddFaqOpen(false);
      setFaqQuestion('');
      setFaqAnswer('');
      setFaqKeywords('');
      setFaqQuickRepliesStr('');
      triggerToast('FAQ entry created');
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to create FAQ'));
    } finally {
      endSubmit();
    }
  };

  const handleDeleteFaq = async (id: number) => {
    if (!confirm('Are you sure you want to delete this FAQ article?')) return;
    try {
      await faqApi.delete(id);
      setFaqList((prev) => prev.filter((f) => f.id !== id));
      triggerToast('FAQ article removed');
    } catch (err) {
      console.error('Failed to delete FAQ', err);
    }
  };

  // Edit Handlers for Macros
  const openEditCanned = (macro: CannedResponse) => {
    setEditingCanned(macro);
    setEditShortcut(macro.shortcut);
    setEditTitle(macro.title);
    setEditContent(macro.content);
    setEditCategory(macro.category);
  };

  const handleUpdateCanned = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCanned || !editShortcut.trim() || !editTitle.trim() || !editContent.trim()) return;
    if (!beginSubmit('canned:update')) return;

    try {
      const updated = await cannedApi.update(editingCanned.id, {
        shortcut: editShortcut.startsWith('/') ? editShortcut.trim() : `/${editShortcut.trim()}`,
        title: editTitle.trim(),
        content: editContent.trim(),
        category: editCategory,
      });
      setCannedList((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setEditingCanned(null);
      triggerToast(`Macro "${updated.shortcut}" updated`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update macro'));
    } finally {
      endSubmit();
    }
  };

  // Edit Handlers for Apps
  const openEditApp = (app: ManagedApp) => {
    setEditingApp(app);
    setEditAppName(app.name);
    setEditAppCode(app.code);
    setEditAppBaseUrl(app.base_url || '');
    setEditAppActive(app.is_active);
  };

  const handleUpdateApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingApp || !editAppName.trim() || !editAppCode.trim()) return;
    if (!beginSubmit('app:update')) return;

    try {
      const updated = await appsApi.update(editingApp.id, {
        name: editAppName.trim(),
        code: editAppCode.trim().toLowerCase(),
        // Send '' (not undefined) so an emptied field actually clears the value:
        // JSON.stringify drops undefined keys, and the API then keeps the old one.
        base_url: editAppBaseUrl.trim(),
        is_active: editAppActive,
      });
      setAppsList((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setEditingApp(null);
      triggerToast(`Application "${updated.name}" updated`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update app'));
    } finally {
      endSubmit();
    }
  };

  // Edit Handlers for Ticket Types
  const openEditType = (tt: TicketType) => {
    setEditingType(tt);
    setEditTypeName(tt.name);
    setEditTypeCode(tt.code);
    setEditTypeDescription(tt.description || '');
    setEditTypeFields([...tt.fields_schema]);
    setEditTypeActive(tt.is_active);
  };

  const handleUpdateTicketType = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingType || !editTypeName.trim() || !editTypeCode.trim()) return;
    if (!beginSubmit('type:update')) return;

    try {
      const updated = await ticketTypesApi.update(editingType.id, {
        name: editTypeName.trim(),
        code: editTypeCode.trim().toLowerCase(),
        description: editTypeDescription.trim(),
        fields_schema: editTypeFields,
        is_active: editTypeActive,
      });
      setTypesList((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      setEditingType(null);
      triggerToast(`Ticket type "${updated.name}" updated`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update ticket type'));
    } finally {
      endSubmit();
    }
  };

  // Edit Handlers for FAQ
  const openEditFaq = (item: FaqItem) => {
    setEditingFaq(item);
    setEditFaqCategory(item.category);
    setEditFaqQuestion(item.question);
    setEditFaqAnswer(item.answer);
    setEditFaqKeywords(item.keywords || '');
    setEditFaqQuickRepliesStr((item.quick_replies || []).join(', '));
    setEditFaqActive(item.is_active);
  };

  const handleUpdateFaq = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingFaq || !editFaqQuestion.trim() || !editFaqAnswer.trim()) return;
    if (!beginSubmit('faq:update')) return;

    try {
      const replies = editFaqQuickRepliesStr
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const updated = await faqApi.update(editingFaq.id, {
        category: editFaqCategory,
        question: editFaqQuestion.trim(),
        answer: editFaqAnswer.trim(),
        keywords: editFaqKeywords.trim(),
        quick_replies: replies,
        is_active: editFaqActive,
      });
      setFaqList((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      setEditingFaq(null);
      triggerToast('FAQ article updated');
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update FAQ'));
    } finally {
      endSubmit();
    }
  };

  // Debounced server-side user search: the table only holds one page.
  const userSearchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (userSearchTimer.current) clearTimeout(userSearchTimer.current);
    // Skip the initial mount, the first page is already loaded.
    userSearchTimer.current = setTimeout(() => {
      void searchUsers(userSearch);
    }, 300);
    return () => {
      if (userSearchTimer.current) clearTimeout(userSearchTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userSearch]);

  if (loading && !summary) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center text-xs font-mono text-zinc-500">
        Loading administrator console...
      </div>
    );
  }

  if (fetchError && !summary) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center space-y-3 font-mono">
        <div className="text-xs text-rose-400">{fetchError}</div>
        <button
          type="button"
          onClick={fetchData}
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs rounded transition"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center space-y-3 font-mono text-xs text-zinc-500">
        <div>No system metrics available.</div>
        <button
          type="button"
          onClick={fetchData}
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs rounded transition"
        >
          Reload
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 space-y-4 w-full">
      {fetchError && (
        <div className="bg-amber-950/50 border border-amber-800/80 text-amber-300 text-xs px-3.5 py-2 rounded-lg font-mono flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span>{fetchError}</span>
          </div>
          <button
            type="button"
            onClick={fetchData}
            className="text-[11px] underline hover:text-amber-100"
          >
            Retry
          </button>
        </div>
      )}

      {/* Top Header & Tab Navigation */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-zinc-900/40 p-4 rounded-xl border border-zinc-800">
        <div>
          <div className="font-mono text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">
            ADMINISTRATION
          </div>
          <h1 className="text-base font-semibold text-zinc-100">System Management Console</h1>
          <p className="text-xs text-zinc-400 mt-0.5">
            Role-based access control, managed apps, dynamic custom fields, SLA metrics, and FAQ knowledge engine.
          </p>
        </div>

        {actionMessage && (
          <div className="bg-emerald-950/80 text-emerald-300 border border-emerald-800 text-xs px-3 py-1.5 rounded-lg font-mono flex items-center gap-1.5 animate-in fade-in">
            <Check className="w-3.5 h-3.5" />
            <span>{actionMessage}</span>
          </div>
        )}

        {/* Tab switch */}
        <div className="flex bg-zinc-950 p-1 rounded-lg border border-zinc-800 text-xs font-mono overflow-x-auto">
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            className={`px-3 py-1 rounded transition whitespace-nowrap ${
              activeTab === 'overview'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            SLA & Metrics
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('users')}
            className={`px-3 py-1 rounded transition flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'users'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Shield className="w-3 h-3" />
            Users ({usersTotal})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('apps')}
            className={`px-3 py-1 rounded transition flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'apps'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Globe className="w-3 h-3" />
            Apps & Sites ({appsList.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('types')}
            className={`px-3 py-1 rounded transition flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'types'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Sliders className="w-3 h-3" />
            Ticket Types ({typesList.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('faq')}
            className={`px-3 py-1 rounded transition flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'faq'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <HelpCircle className="w-3 h-3" />
            FAQ Engine ({faqList.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('canned')}
            className={`px-3 py-1 rounded transition whitespace-nowrap ${
              activeTab === 'canned'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            Macros
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('settings')}
            className={`px-3 py-1 rounded transition whitespace-nowrap ${
              activeTab === 'settings'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <ServerCog className="w-3 h-3" />
              Email &amp; Alerts
            </span>
          </button>
        </div>
      </div>

      {/* TAB 7: EMAIL & NOTIFICATIONS */}
      {activeTab === 'settings' && <EmailSettingsPanel />}

      {/* TAB 1: USERS & PERMISSIONS (RBAC) */}
      {activeTab === 'users' && (
        <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 shadow-2xl overflow-hidden">
          <div className="p-3.5 border-b border-zinc-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-zinc-900/40">
            <div>
              <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-zinc-400" />
                Access Control & Roles
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Configure user authorization levels: Customer, Support Specialist (Agent), or Administrator.
              </p>
            </div>

            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                placeholder="Filter by name, email, role..."
                className="w-full text-xs pl-8 pr-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-600 transition"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase tracking-wider text-[10px] font-mono">
                <tr>
                  <th className="py-2.5 px-3.5">User</th>
                  <th className="py-2.5 px-3.5">Email</th>
                  <th className="py-2.5 px-3.5">Role</th>
                  <th className="py-2.5 px-3.5">Assign Role</th>
                  <th className="py-2.5 px-3.5">Status</th>
                  <th className="py-2.5 px-3.5">Registered</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 font-medium">
                {usersList.map((u) => (
                  <tr key={u.id} className="hover:bg-zinc-800/30 transition">
                    <td className="py-2.5 px-3.5 text-zinc-200 flex items-center gap-2.5">
                      <UserAvatar name={u.full_name} size="sm" />
                      <div>
                        <div className="font-semibold text-zinc-100 leading-tight">{u.full_name}</div>
                        <div className="text-[10px] font-mono text-zinc-500">@{u.username}</div>
                      </div>
                    </td>
                    <td className="py-2.5 px-3.5 font-mono text-zinc-400">{u.email}</td>
                    <td className="py-2.5 px-3.5">
                      <span
                        className={`inline-block text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${
                          u.role === 'admin'
                            ? 'bg-purple-950/60 text-purple-400 border-purple-800/80'
                            : u.role === 'agent'
                            ? 'bg-blue-950/60 text-blue-400 border-blue-800/80'
                            : 'bg-zinc-900 text-zinc-400 border-zinc-800'
                        }`}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="py-2.5 px-3.5">
                      <div className="flex items-center gap-1 font-mono text-[11px]">
                        {(['customer', 'agent', 'admin'] as const).map((r) => (
                          <button
                            key={r}
                            type="button"
                            disabled={updatingUserId === u.id || u.role === r}
                            onClick={() => handleRoleChange(u, r)}
                            className={`px-2 py-0.5 rounded transition uppercase text-[10px] ${
                              u.role === r
                                ? 'bg-zinc-800 text-zinc-200 border border-zinc-700 cursor-default'
                                : 'bg-zinc-950 text-zinc-500 hover:text-zinc-300 border border-zinc-800 hover:border-zinc-700'
                            }`}
                          >
                            {r}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="py-2.5 px-3.5 font-mono">
                      <button
                        type="button"
                        disabled={updatingUserId === u.id}
                        onClick={() => handleToggleUserActive(u)}
                        className={`flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded border transition ${
                          u.is_active
                            ? 'text-emerald-400 border-emerald-900/60 bg-emerald-950/20 hover:bg-emerald-950/40'
                            : 'text-zinc-500 border-zinc-800 bg-zinc-950 hover:text-zinc-300'
                        }`}
                        title={u.is_active ? 'Click to deactivate account' : 'Click to activate account'}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                        {u.is_active ? 'Active' : 'Disabled'}
                      </button>
                    </td>
                    <td className="py-2.5 px-3.5 text-zinc-500 font-mono text-[11px]">
                      {formatUtc(u.created_at, 'yyyy-MM-dd')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {usersList.length < usersTotal && (
              <div className="p-3 border-t border-zinc-800/60 text-center">
                <button
                  type="button"
                  onClick={loadMoreUsers}
                  disabled={loadingMoreUsers}
                  className="px-3 py-1.5 text-[11px] font-mono text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 border border-zinc-800 rounded-md transition disabled:opacity-50"
                >
                  {loadingMoreUsers
                    ? 'Loading...'
                    : `Load more (${usersList.length} of ${usersTotal})`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: MANAGED APPS & SITES */}
      {activeTab === 'apps' && (
        <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 shadow-2xl overflow-hidden">
          <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/40">
            <div>
              <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-zinc-400" />
                Managed Applications & Web Properties
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Register managed apps and URLs that customers can select when reporting issues.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setAppFormError(null);
                setIsAddAppOpen(true);
              }}
              className="px-3 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              Register App
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase tracking-wider text-[10px] font-mono">
                <tr>
                  <th className="py-2.5 px-3.5">App Name</th>
                  <th className="py-2.5 px-3.5">Code</th>
                  <th className="py-2.5 px-3.5">Base URL</th>
                  <th className="py-2.5 px-3.5">Status</th>
                  <th className="py-2.5 px-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 font-medium">
                {appsList.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-zinc-500 font-mono text-xs">
                      No applications registered yet. Click "Register App" to create one.
                    </td>
                  </tr>
                ) : (
                  appsList.map((app) => (
                    <tr key={app.id} className="hover:bg-zinc-800/30 transition">
                      <td className="py-2.5 px-3.5 font-semibold text-zinc-100">{app.name}</td>
                      <td className="py-2.5 px-3.5 font-mono text-zinc-400">
                        <span className="px-1.5 py-0.5 rounded bg-zinc-950 border border-zinc-800">
                          {app.code}
                        </span>
                      </td>
                      <td className="py-2.5 px-3.5 font-mono text-zinc-400">
                        {app.base_url ? (
                          <a
                            href={app.base_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-emerald-400 hover:underline flex items-center gap-1"
                          >
                            <span>{app.base_url}</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </a>
                        ) : (
                          <span className="text-zinc-600">-</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3.5 font-mono">
                        <span
                          className={`text-[11px] flex items-center gap-1 ${
                            app.is_active ? 'text-emerald-400' : 'text-zinc-500'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              app.is_active ? 'bg-emerald-500' : 'bg-zinc-600'
                            }`}
                          />
                          {app.is_active ? 'Active' : 'Disabled'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => openEditApp(app)}
                            aria-label={`Edit ${app.name}`}
                            className="p-1 text-zinc-500 hover:text-zinc-200 transition"
                            title="Edit App"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteApp(app.id)}
                            aria-label={`Delete ${app.name}`}
                            className="p-1 text-zinc-500 hover:text-rose-400 transition"
                            title="Delete App"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: TICKET TYPES & DYNAMIC CUSTOM FIELDS */}
      {activeTab === 'types' && (
        <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 shadow-2xl overflow-hidden">
          <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/40">
            <div>
              <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200 flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-zinc-400" />
                Ticket Types & Dynamic Custom Fields Engine
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Build custom schemas with text, numbers, dropdown options, and switches for each ticket category.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsAddTypeOpen(true)}
              className="px-3 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              New Ticket Type
            </button>
          </div>

          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            {typesList.length === 0 ? (
              <div className="col-span-2 py-8 text-center text-zinc-500 font-mono text-xs">
                No custom ticket types configured yet.
              </div>
            ) : (
              typesList.map((tt) => (
                <div
                  key={tt.id}
                  className="bg-zinc-950/60 border border-zinc-800 rounded-xl p-4 space-y-3"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-zinc-100">{tt.name}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
                          {tt.code}
                        </span>
                      </div>
                      {tt.description && (
                        <p className="text-xs text-zinc-400 mt-0.5">{tt.description}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => openEditType(tt)}
                        aria-label={`Edit ${tt.name}`}
                        className="text-zinc-500 hover:text-zinc-200 p-1 rounded transition"
                        title="Edit Ticket Type"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteTicketType(tt.id)}
                        aria-label={`Delete ${tt.name}`}
                        className="text-zinc-500 hover:text-rose-400 p-1 rounded transition"
                        title="Delete Ticket Type"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Fields list */}
                  <div className="pt-2 border-t border-zinc-800">
                    <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-2">
                      Custom Schema Fields ({tt.fields_schema.length})
                    </div>
                    {tt.fields_schema.length === 0 ? (
                      <div className="text-xs text-zinc-600 font-mono">No custom fields defined</div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {tt.fields_schema.map((f, idx) => (
                          <div
                            key={idx}
                            className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-2.5 py-1 rounded-md flex items-center gap-1.5"
                          >
                            <span className="font-medium text-zinc-200">{f.label}</span>
                            <span className="text-[10px] font-mono text-zinc-500 uppercase">
                              ({f.type})
                            </span>
                            {f.required && (
                              <span className="text-[9px] font-mono text-rose-400 uppercase">req</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 4: FAQ & BOT TRIAGE ENGINE */}
      {activeTab === 'faq' && (
        <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 shadow-2xl overflow-hidden">
          <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/40">
            <div>
              <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200 flex items-center gap-1.5">
                <HelpCircle className="w-3.5 h-3.5 text-zinc-400" />
                Frequently Asked Questions & Diagnostic Engine
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Configure self-service diagnostic articles and quick prompt options for the customer assistant.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsAddFaqOpen(true)}
              className="px-3 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              New FAQ Article
            </button>
          </div>

          <div className="divide-y divide-zinc-800/60">
            {faqList.length === 0 ? (
              <div className="py-8 text-center text-zinc-500 font-mono text-xs">
                No FAQ articles created yet. Click "New FAQ Article" to populate the engine.
              </div>
            ) : (
              faqList.map((item) => (
                <div key={item.id} className="p-4 hover:bg-zinc-800/20 transition space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono uppercase px-1.5 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-zinc-400">
                          {item.category}
                        </span>
                        <h3 className="text-sm font-semibold text-zinc-100">{item.question}</h3>
                      </div>
                      {item.keywords && (
                        <div className="text-[10px] font-mono text-zinc-500 mt-1">
                          Keywords: {item.keywords}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => openEditFaq(item)}
                        aria-label={`Edit FAQ article: ${item.question}`}
                        className="text-zinc-500 hover:text-zinc-200 p-1 rounded transition"
                        title="Edit FAQ Article"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteFaq(item.id)}
                        aria-label={`Delete FAQ article: ${item.question}`}
                        className="text-zinc-500 hover:text-rose-400 p-1 rounded transition"
                        title="Delete FAQ Article"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="text-xs text-zinc-300 prose prose-invert prose-sm max-w-none bg-zinc-950/40 p-3 rounded-lg border border-zinc-800">
                    <ReactMarkdown>{item.answer}</ReactMarkdown>
                  </div>

                  {item.quick_replies && item.quick_replies.length > 0 && (
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                      <span className="text-zinc-500">Drill-down prompts:</span>
                      {item.quick_replies.map((reply, rIdx) => (
                        <span key={rIdx} className="px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300">
                          {reply}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 5: OVERVIEW (METRICS & SLA) */}
      {activeTab === 'overview' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-zinc-500">Total Tickets</div>
              <div className="text-xl font-bold font-mono text-zinc-100 mt-1">{summary.total_tickets}</div>
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-emerald-500">SLA Compliance</div>
              <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                {summary.sla_compliance_rate != null ? `${summary.sla_compliance_rate.toFixed(1)}%` : 'N/A'}
              </div>
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-rose-500">Breached SLA</div>
              <div className="text-xl font-bold font-mono text-rose-400 mt-1">{summary.sla_breached_count}</div>
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-blue-400">Active Queue</div>
              <div className="text-xl font-bold font-mono text-blue-300 mt-1">
                {summary.open_tickets + summary.in_progress_tickets}
              </div>
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-zinc-400">Resolved</div>
              <div className="text-xl font-bold font-mono text-zinc-300 mt-1">{summary.resolved_tickets}</div>
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800 p-3.5 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-amber-400">CSAT Average</div>
              <div className="text-xl font-bold font-mono text-amber-300 mt-1 flex items-center gap-1">
                <Star className="w-4 h-4 fill-amber-400 text-amber-400" />
                <span>
                  {summary.csat_average_score != null ? summary.csat_average_score.toFixed(1) : 'N/A'}
                </span>
              </div>
            </div>
          </div>

          {/* Performance Table */}
          <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 overflow-hidden shadow-2xl">
            <div className="p-3.5 border-b border-zinc-800 bg-zinc-900/40">
              <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                Staff Performance & Operational SLA
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-2.5 px-3.5">Specialist</th>
                    <th className="py-2.5 px-3.5">Assigned</th>
                    <th className="py-2.5 px-3.5">Resolved</th>
                    <th className="py-2.5 px-3.5">Avg Resolution Time</th>
                    <th className="py-2.5 px-3.5">CSAT</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {summary.agents_performance.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-6 text-center text-zinc-500">
                        No agent performance metrics logged yet.
                      </td>
                    </tr>
                  ) : (
                    summary.agents_performance.map((ap) => (
                      <tr key={ap.agent_id} className="hover:bg-zinc-800/30">
                        <td className="py-2.5 px-3.5 font-semibold text-zinc-200">{ap.name}</td>
                        <td className="py-2.5 px-3.5 text-zinc-400">{ap.assigned_count}</td>
                        <td className="py-2.5 px-3.5 text-emerald-400">{ap.resolved_count}</td>
                        <td className="py-2.5 px-3.5 text-zinc-400">
                          {ap.avg_resolution_time_minutes != null
                            ? `${ap.avg_resolution_time_minutes} mins`
                            : 'N/A'}
                        </td>
                        <td className="py-2.5 px-3.5 text-amber-400 flex items-center gap-1">
                          <Star className="w-3 h-3 fill-amber-400" />
                          <span>{ap.csat_avg != null ? ap.csat_avg.toFixed(1) : 'N/A'}</span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 6: MACROS */}
      {activeTab === 'canned' && (
        <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 shadow-2xl overflow-hidden">
          <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/40">
            <div>
              <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                Staff Canned Responses (Macros)
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Type <code className="text-emerald-400">/</code> in any ticket chat box to trigger these shortcuts.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsAddCannedOpen(true)}
              className="px-3 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              New Macro
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="py-2.5 px-3.5">Shortcut</th>
                  <th className="py-2.5 px-3.5">Title</th>
                  <th className="py-2.5 px-3.5">Content Preview</th>
                  <th className="py-2.5 px-3.5">Category</th>
                  <th className="py-2.5 px-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {cannedList.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-zinc-500 font-mono text-xs">
                      No macros configured yet. Click "New Macro" to create one.
                    </td>
                  </tr>
                ) : (
                  cannedList.map((macro) => (
                    <tr key={macro.id} className="hover:bg-zinc-800/30 transition">
                      <td className="py-2.5 px-3.5 font-bold text-emerald-400">{macro.shortcut}</td>
                      <td className="py-2.5 px-3.5 text-zinc-200">{macro.title}</td>
                      <td className="py-2.5 px-3.5 text-zinc-400 truncate max-w-xs">{macro.content}</td>
                      <td className="py-2.5 px-3.5">
                        <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-zinc-400">
                          {macro.category}
                        </span>
                      </td>
                      <td className="py-2.5 px-3.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => openEditCanned(macro)}
                            aria-label={`Edit macro ${macro.shortcut}`}
                            className="p-1 text-zinc-500 hover:text-zinc-200 transition"
                            title="Edit Macro"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteCanned(macro.id)}
                            aria-label={`Delete macro ${macro.shortcut}`}
                            className="p-1 text-zinc-500 hover:text-rose-400 transition"
                            title="Delete Macro"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODAL: Register App */}
      <Modal
        isOpen={isAddAppOpen}
        onClose={() => setIsAddAppOpen(false)}
        labelledBy="admin-add-app-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-md w-full shadow-2xl space-y-4"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-add-app-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <Globe className="w-4 h-4 text-zinc-400" />
                Register New Application / Site
              </h3>
              <button type="button" onClick={() => setIsAddAppOpen(false)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddApp} className="space-y-3">
              {appFormError && (
                <div
                  role="alert"
                  className="p-2.5 rounded-lg bg-rose-950/60 border border-rose-900 text-rose-300 text-xs flex items-start gap-2"
                >
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{appFormError}</span>
                </div>
              )}

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Application Name *
                </label>
                <input
                  type="text"
                  required
                  value={appName}
                  onChange={(e) => {
                    setAppName(e.target.value);
                    setAppFormError(null);
                  }}
                  placeholder="e.g. Cloud Portal Web"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Identifier Code (Unique) *
                </label>
                <input
                  type="text"
                  required
                  value={appCode}
                  onChange={(e) => {
                    setAppCode(e.target.value);
                    setAppFormError(null);
                  }}
                  placeholder="e.g. cloud_portal"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Base URL (optional)
                </label>
                <input
                  type="url"
                  value={appBaseUrl}
                  onChange={(e) => {
                    setAppBaseUrl(e.target.value);
                    setAppFormError(null);
                  }}
                  placeholder="https://cloud.example.com"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setIsAddAppOpen(false)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition"
                >
                  Save Application
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: New Ticket Type & Custom Fields Builder */}
      <Modal
        isOpen={isAddTypeOpen}
        onClose={() => setIsAddTypeOpen(false)}
        labelledBy="admin-add-type-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-xl w-full shadow-2xl space-y-4 my-8 max-h-[90vh] flex flex-col"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-add-type-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <Sliders className="w-4 h-4 text-zinc-400" />
                Configure Ticket Type & Dynamic Fields
              </h3>
              <button type="button" onClick={() => setIsAddTypeOpen(false)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddTicketType} className="space-y-3.5 overflow-y-auto flex-1 pr-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                    Type Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={typeName}
                    onChange={(e) => setTypeName(e.target.value)}
                    placeholder="e.g. Bug Report"
                    className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                    Type Code *
                  </label>
                  <input
                    type="text"
                    required
                    value={typeCode}
                    onChange={(e) => setTypeCode(e.target.value)}
                    placeholder="e.g. bug_report"
                    className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={typeDescription}
                  onChange={(e) => setTypeDescription(e.target.value)}
                  placeholder="e.g. Software defects and UI glitches"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              {/* Dynamic Form Builder */}
              <CustomFieldBuilder fields={typeFields} onChange={setTypeFields} />

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setIsAddTypeOpen(false)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition"
                >
                  Save Ticket Type
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: New FAQ Article */}
      <Modal
        isOpen={isAddFaqOpen}
        onClose={() => setIsAddFaqOpen(false)}
        labelledBy="admin-add-faq-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-lg w-full shadow-2xl space-y-4 my-8 max-h-[90vh] flex flex-col"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-add-faq-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <HelpCircle className="w-4 h-4 text-zinc-400" />
                Add FAQ Diagnostic Solution
              </h3>
              <button type="button" onClick={() => setIsAddFaqOpen(false)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddFaq} className="space-y-3 overflow-y-auto flex-1 pr-1">
              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Category *
                </label>
                <select
                  value={faqCategory}
                  onChange={(e) => setFaqCategory(e.target.value)}
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition capitalize"
                >
                  <option value="technical">Technical Support</option>
                  <option value="billing">Billing & Payment</option>
                  <option value="account">Account & Security</option>
                  <option value="general">General Platform</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Question / Problem Prompt *
                </label>
                <input
                  type="text"
                  required
                  value={faqQuestion}
                  onChange={(e) => setFaqQuestion(e.target.value)}
                  placeholder="e.g. How to resolve 502 Bad Gateway?"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Diagnostic Answer (Markdown supported) *
                </label>
                <textarea
                  rows={4}
                  required
                  value={faqAnswer}
                  onChange={(e) => setFaqAnswer(e.target.value)}
                  placeholder="Step 1: Check upstream service..."
                  className="w-full text-xs p-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition resize-none font-mono"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Keywords Index (comma-separated, optional)
                </label>
                <input
                  type="text"
                  value={faqKeywords}
                  onChange={(e) => setFaqKeywords(e.target.value)}
                  placeholder="502, nginx, gateway, timeout"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Drill-down Quick Prompts (comma-separated, optional)
                </label>
                <input
                  type="text"
                  value={faqQuickRepliesStr}
                  onChange={(e) => setFaqQuickRepliesStr(e.target.value)}
                  placeholder="Still timeout, Server restart failed, Check cluster"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setIsAddFaqOpen(false)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition"
                >
                  Save FAQ Article
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: New Macro */}
      <Modal
        isOpen={isAddCannedOpen}
        onClose={() => setIsAddCannedOpen(false)}
        labelledBy="admin-add-canned-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-md w-full shadow-2xl space-y-4"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-add-canned-title" className="text-sm font-semibold text-zinc-100">Create Staff Response Macro</h3>
              <button type="button" onClick={() => setIsAddCannedOpen(false)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddCanned} className="space-y-3">
              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Shortcut (e.g. /refund)</label>
                <input
                  type="text"
                  required
                  value={shortcut}
                  onChange={(e) => setShortcut(e.target.value)}
                  placeholder="/refund"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition font-mono"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Title</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Refund Notice"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Category</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                >
                  <option value="greeting">Greeting</option>
                  <option value="troubleshooting">Troubleshooting</option>
                  <option value="billing">Billing</option>
                  <option value="closing">Closing</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Content</label>
                <textarea
                  rows={3}
                  required
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="We have processed your request..."
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none resize-none transition"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setIsAddCannedOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-medium text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg shadow-sm transition"
                >
                  Save Shortcut
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: Edit App */}
      <Modal
        isOpen={editingApp !== null}
        onClose={() => setEditingApp(null)}
        labelledBy="admin-edit-app-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-md w-full shadow-2xl space-y-4"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-edit-app-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <Globe className="w-4 h-4 text-zinc-400" />
                Edit Application / Site
              </h3>
              <button type="button" onClick={() => setEditingApp(null)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateApp} className="space-y-3">
              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Application Name *
                </label>
                <input
                  type="text"
                  required
                  value={editAppName}
                  onChange={(e) => setEditAppName(e.target.value)}
                  placeholder="e.g. Cloud Portal Web"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Identifier Code (Unique) *
                </label>
                <input
                  type="text"
                  required
                  value={editAppCode}
                  onChange={(e) => setEditAppCode(e.target.value)}
                  placeholder="e.g. cloud_portal"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Base URL (optional)
                </label>
                <input
                  type="url"
                  value={editAppBaseUrl}
                  onChange={(e) => setEditAppBaseUrl(e.target.value)}
                  placeholder="https://cloud.example.com"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div className="pt-1">
                <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-400 font-mono">
                  <input
                    type="checkbox"
                    checked={editAppActive}
                    onChange={(e) => setEditAppActive(e.target.checked)}
                    className="rounded bg-zinc-950 border-zinc-800 text-emerald-500 focus:ring-0"
                  />
                  Active (Available for issue reporting)
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setEditingApp(null)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition"
                >
                  Update Application
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: Edit Ticket Type & Custom Fields */}
      <Modal
        isOpen={editingType !== null}
        onClose={() => setEditingType(null)}
        labelledBy="admin-edit-type-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-xl w-full shadow-2xl space-y-4 my-8 max-h-[90vh] flex flex-col"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-edit-type-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <Sliders className="w-4 h-4 text-zinc-400" />
                Edit Ticket Type & Schema Fields
              </h3>
              <button type="button" onClick={() => setEditingType(null)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateTicketType} className="space-y-3.5 overflow-y-auto flex-1 pr-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                    Type Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={editTypeName}
                    onChange={(e) => setEditTypeName(e.target.value)}
                    placeholder="e.g. Bug Report"
                    className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                    Type Code *
                  </label>
                  <input
                    type="text"
                    required
                    value={editTypeCode}
                    onChange={(e) => setEditTypeCode(e.target.value)}
                    placeholder="e.g. bug_report"
                    className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={editTypeDescription}
                  onChange={(e) => setEditTypeDescription(e.target.value)}
                  placeholder="e.g. Software defects and UI glitches"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div className="pt-1">
                <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-400 font-mono">
                  <input
                    type="checkbox"
                    checked={editTypeActive}
                    onChange={(e) => setEditTypeActive(e.target.checked)}
                    className="rounded bg-zinc-950 border-zinc-800 text-emerald-500 focus:ring-0"
                  />
                  Active (Available when opening tickets)
                </label>
              </div>

              {/* Dynamic Form Builder */}
              <CustomFieldBuilder fields={editTypeFields} onChange={setEditTypeFields} />

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setEditingType(null)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition"
                >
                  Update Ticket Type
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: Edit FAQ Article */}
      <Modal
        isOpen={editingFaq !== null}
        onClose={() => setEditingFaq(null)}
        labelledBy="admin-edit-faq-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-lg w-full shadow-2xl space-y-4 my-8 max-h-[90vh] flex flex-col"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-edit-faq-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <HelpCircle className="w-4 h-4 text-zinc-400" />
                Edit FAQ Diagnostic Solution
              </h3>
              <button type="button" onClick={() => setEditingFaq(null)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateFaq} className="space-y-3 overflow-y-auto flex-1 pr-1">
              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Category *
                </label>
                <select
                  value={editFaqCategory}
                  onChange={(e) => setEditFaqCategory(e.target.value)}
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition capitalize"
                >
                  <option value="technical">Technical Support</option>
                  <option value="billing">Billing & Payment</option>
                  <option value="account">Account & Security</option>
                  <option value="general">General Platform</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Question / Problem Prompt *
                </label>
                <input
                  type="text"
                  required
                  value={editFaqQuestion}
                  onChange={(e) => setEditFaqQuestion(e.target.value)}
                  placeholder="e.g. How to resolve 502 Bad Gateway?"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Diagnostic Answer (Markdown supported) *
                </label>
                <textarea
                  rows={4}
                  required
                  value={editFaqAnswer}
                  onChange={(e) => setEditFaqAnswer(e.target.value)}
                  placeholder="Step 1: Check upstream service..."
                  className="w-full text-xs p-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition resize-none font-mono"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Keywords Index (comma-separated, optional)
                </label>
                <input
                  type="text"
                  value={editFaqKeywords}
                  onChange={(e) => setEditFaqKeywords(e.target.value)}
                  placeholder="502, nginx, gateway, timeout"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                  Drill-down Quick Prompts (comma-separated, optional)
                </label>
                <input
                  type="text"
                  value={editFaqQuickRepliesStr}
                  onChange={(e) => setEditFaqQuickRepliesStr(e.target.value)}
                  placeholder="Still timeout, Server restart failed, Check cluster"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 font-mono focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div className="pt-1">
                <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-400 font-mono">
                  <input
                    type="checkbox"
                    checked={editFaqActive}
                    onChange={(e) => setEditFaqActive(e.target.checked)}
                    className="rounded bg-zinc-950 border-zinc-800 text-emerald-500 focus:ring-0"
                  />
                  Active in Bot Engine
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setEditingFaq(null)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition"
                >
                  Update FAQ Article
                </button>
              </div>
            </form>
      </Modal>

      {/* MODAL: Edit Macro */}
      <Modal
        isOpen={editingCanned !== null}
        onClose={() => setEditingCanned(null)}
        labelledBy="admin-edit-canned-title"
        className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50"
        panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl p-5 max-w-md w-full shadow-2xl space-y-4"
      >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <h3 id="admin-edit-canned-title" className="text-sm font-semibold text-zinc-100">Edit Staff Response Macro</h3>
              <button type="button" onClick={() => setEditingCanned(null)} aria-label="Close dialog" className="text-zinc-400 hover:text-zinc-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateCanned} className="space-y-3">
              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Shortcut (e.g. /refund)</label>
                <input
                  type="text"
                  required
                  value={editShortcut}
                  onChange={(e) => setEditShortcut(e.target.value)}
                  placeholder="/refund"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition font-mono"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Title</label>
                <input
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  placeholder="Refund Notice"
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Category</label>
                <select
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                >
                  <option value="greeting">Greeting</option>
                  <option value="troubleshooting">Troubleshooting</option>
                  <option value="billing">Billing</option>
                  <option value="closing">Closing</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">Content</label>
                <textarea
                  rows={3}
                  required
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  placeholder="We have processed your request..."
                  className="w-full text-xs p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none resize-none transition"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setEditingCanned(null)}
                  className="px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction !== null}
                  className="px-3.5 py-1.5 text-xs font-medium text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg shadow-sm transition"
                >
                  Update Shortcut
                </button>
              </div>
            </form>
      </Modal>
    </div>
  );
};
