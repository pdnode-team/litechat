import React, { useCallback, useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { inboxApi } from '../../api/client';
import { InboxItem } from '../../types';
import { useRealtimeEvent } from '../../context/RealtimeContext';
import { openTicket } from '../../utils/ticketNav';
import { formatUtc } from '../../utils/datetime';

export const InboxBell: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<InboxItem[]>([]);
  const [unread, setUnread] = useState(0);

  const refresh = useCallback(async () => {
    const page = await inboxApi.list({ limit: 20, offset: 0 });
    setItems(page.items);
    setUnread(page.items.filter((item) => !item.read_at).length);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useRealtimeEvent(
    ['ticket_created', 'ticket_updated', 'message_created', 'csat_submitted', 'user_updated', 'sla_first_response', 'sla_resolution'],
    () => {
      void refresh();
    },
  );

  const handleClick = async (item: InboxItem) => {
    if (!item.read_at) {
      await inboxApi.markRead({ ids: [item.id] });
      await refresh();
    }
    if (item.ticket_id) openTicket(item.ticket_id);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 rounded-md"
        aria-label="Notifications"
      >
        <Bell className="w-3.5 h-3.5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] px-0.5 rounded-full bg-emerald-500 text-[9px] text-zinc-950 font-bold flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-80 max-h-80 overflow-y-auto bg-zinc-950 border border-zinc-800 rounded-lg shadow-xl z-40">
          <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
            <span className="text-[10px] font-mono uppercase text-zinc-500">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                className="text-[10px] text-zinc-400 hover:text-zinc-100"
                onClick={async () => {
                  await inboxApi.markRead({ all: true });
                  await refresh();
                }}
              >
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 && <p className="p-3 text-[11px] text-zinc-500">No notifications yet.</p>}
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => void handleClick(item)}
              className={`w-full text-left px-3 py-2 border-b border-zinc-900 hover:bg-zinc-900 ${item.read_at ? 'opacity-70' : ''}`}
            >
              <p className="text-xs text-zinc-200">{item.title}</p>
              <p className="text-[10px] text-zinc-500 font-mono">{formatUtc(item.created_at, 'MMM d, HH:mm')}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
