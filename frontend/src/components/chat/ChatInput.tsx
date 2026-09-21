import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Lock, MessageSquare, X } from 'lucide-react';
import { AttachmentItem, CannedResponse, UserRole } from '../../types';
import { cannedApi, messagesApi } from '../../api/client';
import { apiErrorMessage } from '../../utils/errors';
import { useToast } from '../common/Toast';

interface Props {
  onSendMessage: (content: string, type: 'text' | 'whisper', attachments?: AttachmentItem[]) => Promise<void>;
  onTyping?: (isTyping: boolean) => void;
  userRole?: UserRole;
  disabled?: boolean;
}

export const ChatInput: React.FC<Props> = ({ onSendMessage, onTyping, userRole, disabled }) => {
  const { showError } = useToast();
  const [content, setContent] = useState('');
  const [messageType, setMessageType] = useState<'text' | 'whisper'>('text');
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  
  // Canned responses popup
  const [cannedList, setCannedList] = useState<CannedResponse[]>([]);
  const [showCanned, setShowCanned] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onTypingRef = useRef(onTyping);
  onTypingRef.current = onTyping;

  const canWhisper = userRole === 'agent' || userRole === 'admin';

  useEffect(() => {
    if (canWhisper) {
      cannedApi.listAll().then(setCannedList).catch(console.warn);
    }
  }, [canWhisper]);

  useEffect(() => {
    return () => {
      if (typingTimerRef.current) {
        clearTimeout(typingTimerRef.current);
      }
      onTypingRef.current?.(false);
    };
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setContent(val);

    // If starts with "/" or contains "/", trigger canned menu
    if (val.startsWith('/') && canWhisper) {
      setShowCanned(true);
    } else {
      setShowCanned(false);
    }

    if (onTyping) {
      onTyping(true);
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      typingTimerRef.current = setTimeout(() => {
        onTyping(false);
      }, 1500);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const item = await messagesApi.upload(files[i]);
        setAttachments((prev) => [...prev, item]);
      }
    } catch (err) {
      showError(apiErrorMessage(err, 'File upload failed.'));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleSelectCanned = (item: CannedResponse) => {
    setContent(item.content);
    setShowCanned(false);
  };

  const handleSend = async () => {
    const trimmed = content.trim();
    if (!trimmed && attachments.length === 0) return;

    setSending(true);
    try {
      await onSendMessage(trimmed, messageType, attachments.length > 0 ? attachments : undefined);
      setContent('');
      setAttachments([]);
      setShowCanned(false);
      setMessageType('text');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={`p-3 border-t relative ${messageType === 'whisper' ? 'bg-amber-950/20 border-amber-900/60' : 'bg-zinc-950/90 border-zinc-800'}`}>
      {/* Canned Responses Popover Menu */}
      {showCanned && cannedList.length > 0 && (
        <div className="absolute bottom-full left-4 mb-2 w-80 bg-zinc-900 rounded-lg shadow-2xl border border-zinc-800 py-1.5 z-50 max-h-60 overflow-y-auto">
          <div className="px-3 py-1 text-[10px] font-mono text-zinc-500 uppercase tracking-wider flex items-center gap-1 border-b border-zinc-800/80 mb-1">
            <span>QUICK SHORTCUTS</span>
          </div>
          {cannedList
            .filter((c) => !content || c.shortcut.toLowerCase().includes(content.toLowerCase()) || c.title.toLowerCase().includes(content.toLowerCase()))
            .map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => handleSelectCanned(c)}
                className="w-full text-left px-3 py-1.5 hover:bg-zinc-800/80 flex items-center justify-between group transition"
              >
                <div>
                  <span className="font-mono text-xs text-zinc-200 group-hover:text-white mr-2">{c.shortcut}</span>
                  <span className="text-xs text-zinc-400 group-hover:text-zinc-300">{c.title}</span>
                </div>
                <span className="text-[10px] font-mono text-zinc-500 uppercase bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                  {c.category}
                </span>
              </button>
            ))}
        </div>
      )}

      {/* Tabs for Staff: Public Reply vs Whisper Note */}
      {canWhisper && (
        <div className="flex items-center gap-2 mb-2 font-mono text-xs">
          <button
            type="button"
            onClick={() => setMessageType('text')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition text-[11px] ${
              messageType === 'text'
                ? 'bg-zinc-800 text-zinc-100 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <MessageSquare className="w-3 h-3" />
            Public Reply
          </button>
          <button
            type="button"
            onClick={() => setMessageType('whisper')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition text-[11px] ${
              messageType === 'whisper'
                ? 'bg-amber-950/60 text-amber-300 border border-amber-800/80 font-medium'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Lock className="w-3 h-3" />
            Internal Note
          </button>

          <div className="ml-auto">
            <button
              type="button"
              onClick={() => setShowCanned(!showCanned)}
              className="text-[11px] font-mono text-zinc-400 hover:text-zinc-200 flex items-center gap-1 px-2 py-0.5 rounded hover:bg-zinc-800 transition"
            >
              <span>/ Shortcuts</span>
            </button>
          </div>
        </div>
      )}

      {/* Attachments Preview Bar */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 font-mono text-[11px]">
          {attachments.map((att, idx) => (
            <div
              key={idx}
              className="flex items-center gap-1.5 bg-zinc-900 text-zinc-300 px-2 py-1 rounded border border-zinc-800"
            >
              <span className="truncate max-w-[140px]">{att.name}</span>
              <button
                type="button"
                onClick={() => setAttachments(attachments.filter((_, i) => i !== idx))}
                aria-label={`Remove attachment ${att.name}`}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className="flex items-end gap-2">
        <textarea
          rows={2}
          value={content}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          disabled={disabled || sending}
          placeholder={
            disabled
              ? 'This ticket is closed.'
              : messageType === 'whisper'
              ? 'Write an internal note only visible to team members...'
              : 'Type a message... (Enter to send, Shift+Enter for newline)'
          }
          className={`w-full p-2.5 text-xs rounded-lg border focus:outline-none transition resize-none ${
            messageType === 'whisper'
              ? 'border-amber-800/80 bg-zinc-900 text-amber-100 placeholder-amber-700/60 focus:border-amber-600'
              : 'border-zinc-800 bg-zinc-900 text-zinc-100 placeholder-zinc-600 focus:border-zinc-600'
          }`}
        />

        <div className="flex items-center gap-1 flex-shrink-0">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            multiple
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || uploading}
            aria-label="Attach file"
            title="Attach file"
            className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || sending || (!content.trim() && attachments.length === 0)}
            aria-label={messageType === 'whisper' ? 'Send internal note' : 'Send message'}
            className={`p-2 rounded-lg font-medium shadow-sm transition disabled:opacity-40 ${
              messageType === 'whisper'
                ? 'bg-amber-500 text-zinc-950 hover:bg-amber-400'
                : 'bg-zinc-100 text-zinc-950 hover:bg-white'
            }`}
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
