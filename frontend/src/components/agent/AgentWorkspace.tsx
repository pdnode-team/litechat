import React, { useCallback, useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { ticketsApi, messagesApi, usersApi } from '../../api/client';
import { Ticket, Message, AttachmentItem, TicketStatus, TicketPriority, User } from '../../types';
import { TicketWebSocketClient } from '../../api/websocket';
import { MessageBubble } from '../chat/MessageBubble';
import { ChatInput } from '../chat/ChatInput';
import { StatusBadge } from '../common/StatusBadge';
import { PriorityChip } from '../common/PriorityChip';
import { SlaCountdown } from '../common/SlaCountdown';
import { UserAvatar } from '../common/UserAvatar';
import {
  Inbox,
  UserCheck,
  Clock,
  Search,
  CheckCircle,
  Shield,
  User as UserIcon,
  Globe,
  ExternalLink,
  Sliders,
} from 'lucide-react';
import { formatUtc } from '../../utils/datetime';
import { apiErrorMessage } from '../../utils/errors';
import { useToast } from '../common/Toast';

/** Rows fetched per "load more" step. */
const PAGE_SIZE = 25;
/** Messages fetched initially and per "load earlier" step. */
const MESSAGE_PAGE_SIZE = 100;

const TICKET_CATEGORIES = ['technical', 'billing', 'account', 'general'] as const;

/** Inline editor for a ticket's descriptive fields. */
const TicketDetailsEditor: React.FC<{
  ticket: Ticket;
  onCancel: () => void;
  onSave: (changes: { title: string; description: string; category: string; tags: string }) => void;
}> = ({ ticket, onCancel, onSave }) => {
  const [title, setTitle] = useState(ticket.title);
  const [description, setDescription] = useState(ticket.description);
  const [category, setCategory] = useState<string>(ticket.category);
  const [tags, setTags] = useState(ticket.tags ?? '');

  const dirty =
    title !== ticket.title ||
    description !== ticket.description ||
    category !== ticket.category ||
    tags !== (ticket.tags ?? '');

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ title: title.trim(), description: description.trim(), category, tags });
      }}
      className="border-b border-zinc-800 bg-zinc-900/40 p-3 space-y-2.5"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <label className="block">
          <span className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Title</span>
          <input
            type="text"
            required
            minLength={3}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 focus:border-zinc-600 focus:outline-none"
          />
        </label>

        <label className="block">
          <span className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 focus:border-zinc-600 focus:outline-none capitalize"
          >
            {TICKET_CATEGORIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="block">
        <span className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
          Description
        </span>
        <textarea
          required
          minLength={5}
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full text-xs p-2.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 focus:border-zinc-600 focus:outline-none resize-none"
        />
      </label>

      <label className="block">
        <span className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
          Tags (comma separated)
        </span>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="checkout, payment"
          className="w-full text-xs px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 focus:border-zinc-600 focus:outline-none"
        />
      </label>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!dirty}
          className="px-3 py-1.5 text-xs font-medium rounded-md bg-zinc-100 hover:bg-white text-zinc-950 transition disabled:opacity-40"
        >
          Save changes
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-xs font-medium rounded-md border border-zinc-700 text-zinc-300 hover:bg-zinc-800 transition"
        >
          Cancel
        </button>
        <span className="text-[10px] font-mono text-zinc-500 ml-auto">
          An entry is added to the ticket history when you save.
        </span>
      </div>
    </form>
  );
};

