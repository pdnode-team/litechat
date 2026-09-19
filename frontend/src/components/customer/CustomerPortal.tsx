import React, { useCallback, useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { ticketsApi, messagesApi } from '../../api/client';
import { Ticket, Message, AttachmentItem } from '../../types';
import { TicketWebSocketClient } from '../../api/websocket';
import { MessageBubble } from '../chat/MessageBubble';
import { ChatInput } from '../chat/ChatInput';
import { StatusBadge } from '../common/StatusBadge';
import { PriorityChip } from '../common/PriorityChip';
import { SlaCountdown } from '../common/SlaCountdown';
import { Navbar } from '../layout/Navbar';
import { CreateTicketModal } from './CreateTicketModal';
import { FaqAssistantModal } from './FaqAssistantModal';
import { CsatDialog } from './CsatDialog';
import {
  Plus,
  Search,
  MessageSquare,
  CheckCircle2,
  Star,
  RefreshCw,
  Bot,
} from 'lucide-react';
import { formatUtc } from '../../utils/datetime';
import { apiErrorMessage } from '../../utils/errors';
import { useToast } from '../common/Toast';
import { useRealtimeEvent } from '../../context/RealtimeContext';

/** Rows fetched per "load more" step. */
const PAGE_SIZE = 25;
/** Messages fetched initially and per "load earlier" step. */
const MESSAGE_PAGE_SIZE = 100;

export const CustomerPortal: React.FC = () => {
  const { user } = useAuth();
  const { showSuccess, showError } = useToast();
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
  const [statusFilter, setStatusFilter] = useState('all');

  const [isFaqOpen, setIsFaqOpen] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [escalateTitle, setEscalateTitle] = useState('');
  const [escalateDesc, setEscalateDesc] = useState('');
  const [isCsatOpen, setIsCsatOpen] = useState(false);
  const [typingUsers, setTypingUsers] = useState<string[]>([]);

  const wsClientRef = useRef<TicketWebSocketClient | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // Track the newest selection so a list refresh never resurrects a stale one.
  const selectedTicketRef = useRef<Ticket | null>(null);
  useEffect(() => {
    selectedTicketRef.current = selectedTicket;
  }, [selectedTicket]);

  // Lets the stable callbacks below see how much is already loaded.
  const loadedTicketsRef = useRef(0);
  useEffect(() => {
    loadedTicketsRef.current = tickets.length;
  }, [tickets]);

  const fetchTickets = useCallback(async () => {
    try {
      // Refetch everything currently on screen (plus a page) so new tickets
      // appear without discarding the pages the user already loaded.
      const limit = Math.max(PAGE_SIZE, loadedTicketsRef.current);
      const page = await ticketsApi.list({ limit, offset: 0 });
      setTickets(page.items);
      setTicketsTotal(page.total);
      const current = selectedTicketRef.current;
      if (!current && page.items.length > 0) {
        setSelectedTicket(page.items[0]);
      } else if (current) {
        const updated = page.items.find((t) => t.id === current.id);
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

  const selectedTicketId = selectedTicket?.id ?? null;

  // Live list: a status change or a reply from support updates the customer's
  // own ticket list immediately. Messages for the open ticket arrive on the
  // ticket socket, so this only refreshes the list to avoid double-appending.
  const liveRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleListRefresh = useCallback(() => {
    if (liveRefreshTimer.current) clearTimeout(liveRefreshTimer.current);
    liveRefreshTimer.current = setTimeout(() => {
      void fetchTickets();
    }, 350);
  }, [fetchTickets]);

  useEffect(
    () => () => {
      if (liveRefreshTimer.current) clearTimeout(liveRefreshTimer.current);
    },
    []
  );

  useRealtimeEvent(['ticket_created', 'ticket_updated', 'message_created'], (event) => {
    if (event.type === 'ticket_updated' && event.reason === 'status_changed') {
      showSuccess('Your ticket status changed');
    }
    scheduleListRefresh();
  });

  useEffect(() => {
    if (selectedTicketId === null) return;

    const currentId = selectedTicketId;
    setLoadingMessages(true);
    setTypingUsers([]);
    messagesApi
      .list(currentId, { limit: MESSAGE_PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (selectedTicketRef.current?.id === currentId) {
          setMessages(page.items);
          setMessagesTotal(page.total);
          setLoadingMessages(false);
          setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        }
      })
      .catch((err) => {
        if (selectedTicketRef.current?.id === currentId) {
          console.error('Failed to fetch messages', err);
          setLoadingMessages(false);
        }
      });

    if (wsClientRef.current) {
      wsClientRef.current.disconnect();
    }

    const ws = new TicketWebSocketClient(currentId);
    ws.connect();
    ws.onMessage((data) => {
      if (data.type === 'new_message' && data.message) {
        if (data.message.message_type === 'whisper') return;
        setMessages((prev) => {
          if (prev.some((m) => m.id === data.message.id)) return prev;
          return [...prev, data.message];
        });
        setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
      } else if (data.type === 'ticket_updated' && data.ticket) {
        setSelectedTicket(data.ticket);
        fetchTickets();
      } else if (data.type === 'typing') {
        if (data.user_id !== user?.id) {
          setTypingUsers((prev) => {
            if (data.is_typing) {
              return prev.includes(data.user_name) ? prev : [...prev, data.user_name];
            } else {
              return prev.filter((name) => name !== data.user_name);
            }
          });
        }
      }
    });

    wsClientRef.current = ws;

    return () => {
      ws.disconnect();
    };
  }, [selectedTicketId, fetchTickets, user?.id]);

  const handleSendMessage = async (
    content: string,
    _type: 'text' | 'whisper' = 'text',
    attachments?: AttachmentItem[]
  ) => {
    if (!selectedTicket) return;
    try {
      const created = await messagesApi.send(selectedTicket.id, {
        content,
        message_type: 'text',
        attachments,
      });
      setMessages((prev) => {
        if (prev.some((m) => m.id === created.id)) return prev;
        return [...prev, created];
      });
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to send your message.'));
    }
  };

  const handleTyping = (isTyping: boolean) => {
    wsClientRef.current?.sendTyping(isTyping);
  };

  /** Fetch the next older page of the conversation and prepend it. */
  const loadOlderMessages = async () => {
    if (!selectedTicket) return;
    const currentId = selectedTicket.id;
    setLoadingOlderMessages(true);
    try {
      const page = await messagesApi.list(currentId, {
        limit: MESSAGE_PAGE_SIZE,
        offset: messages.length,
      });
      if (selectedTicketRef.current?.id !== currentId) return;
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

  const handleToggleClose = async () => {
    if (!selectedTicket) return;
    const isResolvedOrClosed = selectedTicket.status === 'closed' || selectedTicket.status === 'resolved';
    const newStatus = isResolvedOrClosed ? 'open' : 'resolved';
    try {
      const updated = await ticketsApi.updateStatus(selectedTicket.id, newStatus);
      setSelectedTicket(updated);
      fetchTickets();
      if (newStatus === 'resolved') {
        setIsCsatOpen(true);
      }
      showSuccess(newStatus === 'open' ? 'Ticket reopened' : 'Ticket marked resolved');
    } catch (err) {
      showError(apiErrorMessage(err, 'Failed to update the ticket status.'));
    }
  };

  const filteredTickets = tickets.filter((t) => {
    const matchesSearch =
      !searchQuery ||
      t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.ticket_code.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || t.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans selection:bg-zinc-700 selection:text-white">
      <Navbar
        systemLabel="LITECHAT // CLIENT PORTAL"
        badge="Customer"
        rightActions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsCreateOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 text-xs font-semibold rounded-md transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Ticket</span>
            </button>
            <button
              type="button"
              onClick={() => setIsFaqOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700 text-xs font-medium rounded-md transition shadow-sm"
            >
              <Bot className="w-3.5 h-3.5 text-emerald-400" />
              <span>Ask Assistant</span>
            </button>
          </div>
        }
      />

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 flex flex-col">
        {tickets.length === 0 && !loadingTickets ? (
          <div className="flex-1 bg-zinc-900/40 border border-zinc-800/80 rounded-xl flex flex-col items-center justify-center p-12 text-center shadow-2xl">
            <div className="w-12 h-12 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 mb-4">
              <Bot className="w-6 h-6 text-emerald-400" />
            </div>
            <h3 className="text-base font-semibold text-zinc-100">No support tickets found</h3>
            <p className="text-xs text-zinc-400 mt-1 max-w-md">
              Need assistance with an inquiry or platform issue? Query our automated diagnostic engine, or escalate directly to engineering support.
            </p>
            <div className="mt-5 flex items-center gap-3">
              <button
                type="button"
                onClick={() => setIsCreateOpen(true)}
                className="px-4 py-2 bg-zinc-100 hover:bg-white text-zinc-950 font-semibold text-xs rounded-lg transition shadow-sm flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Open New Ticket
              </button>
              <button
                type="button"
                onClick={() => setIsFaqOpen(true)}
                className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700 font-medium text-xs rounded-lg transition shadow-sm flex items-center gap-2"
              >
                <Bot className="w-4 h-4 text-emerald-400" />
                Ask Assistant & Solutions
              </button>
            </div>
          </div>
        ) : (
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden flex flex-1 h-[calc(100vh-130px)] shadow-2xl">
            {/* Left Column: Tickets List */}
            <div className="w-80 lg:w-96 border-r border-zinc-800 flex flex-col bg-zinc-950/50">
              <div className="p-3 border-b border-zinc-800">
                <div className="relative mb-2">
                  <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search ticket code or title..."
                    className="w-full text-xs pl-8 pr-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-600 transition"
                  />
                </div>

                <div className="flex gap-1 overflow-x-auto text-[11px] font-mono">
                  {['all', 'open', 'pending', 'in_progress', 'resolved', 'closed'].map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setStatusFilter(st)}
                      className={`px-2 py-0.5 rounded capitalize whitespace-nowrap transition ${
                        statusFilter === st
                          ? 'bg-zinc-800 text-zinc-100 font-medium border border-zinc-700'
                          : 'text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      {st.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tickets Items */}
              <div className="flex-1 overflow-y-auto divide-y divide-zinc-800/60">
                {loadingTickets ? (
                  <div className="p-6 text-center text-xs text-zinc-500 font-mono">Loading tickets...</div>
                ) : filteredTickets.length === 0 ? (
                  <div className="p-8 text-center text-xs text-zinc-500">
                    No tickets match filter.
                  </div>
                ) : (
                  filteredTickets.map((ticket) => {
                    const isSelected = selectedTicket?.id === ticket.id;
                    return (                      <div
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
                        <h3 className="text-xs font-medium text-zinc-200 line-clamp-1 mb-1.5">
                          {ticket.title}
                        </h3>
                        <div className="flex items-center justify-between text-[10px] text-zinc-500 font-mono">
                          <PriorityChip priority={ticket.priority} />
                          <span>{formatUtc(ticket.updated_at, 'MMM d, HH:mm')}</span>
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

            {/* Right Column: Active Ticket Thread */}
            {selectedTicket ? (
              <div className="flex-1 flex flex-col bg-zinc-950/70">
                {/* Header */}
                <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between flex-wrap gap-2 bg-zinc-900/30">
                  <div className="flex-1 min-w-[200px]">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono font-bold text-zinc-200">
                        {selectedTicket.ticket_code}
                      </span>
                      <StatusBadge status={selectedTicket.status} size="sm" />
                      <PriorityChip priority={selectedTicket.priority} />
                      <span className="text-[11px] font-mono text-zinc-500 uppercase">
                        {selectedTicket.category}
                      </span>
                    </div>
                    <h2 className="text-sm font-semibold text-zinc-100 line-clamp-1">
                      {selectedTicket.title}
                    </h2>
                  </div>

                  <div className="flex items-center gap-2">
                    <SlaCountdown
                      dueAt={selectedTicket.resolution_due_at}
                      completedAt={selectedTicket.resolved_at}
                      label="SLA Target"
                    />

                    {selectedTicket.status === 'resolved' && (
                      <button
                        type="button"
                        onClick={() => setIsCsatOpen(true)}
                        className="flex items-center gap-1 px-2.5 py-1 bg-amber-500 hover:bg-amber-400 text-zinc-950 rounded-md text-xs font-medium transition shadow-sm"
                      >
                        <Star className="w-3.5 h-3.5 fill-current" />
                        Rate Support
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={handleToggleClose}
                      className="flex items-center gap-1 px-2.5 py-1 border border-zinc-700 hover:bg-zinc-800 text-zinc-300 rounded-md text-xs font-medium transition"
                    >
                      {selectedTicket.status === 'closed' || selectedTicket.status === 'resolved' ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5" />
                          Reopen
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          Mark Resolved
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Conversation Stream */}
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
                    messages
                      .filter((m) => m.message_type !== 'whisper')
                      .map((msg) => (
                        <MessageBubble
                          key={msg.id}
                          message={msg}
                          currentUserId={user?.id}
                          currentUserRole={user?.role}
                        />
                      ))
                  )}

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
                  disabled={selectedTicket.status === 'closed'}
                />
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-zinc-500">
                <MessageSquare className="w-8 h-8 text-zinc-600 mb-2" />
                <h3 className="text-sm font-medium text-zinc-300">No Ticket Selected</h3>
                <p className="text-xs text-zinc-500 mt-1 max-w-xs">
                  Select a ticket from the list or create a new one.
                </p>
              </div>
            )}
          </div>
        )}
      </main>

      <FaqAssistantModal
        isOpen={isFaqOpen}
        onClose={() => setIsFaqOpen(false)}
        onEscalateToTicket={(title, desc) => {
          setEscalateTitle(title || '');
          setEscalateDesc(desc || '');
          setIsFaqOpen(false);
          setIsCreateOpen(true);
        }}
      />

      <CreateTicketModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onTicketCreated={(t) => {
          setTickets((prev) => [t, ...prev]);
          setSelectedTicket(t);
        }}
        initialTitle={escalateTitle}
        initialDescription={escalateDesc}
      />

      {selectedTicket && (
        <CsatDialog
          ticketId={selectedTicket.id}
          ticketTitle={selectedTicket.title}
          isOpen={isCsatOpen}
          onClose={() => setIsCsatOpen(false)}
        />
      )}
    </div>
  );
};
