import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { X, Search, Bot, HelpCircle, CornerDownRight, Sparkles, MessageSquarePlus } from 'lucide-react';
import { faqApi } from '../../api/client';
import { FaqItem, FaqQueryResult } from '../../types';
import { Modal } from '../common/Modal';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onEscalateToTicket: (initialTitle?: string, initialDescription?: string) => void;
}

export const FaqAssistantModal: React.FC<Props> = ({
  isOpen,
  onClose,
  onEscalateToTicket,
}) => {
  const [query, setQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [queryResult, setQueryResult] = useState<FaqQueryResult | null>(null);
  const [recentFaqs, setRecentFaqs] = useState<FaqItem[]>([]);
  const [selectedFaq, setSelectedFaq] = useState<FaqItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Start each session from the recommended list rather than the previous
    // search, which otherwise reappears every time the modal is reopened.
    setQuery('');
    setSelectedCategory(undefined);
    setQueryResult(null);
    setSelectedFaq(null);

    faqApi.listAll({ active_only: true })
      .then((items) => {
        setError(null);
        setRecentFaqs(items.slice(0, 8));
      })
      .catch((err) => {
        console.error('Failed to load initial FAQs', err);
        setError('Could not load help articles.');
      });
  }, [isOpen]);

  const handleSearch = async (textToSearch: string, categoryOverride?: string) => {
    if (!textToSearch.trim()) return;
    setLoading(true);
    const cat = categoryOverride !== undefined ? categoryOverride : selectedCategory;
    try {
      const result = await faqApi.query(textToSearch.trim(), cat);
      setError(null);
      setQueryResult(result);
      if (result.matches.length > 0) {
        setSelectedFaq(result.matches[0]);
      } else {
        setSelectedFaq(null);
      }
    } catch (err) {
      console.error('FAQ query failed', err);
      setError('The assistant could not search right now. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleEscalate = () => {
    onEscalateToTicket(
      query.trim() || selectedFaq?.question || 'Support inquiry',
      selectedFaq ? `User inquired regarding FAQ: "${selectedFaq.question}"\n\nProblem details:\n` : query
    );
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      labelledBy="faq-assistant-modal-title"
      className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
      panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl max-w-2xl w-full p-5 relative animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col"
    >
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-zinc-800 border border-zinc-700/60 flex items-center justify-center text-zinc-300">
              <Bot className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h2 id="faq-assistant-modal-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
                <span>Self-Service & Diagnostic Engine</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                  AI Triage
                </span>
              </h2>
              <p className="text-xs text-zinc-400">
                Instant solutions for common technical issues, billing questions, and system status.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="text-zinc-400 hover:text-zinc-200 p-1 rounded-md hover:bg-zinc-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search Bar */}
        <div className="pt-3 pb-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSearch(query);
            }}
            className="relative"
          >
            <Search className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Describe your issue (e.g. 502 gateway error, invoice download, reset password)..."
              className="w-full text-xs pl-9 pr-24 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none transition shadow-inner"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium rounded-md transition disabled:opacity-40"
            >
              {loading ? 'Searching...' : 'Ask Engine'}
            </button>
          </form>
          {error && (
            <p className="mt-2 text-[11px] text-rose-300 font-mono" role="alert">
              {error}
            </p>
          )}
        </div>

        {/* Category Pills */}
        <div className="flex items-center gap-1.5 pb-3 overflow-x-auto text-[11px] font-mono border-b border-zinc-800/80">
          <button
            type="button"
            onClick={() => {
              setSelectedCategory(undefined);
              if (query.trim()) handleSearch(query, '');
            }}
            className={`px-2.5 py-0.5 rounded transition ${
              !selectedCategory ? 'bg-zinc-800 text-zinc-100 font-medium' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            All Topics
          </button>
          {['technical', 'billing', 'account', 'general'].map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => {
                setSelectedCategory(cat);
                if (query.trim()) handleSearch(query, cat);
              }}
              className={`px-2.5 py-0.5 rounded transition capitalize ${
                selectedCategory === cat ? 'bg-zinc-800 text-zinc-100 font-medium' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Main Body */}
        <div className="flex-1 overflow-y-auto py-3 space-y-3.5 pr-1">
          {/* Query Results */}
          {queryResult && (
            <div className="space-y-3">
              <div className="text-xs font-mono text-zinc-400 flex items-center justify-between">
                <span>Matching Solutions ({queryResult.matches.length})</span>
                {queryResult.matches.length === 0 && (
                  <span className="text-zinc-500">No direct answers found</span>
                )}
              </div>

              {queryResult.matches.length > 0 ? (
                <div className="space-y-2.5">
                  {queryResult.matches.map((item) => (
                    <div
                      key={item.id}
                      onClick={() => setSelectedFaq(item)}
                      className={`p-3 rounded-lg border transition cursor-pointer ${
                        selectedFaq?.id === item.id
                          ? 'bg-zinc-950/90 border-zinc-600'
                          : 'bg-zinc-950/40 border-zinc-800 hover:border-zinc-700'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-xs font-medium text-zinc-100 flex items-center gap-1.5">
                          <HelpCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                          {item.question}
                        </span>
                        <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-500">
                          {item.category}
                        </span>
                      </div>

                      <div className="text-xs text-zinc-300 prose prose-invert prose-sm max-w-none line-clamp-3">
                        <ReactMarkdown>{item.answer}</ReactMarkdown>
                      </div>

                      {/* Drill-down prompt options */}
                      {item.quick_replies && item.quick_replies.length > 0 && (
                        <div className="mt-2.5 pt-2 border-t border-zinc-800 flex flex-wrap gap-1.5">
                          {item.quick_replies.map((reply, rIdx) => (
                            <button
                              key={rIdx}
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setQuery(reply);
                                handleSearch(reply);
                              }}
                              className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition flex items-center gap-1"
                            >
                              <CornerDownRight className="w-2.5 h-2.5" />
                              <span>{reply}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-lg bg-zinc-950/50 border border-zinc-800 text-center text-xs text-zinc-400">
                  <p>Our automated diagnostics did not find an article answering "{query}".</p>
                  <p className="mt-1 text-zinc-500">
                    You can immediately escalate this inquiry to our official human support engineering team below.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Popular / Recent Questions (If no active query result) */}
          {!queryResult && recentFaqs.length > 0 && (
            <div className="space-y-2.5">
              <div className="text-xs font-mono text-zinc-400">Recommended Frequently Asked Questions</div>
              <div className="grid grid-cols-1 gap-2">
                {recentFaqs.map((faq) => (
                  <div
                    key={faq.id}
                    onClick={() => {
                      setQuery(faq.question);
                      handleSearch(faq.question);
                    }}
                    className="p-2.5 rounded-lg bg-zinc-950/50 border border-zinc-800 hover:border-zinc-700 hover:bg-zinc-800/40 transition cursor-pointer flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <HelpCircle className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
                      <span className="text-xs text-zinc-200 truncate">{faq.question}</span>
                    </div>
                    <span className="text-[10px] font-mono text-zinc-500 uppercase px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800">
                      {faq.category}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ALWAYS PRESENT ESCALATION BANNER (Under bot answers) */}
        <div className="pt-3 border-t border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-950/80 p-3 rounded-lg border border-zinc-800">
          <div>
            <div className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>Still need human engineering support?</span>
            </div>
            <p className="text-[11px] text-zinc-400 mt-0.5">
              If the diagnostic solution did not resolve your issue, dispatch a verified official support ticket.
            </p>
          </div>

          <button
            type="button"
            onClick={handleEscalate}
            className="w-full sm:w-auto px-3.5 py-2 bg-zinc-100 hover:bg-white text-zinc-950 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-sm flex-shrink-0"
          >
            <MessageSquarePlus className="w-3.5 h-3.5" />
            <span>Create Official Ticket</span>
          </button>
        </div>
    </Modal>
  );
};
