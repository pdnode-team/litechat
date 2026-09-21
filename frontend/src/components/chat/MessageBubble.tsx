import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AttachmentItem, Message, UserRole } from '../../types';
import { Shield, Lock, FileText, Download } from 'lucide-react';
import { UserAvatar } from '../common/UserAvatar';
import { formatUtc } from '../../utils/datetime';
import api from '../../api/client';

const apiPath = (url: string): string => (url.startsWith('/api/') ? url.slice(4) : url);

const AttachmentView: React.FC<{ att: AttachmentItem }> = ({ att }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const isImage = att.file_type === 'image' && !att.name.toLowerCase().endsWith('.svg');

  useEffect(() => {
    if (!isImage) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .get<Blob>(apiPath(att.url), { responseType: 'blob' })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setImageSrc(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setImageSrc(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [att.url, isImage]);

  const download = async (event: React.MouseEvent) => {
    event.preventDefault();
    try {
      const res = await api.get<Blob>(apiPath(att.url), { responseType: 'blob' });
      const href = URL.createObjectURL(res.data);
      const link = document.createElement('a');
      link.href = href;
      link.download = att.name;
      link.rel = 'noopener';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } catch {
      // The toast lives outside this leaf; a failed click is still visible
      // because the file simply does not download.
    }
  };

  if (isImage && imageSrc) {
    return (
      <div>
        <img src={imageSrc} alt={att.name} className="max-h-48 rounded object-contain" />
        <span className="text-[10px] font-mono mt-1 block truncate text-zinc-400">
          {att.name} ({Math.round(att.size / 1024)} KB)
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={download}
      className="flex items-center gap-2 font-mono text-xs text-zinc-200 hover:underline w-full text-left"
    >
      <FileText className="w-3.5 h-3.5 opacity-70" />
      <span className="truncate flex-1">{att.name}</span>
      <Download className="w-3.5 h-3.5 opacity-70" />
    </button>
  );
};

interface Props {
  message: Message;
  currentUserId?: number;
  currentUserRole?: UserRole;
}

export const MessageBubble: React.FC<Props> = ({ message, currentUserId, currentUserRole }) => {
  const isMine = Boolean(currentUserId && String(message.sender_id) === String(currentUserId));
  const isSystem = message.sender_role === 'system' || message.message_type === 'action_card';
  const isWhisper = message.message_type === 'whisper';
  const isStaff = message.sender_role === 'agent' || message.sender_role === 'admin';

  // Strict RBAC: Customer must NEVER see internal whisper notes
  if (isWhisper && currentUserRole === 'customer') {
    return null;
  }

  // System or Action Card message
  if (isSystem) {
    return (
      <div className="flex justify-center my-3">
        <div className="bg-zinc-900 border border-zinc-800 text-zinc-400 text-[11px] font-mono px-3.5 py-1 rounded-full shadow-sm flex items-center gap-1.5">
          <Shield className="w-3 h-3 text-zinc-500" />
          <span>{message.content}</span>
          <span className="text-zinc-600 ml-1">
            {formatUtc(message.created_at, 'HH:mm')}
          </span>
        </div>
      </div>
    );
  }

  // Internal Whisper Note (Staff only)
  if (isWhisper) {
    return (
      <div className="my-3 px-4 py-3 bg-amber-950/20 border border-amber-800/50 rounded-xl shadow-sm">
        <div className="flex items-center justify-between mb-1.5 text-[11px] font-mono text-amber-400">
          <div className="flex items-center gap-1.5 font-medium">
            <Lock className="w-3.5 h-3.5 text-amber-500" />
            <span className="tracking-wider uppercase text-[10px] font-semibold">INTERNAL NOTE (STAFF ONLY)</span>
            <span className="text-amber-500/80 font-normal">· {message.sender_name}</span>
          </div>
          <span className="text-amber-500/70 text-[10px]">
            {formatUtc(message.created_at, 'HH:mm')}
          </span>
        </div>
        <div className="text-xs text-amber-200/95 prose prose-invert prose-sm max-w-none leading-relaxed">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  // Current user's own message (Right side: clean bubble, dark harmonious palette, no glaring white)
  if (isMine) {
    return (
      <div className="flex flex-col items-end my-2.5 ml-auto max-w-[80%] sm:max-w-[70%]">
        <div className="bg-zinc-800 border border-zinc-700/80 text-zinc-100 px-4 py-2.5 rounded-2xl rounded-tr-sm shadow-sm text-xs leading-relaxed selection:bg-zinc-700">
          <div className="prose prose-sm max-w-none break-words text-zinc-100 prose-invert">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>

          {/* Attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-2 pt-2 border-t border-zinc-700/80 flex flex-col gap-1.5">
              {message.attachments.map((att, idx) => (
                <div key={idx} className="rounded p-1.5 border border-zinc-700 bg-zinc-900 text-xs">
                  <AttachmentView att={att} />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 mt-1 pr-1 text-[10px] font-mono text-zinc-500">
          <span>{formatUtc(message.created_at, 'HH:mm')}</span>
        </div>
      </div>
    );
  }

  // Opposite party's message (Left side: avatar, sender name, role badge, timestamp, dark bubble)
  return (
    <div className="flex gap-2.5 my-2.5 flex-row items-start max-w-[80%] sm:max-w-[70%]">
      <UserAvatar name={message.sender_name} size="sm" />

      <div className="flex flex-col items-start min-w-0">
        <div className="flex items-center gap-1.5 mb-1 px-0.5 text-[11px]">
          <span className="font-medium text-zinc-200">
            {message.sender_name}
          </span>
          {isStaff && (
            <span className="bg-zinc-800 text-zinc-400 font-mono text-[9px] px-1.5 py-0.5 rounded border border-zinc-700/60 leading-none">
              STAFF
            </span>
          )}
          <span className="text-zinc-500 font-mono text-[10px]">
            {formatUtc(message.created_at, 'HH:mm')}
          </span>
        </div>

        <div className="bg-zinc-900 border border-zinc-800/90 text-zinc-100 px-4 py-2.5 rounded-2xl rounded-tl-sm shadow-sm text-xs leading-relaxed">
          <div className="prose prose-sm max-w-none break-words text-zinc-100 prose-invert">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>

          {/* Attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-2 pt-2 border-t border-zinc-800 flex flex-col gap-1.5">
              {message.attachments.map((att, idx) => (
                <div key={idx} className="rounded p-1.5 border border-zinc-800 bg-zinc-950 text-xs">
                  <AttachmentView att={att} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