export const AgentWorkspace: React.FC = () => {
  const { user } = useAuth();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketsTotal, setTicketsTotal] = useState(0);
  const [loadingMoreTickets, setLoadingMoreTickets] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesTotal, setMessagesTotal] = useState(0);
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [loadingTickets, setLoadingTickets] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [queueTab, setQueueTab] = useState<'all' | 'mine' | 'unassigned' | 'urgent'>('all');
  const [typingUsers, setTypingUsers] = useState<string[]>([]);
  const [agentsList, setAgentsList] = useState<User[]>([]);
  const [editing, setEditing] = useState(false);
  const { showSuccess, showError } = useToast();

  const wsClientRef = useRef<TicketWebSocketClient | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const selectedTicketRef = useRef<number | null>(null);

  // Lets the stable callbacks below see how much is already loaded.
  const loadedTicketsRef = useRef(0);
  useEffect(() => {
    loadedTicketsRef.current = tickets.length;
  }, [tickets]);

  // 1. Fetch Tickets
  // Reads the current selection from a ref so the callback stays stable: making
  // it depend on `selectedTicket` would retrigger the effect on every refresh.
  const fetchTickets = useCallback(async () => {
    try {
      // Refetch what is already on screen (plus a page) so new tickets appear
      // without discarding pages the agent already loaded.
      const limit = Math.max(PAGE_SIZE, loadedTicketsRef.current);
      const page = await ticketsApi.list({ limit, offset: 0 });
      setTickets(page.items);
      setTicketsTotal(page.total);
      const currentId = selectedTicketRef.current;
      if (currentId === null && page.items.length > 0) {
        setSelectedTicket(page.items[0]);
      } else if (currentId !== null) {
        const updated = page.items.find((t) => t.id === currentId);
        if (updated) setSelectedTicket(updated);
      }
    } catch (err) {
      console.error('Failed to load tickets', err);
    } finally {
      setLoadingTickets(false);
    }
  }, []);

  const loadMoreTickets = async () => {
    setLoadingMoreTickets(true);
    try {
      const page = await ticketsApi.list({ limit: PAGE_SIZE, offset: tickets.length });
      setTickets((prev) => {
        const seen = new Set(prev.map((t) => t.id));
        return [...prev, ...page.items.filter((t) => !seen.has(t.id))];
      });
      setTicketsTotal(page.total);
    } catch (err) {
      console.error('Failed to load more tickets', err);
    } finally {
      setLoadingMoreTickets(false);
    }
  };

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets, user?.id]);

  // Load available staff specialists for assignment
  useEffect(() => {
    // Assignable staff only: the full user list is administrator-only, so an
    // agent calling /api/users would get a 403 and the picker would stay empty.
    usersApi
      .listAssignable()
      .then(setAgentsList)
      .catch(console.warn);
  }, []);

  // 2. Fetch Messages and Setup WebSocket
  const selectedTicketId = selectedTicket?.id ?? null;

  useEffect(() => {
    if (selectedTicketId === null) return;
    const currentTicketId = selectedTicketId;
    selectedTicketRef.current = currentTicketId;
    setTypingUsers([]);
    setLoadingMessages(true);

    messagesApi
      .list(currentTicketId, { limit: MESSAGE_PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (selectedTicketRef.current === currentTicketId) {
          setMessages(page.items);
          setMessagesTotal(page.total);
          setLoadingMessages(false);
          setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        }
      })
      .catch((err) => {
        if (selectedTicketRef.current === currentTicketId) {
          console.error('Failed to load messages', err);
          setLoadingMessages(false);
        }
      });

    if (wsClientRef.current) {
      wsClientRef.current.disconnect();
    }

    const ws = new TicketWebSocketClient(currentTicketId);
    ws.connect();
    ws.onMessage((data) => {
      if (selectedTicketRef.current !== currentTicketId) return;
      if (data.type === 'new_message' && data.message) {
        setMessages((prev) => (prev.some((m) => m.id === data.message.id) ? prev : [...prev, data.message]));
        setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
      } else if (data.type === 'ticket_updated' && data.ticket) {
        setSelectedTicket(data.ticket);
        setTickets((prev) => prev.map((t) => (t.id === data.ticket.id ? data.ticket : t)));
      } else if (data.type === 'typing') {
        if (data.is_typing) {
          setTypingUsers((prev) => (prev.includes(data.user_name) ? prev : [...prev, data.user_name]));
        } else {
          setTypingUsers((prev) => prev.filter((n) => n !== data.user_name));
        }
      }
    });

    wsClientRef.current = ws;

    return () => {
      ws.disconnect();
    };
  }, [selectedTicketId, fetchTickets, user?.id]);

  // 3. Send Message / Whisper
  const handleSendMessage = async (
    content: string,
    type: 'text' | 'whisper',
    attachments?: AttachmentItem[]
  ) => {
    if (!selectedTicket) return;
    try {
      await messagesApi.send(selectedTicket.id, {
        content,
        message_type: type,
        attachments,
      });
      fetchTickets();
    } catch (err) {
      console.error('Failed to send message', err);
    }
  };

  const handleTyping = (isTyping: boolean) => {
    wsClientRef.current?.sendTyping(isTyping);
  };

  /** Fetch the next older page of the conversation and prepend it. */
  const loadOlderMessages = async () => {
    if (selectedTicketId === null) return;
    const currentId = selectedTicketId;
    setLoadingOlderMessages(true);
    try {
      const page = await messagesApi.list(currentId, {
        limit: MESSAGE_PAGE_SIZE,
        offset: messages.length,
      });
      if (selectedTicketRef.current !== currentId) return;
      setMessages((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        // The page arrives in chronological order, so it can be prepended as-is.
        return [...page.items.filter((m) => !seen.has(m.id)), ...prev];
      });
      setMessagesTotal(page.total);
    } catch (err) {
      console.error('Failed to load earlier messages', err);
    } finally {
      setLoadingOlderMessages(false);
    }
  };

  // Status & Assignment Actions
  const handleStatusChange = async (newStatus: TicketStatus) => {
    if (!selectedTicket) return;
    try {
      const updated = await ticketsApi.updateStatus(selectedTicket.id, newStatus);
      setSelectedTicket(updated);
      fetchTickets();
      showSuccess(`Ticket marked ${newStatus.replace('_', ' ')}`);
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to update the ticket status.'));
    }
  };

  const handleAssignToMe = async () => {
    if (!selectedTicket || !user) return;
    try {
      const updated = await ticketsApi.assign(selectedTicket.id, user.id);
      setSelectedTicket(updated);
      fetchTickets();
      showSuccess('Ticket assigned to you');
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to assign the ticket.'));
    }
  };

  const handleAssignAgent = async (agentIdStr: string) => {
    if (!selectedTicket) return;
    try {
      const agentId = agentIdStr ? Number(agentIdStr) : null;
      const updated = await ticketsApi.assign(selectedTicket.id, agentId);
      setSelectedTicket(updated);
      fetchTickets();
      showSuccess(
        updated.assigned_agent
          ? `Assigned to ${updated.assigned_agent.full_name}`
          : 'Ticket released back to the queue'
      );
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to update the ticket assignment.'));
    }
  };

  const handlePriorityChange = async (newPriority: TicketPriority) => {
    if (!selectedTicket) return;
    try {
      const updated = await ticketsApi.updatePriority(selectedTicket.id, newPriority);
      setSelectedTicket(updated);
      fetchTickets();
      showSuccess(`Priority set to ${newPriority}`);
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to update the ticket priority.'));
    }
  };

  const handleEditTicket = async (changes: {
    title: string;
    description: string;
    category: string;
    tags: string;
  }) => {
    if (!selectedTicket) return;
    try {
      const updated = await ticketsApi.update(selectedTicket.id, changes);
      setSelectedTicket(updated);
      fetchTickets();
      setEditing(false);
      showSuccess('Ticket details saved');
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to save the ticket details.'));
    }
  };

  // Filter queue
  const filteredTickets = tickets.filter((t) => {
    const matchesSearch =
      !searchQuery ||
      t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.ticket_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (t.customer?.full_name && t.customer.full_name.toLowerCase().includes(searchQuery.toLowerCase()));

    if (!matchesSearch) return false;

    if (queueTab === 'mine') return t.assigned_agent_id === user?.id;
    if (queueTab === 'unassigned') return !t.assigned_agent_id;
    if (queueTab === 'urgent') return t.priority === 'urgent' || t.priority === 'high';
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 w-full flex-1 flex flex-col">
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden flex flex-1 h-[calc(100vh-130px)] shadow-2xl">
        {/* Column 1: Ticket Queue List */}
        <div className="w-80 lg:w-[22rem] border-r border-zinc-800 flex flex-col bg-zinc-950/50 flex-shrink-0">
          {/* Header & Tabs */}
          <div className="p-3 border-b border-zinc-800 bg-zinc-900/40">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <Inbox className="w-3.5 h-3.5 text-zinc-400" />
                <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">Inbox Queue</h2>
              </div>
              <span className="text-[10px] font-mono text-zinc-400 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded">
                {filteredTickets.length} active
              </span>
            </div>

            {/* Queue Filter Tabs */}
            <div className="grid grid-cols-4 gap-1 p-0.5 bg-zinc-950 rounded-lg mb-2 text-[11px] font-mono border border-zinc-800">
              <button
                type="button"
                onClick={() => setQueueTab('all')}
                className={`py-1 rounded transition ${
                  queueTab === 'all' ? 'bg-zinc-800 text-zinc-100 font-medium' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setQueueTab('mine')}
                className={`py-1 rounded transition ${
                  queueTab === 'mine' ? 'bg-zinc-800 text-zinc-100 font-medium' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Mine
              </button>
              <button
                type="button"
                onClick={() => setQueueTab('unassigned')}
                className={`py-1 rounded transition ${
                  queueTab === 'unassigned' ? 'bg-zinc-800 text-zinc-100 font-medium' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Queue
              </button>
              <button
                type="button"
                onClick={() => setQueueTab('urgent')}
                className={`py-1 rounded transition ${
                  queueTab === 'urgent' ? 'bg-zinc-800 text-rose-400 font-medium' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Urgent
              </button>
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search tickets, customers..."
                className="w-full text-xs pl-8 pr-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-600 transition"
              />
            </div>
          </div>

          {/* Ticket Queue List */}
          <div className="flex-1 overflow-y-auto divide-y divide-zinc-800/60">
            {loadingTickets ? (
              <div className="p-6 text-center text-xs font-mono text-zinc-500">Loading queue...</div>
            ) : filteredTickets.length === 0 ? (
              <div className="p-8 text-center text-xs text-zinc-500">No active tickets in queue.</div>
            ) : (
              filteredTickets.map((ticket) => {
                const isSelected = selectedTicket?.id === ticket.id;
                return (
                  <div
                    key={ticket.id}
                    role="button"
                    tabIndex={0}
                    aria-current={isSelected}
                    onClick={() => setSelectedTicket(ticket)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setSelectedTicket(ticket);
                      }
                    }}
                    className={`p-3 cursor-pointer transition select-none focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-zinc-500 ${
                      isSelected
                        ? 'bg-zinc-800/70 border-l-2 border-zinc-200'
                        : 'hover:bg-zinc-900/60'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-mono font-semibold text-zinc-300">
                        {ticket.ticket_code}
                      </span>
                      <StatusBadge status={ticket.status} />
                    </div>

                    <h3 className="text-xs font-medium text-zinc-200 line-clamp-1 mb-1">
                      {ticket.title}
                    </h3>

                    <div className="flex items-center justify-between text-[11px] text-zinc-400 mb-1">
                      <span className="truncate max-w-[120px]">
                        {ticket.customer?.full_name || 'Customer'}
                      </span>
                      <PriorityChip priority={ticket.priority} />
                    </div>

                    <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 mt-1">
                      <SlaCountdown
                        dueAt={ticket.first_response_due_at}
                        completedAt={ticket.first_responded_at}
                        label="Resp"
                      />
                      <span>{formatUtc(ticket.created_at, 'MMM d, HH:mm')}</span>
                    </div>
                  </div>
                );
              })
            )}

            {!loadingTickets && tickets.length < ticketsTotal && (
              <div className="p-3 border-t border-zinc-800/60">
                <button
                  type="button"
                  onClick={loadMoreTickets}
                  disabled={loadingMoreTickets}
                  className="w-full py-1.5 text-[11px] font-mono text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 rounded-md transition disabled:opacity-50"
                >
                  {loadingMoreTickets
                    ? 'Loading...'
                    : `Load more (${tickets.length} of ${ticketsTotal})`}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Column 2: Center Conversation Stream */}
        {selectedTicket ? (
          <div className="flex-1 flex flex-col bg-zinc-950/70 min-w-0">
            {/* Action Bar Header */}
            <div className="p-3 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/30 flex-wrap gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-mono font-bold text-zinc-200">
                  {selectedTicket.ticket_code}
                </span>
                <StatusBadge status={selectedTicket.status} size="sm" />
                <h2 className="text-sm font-semibold text-zinc-100 truncate max-w-xs md:max-w-md">
                  {selectedTicket.title}
                </h2>
              </div>

              {/* Quick Action Buttons */}
              <div className="flex items-center gap-1.5 font-mono text-xs">
                <button
                  type="button"
                  onClick={() => setEditing((prev) => !prev)}
                  aria-expanded={editing}
                  className="flex items-center gap-1 px-2.5 py-1 border border-zinc-700 hover:bg-zinc-800 text-zinc-300 rounded-md text-xs font-medium transition"
                >
                  <Sliders className="w-3.5 h-3.5" />
                  {editing ? 'Close editor' : 'Edit details'}
                </button>
                {!selectedTicket.assigned_agent_id ? (
                  <button
                    type="button"
                    onClick={handleAssignToMe}
                    className="flex items-center gap-1 px-2.5 py-1 bg-zinc-100 hover:bg-white text-zinc-950 rounded-md text-xs font-medium transition shadow-sm"
                  >
                    <UserCheck className="w-3.5 h-3.5" />
                    Claim Ticket
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleStatusChange('in_progress')}
                    disabled={selectedTicket.status === 'in_progress'}
                    className="px-2.5 py-1 border border-zinc-700 hover:bg-zinc-800 text-zinc-300 rounded-md text-xs font-medium disabled:opacity-40 transition"
                  >
                    In Progress
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => handleStatusChange('resolved')}
                  disabled={selectedTicket.status === 'resolved'}
                  className="flex items-center gap-1 px-2.5 py-1 bg-emerald-950/60 border border-emerald-800/80 text-emerald-400 hover:bg-emerald-900/60 rounded-md text-xs font-medium transition disabled:opacity-40"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  Resolve
                </button>
              </div>
            </div>

            {/* Inline ticket editor: title/description/category/tags were
                previously write-once, with no way to correct a typo. */}
            {editing && (
              <TicketDetailsEditor
                ticket={selectedTicket}
                onCancel={() => setEditing(false)}
                onSave={handleEditTicket}
              />
            )}

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-1">
              {!loadingMessages && messages.length < messagesTotal && (
                <div className="pb-3 text-center">
                  <button
                    type="button"
                    onClick={loadOlderMessages}
                    disabled={loadingOlderMessages}
                    className="px-3 py-1.5 text-[11px] font-mono text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 border border-zinc-800 rounded-md transition disabled:opacity-50"
                  >
                    {loadingOlderMessages
                      ? 'Loading...'
                      : `Load earlier messages (${messagesTotal - messages.length} more)`}
                  </button>
                </div>
              )}

              {loadingMessages ? (
                <div className="text-center py-12 text-xs font-mono text-zinc-500">Loading conversation...</div>
              ) : messages.length === 0 ? (
                <div className="text-center py-12 text-xs font-mono text-zinc-500">No messages yet.</div>
              ) : (
                messages.map((msg) => (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    currentUserId={user?.id}
                    currentUserRole={user?.role}
                  />
                ))
              )}

              {/* Typing indicator */}
              {typingUsers.length > 0 && (
                <div className="flex items-center gap-2 text-xs text-zinc-400 py-1 italic font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                  <span>{typingUsers.join(', ')} is typing...</span>
                </div>
              )}

              <div ref={chatBottomRef} />
            </div>

            {/* Chat Input */}
            <ChatInput
              onSendMessage={handleSendMessage}
              onTyping={handleTyping}
              userRole={user?.role}
            />
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-zinc-500">
            <Inbox className="w-8 h-8 text-zinc-600 mb-2" />
            <h3 className="text-sm font-medium text-zinc-300">No Ticket Selected</h3>
            <p className="text-xs text-zinc-500 mt-1 max-w-xs">
              Select an inquiry from the queue to review context and triage.
            </p>
          </div>
        )}

        {/* Column 3: Right Details & SLA Sidebar */}
        {selectedTicket && (
          <div className="w-72 lg:w-80 bg-zinc-950/60 border-l border-zinc-800 p-3.5 overflow-y-auto space-y-3.5 flex-shrink-0">
            {/* Customer Info Card */}
            <div className="bg-zinc-900/60 p-3 rounded-lg border border-zinc-800">
              <h3 className="text-[10px] font-mono font-semibold text-zinc-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <UserIcon className="w-3 h-3 text-zinc-400" />
                Customer
              </h3>
              <div className="flex items-center gap-2.5">
                <UserAvatar name={selectedTicket.customer?.full_name || 'Customer'} size="md" />
                <div className="min-w-0">
                  <div className="text-xs font-medium text-zinc-200 truncate">
                    {selectedTicket.customer?.full_name || 'Customer'}
                  </div>
                  <div className="text-[11px] font-mono text-zinc-500 truncate">
                    {selectedTicket.customer?.email || 'customer@example.com'}
                  </div>
                </div>
              </div>
            </div>

            {/* Ticket Management Controls */}
            <div className="bg-zinc-900/60 p-3 rounded-lg border border-zinc-800 space-y-2.5">
              <h3 className="text-[10px] font-mono font-semibold text-zinc-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                <Shield className="w-3 h-3 text-zinc-400" />
                Attributes
              </h3>

              {/* Status Selector */}
              <div>
                <label className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Status</label>
                <select
                  value={selectedTicket.status}
                  onChange={(e) => handleStatusChange(e.target.value as TicketStatus)}
                  className="w-full text-xs p-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 font-mono focus:border-zinc-600 focus:outline-none transition"
                >
                  <option value="open">Open</option>
                  <option value="pending">Pending</option>
                  <option value="in_progress">In Progress</option>
                  <option value="resolved">Resolved</option>
                  <option value="closed">Closed</option>
                </select>
              </div>

              {/* Priority Selector */}
              <div>
                <label className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Priority</label>
                <select
                  value={selectedTicket.priority}
                  onChange={(e) => handlePriorityChange(e.target.value as TicketPriority)}
                  className="w-full text-xs p-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 font-mono focus:border-zinc-600 focus:outline-none transition"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>

              {/* Assignee Selector */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-[10px] font-mono uppercase text-zinc-500">Assignee</label>
                  {!selectedTicket.assigned_agent_id && (
                    <button
                      type="button"
                      onClick={handleAssignToMe}
                      className="text-[10px] font-mono text-zinc-300 hover:text-white underline"
                    >
                      Assign to me
                    </button>
                  )}
                </div>
                <select
                  value={selectedTicket.assigned_agent_id ? String(selectedTicket.assigned_agent_id) : ''}
                  onChange={(e) => handleAssignAgent(e.target.value)}
                  className="w-full text-xs p-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 font-mono focus:border-zinc-600 focus:outline-none transition"
                >
                  <option value="">Unassigned</option>
                  {agentsList.map((ag) => (
                    <option key={ag.id} value={ag.id}>
                      {ag.full_name} ({ag.role.toUpperCase()})
                    </option>
                  ))}
                </select>
              </div>

              {/* Tags */}
              <div>
                <label className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Tags</label>
                <div className="flex flex-wrap gap-1">
                  {selectedTicket.tags ? (
                    selectedTicket.tags.split(',').map((tag, idx) => (
                      <span
                        key={idx}
                        className="bg-zinc-950 text-zinc-400 font-mono text-[10px] px-1.5 py-0.5 rounded border border-zinc-800"
                      >
                        #{tag.trim()}
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] font-mono text-zinc-600">No tags</span>
                  )}
                </div>
              </div>
            </div>

            {/* Application & Origin Target */}
            {(selectedTicket.app || selectedTicket.target_url) && (
              <div className="bg-zinc-900/60 p-3 rounded-lg border border-zinc-800 space-y-2">
                <h3 className="text-[10px] font-mono font-semibold text-zinc-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                  <Globe className="w-3 h-3 text-zinc-400" />
                  Application & Origin
                </h3>

                {selectedTicket.app && (
                  <div>
                    <div className="text-[10px] font-mono text-zinc-500 uppercase">Target App</div>
                    <div className="text-xs font-mono font-medium text-zinc-200 mt-0.5 flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-zinc-950 border border-zinc-800">
                        {selectedTicket.app.name}
                      </span>
                      <span className="text-[10px] text-zinc-500 font-normal">
                        ({selectedTicket.app.code})
                      </span>
                    </div>
                  </div>
                )}

                {selectedTicket.target_url && (
                  <div className="pt-1">
                    <div className="text-[10px] font-mono text-zinc-500 uppercase">Page / URL</div>
                    <a
                      href={selectedTicket.target_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-mono text-emerald-400 hover:text-emerald-300 hover:underline flex items-center gap-1 mt-0.5 break-all"
                    >
                      <span className="truncate">{selectedTicket.target_url}</span>
                      <ExternalLink className="w-3 h-3 flex-shrink-0" />
                    </a>
                  </div>
                )}
              </div>
            )}

            {/* Ticket Type & Custom Fields */}
            {(selectedTicket.ticket_type || (selectedTicket.custom_fields && Object.keys(selectedTicket.custom_fields).length > 0)) && (
              <div className="bg-zinc-900/60 p-3 rounded-lg border border-zinc-800 space-y-2">
                <h3 className="text-[10px] font-mono font-semibold text-zinc-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                  <Sliders className="w-3 h-3 text-zinc-400" />
                  Custom Properties
                </h3>

                {selectedTicket.ticket_type && (
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-zinc-500">Type</span>
                    <span className="px-1.5 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-zinc-200 font-medium">
                      {selectedTicket.ticket_type.name}
                    </span>
                  </div>
                )}

                {selectedTicket.custom_fields && Object.keys(selectedTicket.custom_fields).length > 0 && (
                  <div className="pt-1.5 border-t border-zinc-800/80 space-y-1.5">
                    {Object.entries(selectedTicket.custom_fields).map(([k, v]) => (
                      <div key={k} className="flex items-start justify-between gap-2 text-xs font-mono">
                        <span className="text-zinc-500 capitalize">{k.replace('_', ' ')}</span>
                        <span className="text-zinc-200 font-medium text-right break-all">
                          {typeof v === 'boolean'
                            ? v ? 'Yes' : 'No'
                            : typeof v === 'string' && (v.startsWith('http://') || v.startsWith('https://'))
                            ? (
                              <a href={v} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline inline-flex items-center gap-1">
                                Link <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            )
                            : String(v || '-')}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* SLA Compliance Targets */}
            <div className="bg-zinc-900/60 p-3 rounded-lg border border-zinc-800 space-y-2">
              <h3 className="text-[10px] font-mono font-semibold text-zinc-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                <Clock className="w-3 h-3 text-zinc-400" />
                SLA Targets
              </h3>

              <div className="space-y-1">
                <div className="text-[10px] font-mono text-zinc-500 uppercase">First Response</div>
                <SlaCountdown
                  dueAt={selectedTicket.first_response_due_at}
                  completedAt={selectedTicket.first_responded_at}
                  label="Target"
                />
              </div>

              <div className="space-y-1 pt-1.5 border-t border-zinc-800/80">
                <div className="text-[10px] font-mono text-zinc-500 uppercase">Resolution</div>
                <SlaCountdown
                  dueAt={selectedTicket.resolution_due_at}
                  completedAt={selectedTicket.resolved_at}
                  label="Target"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
