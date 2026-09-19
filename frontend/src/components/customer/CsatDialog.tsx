import React, { useState } from 'react';
import { Star, X, CheckCircle } from 'lucide-react';
import { csatApi } from '../../api/client';

interface Props {
  ticketId: number;
  ticketTitle: string;
  isOpen: boolean;
  onClose: () => void;
  onSubmitted?: () => void;
}

export const CsatDialog: React.FC<Props> = ({ ticketId, ticketTitle, isOpen, onClose, onSubmitted }) => {
  const [rating, setRating] = useState<number>(5);
  const [hoverRating, setHoverRating] = useState<number>(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  React.useEffect(() => {
    if (isOpen) {
      setSubmitted(false);
      setRating(5);
      setComment('');
    }
  }, [isOpen, ticketId]);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await csatApi.submit(ticketId, { score: rating, comment });
      setSubmitted(true);
      setTimeout(() => {
        if (onSubmitted) onSubmitted();
        onClose();
      }, 1500);
    } catch (err) {
      console.error('Failed to submit CSAT', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl max-w-md w-full p-5 relative animate-in fade-in zoom-in-95 duration-150">
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-200 p-1 rounded-md hover:bg-zinc-800 transition"
        >
          <X className="w-4 h-4" />
        </button>

        {submitted ? (
          <div className="text-center py-6">
            <div className="w-10 h-10 bg-emerald-950/80 border border-emerald-800 text-emerald-400 rounded-full flex items-center justify-center mx-auto mb-3">
              <CheckCircle className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">Thank You For Your Feedback</h3>
            <p className="text-xs text-zinc-400 mt-1">Your rating has been recorded.</p>
          </div>
        ) : (
          <div>
            <div className="text-center mb-4">
              <div className="w-9 h-9 bg-zinc-800 text-zinc-300 rounded-lg border border-zinc-700/60 flex items-center justify-center mx-auto mb-2.5">
                <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
              </div>
              <h3 className="text-sm font-semibold text-zinc-100">Resolution Feedback</h3>
              <p className="text-xs text-zinc-400 mt-0.5 truncate max-w-xs mx-auto">
                Ticket: <span className="font-mono text-zinc-300">{ticketTitle}</span>
              </p>
            </div>

            {/* Stars */}
            <div className="flex justify-center gap-2 mb-4">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onMouseEnter={() => setHoverRating(star)}
                  onMouseLeave={() => setHoverRating(0)}
                  onClick={() => setRating(star)}
                  className="p-1 hover:scale-105 transition focus:outline-none"
                >
                  <Star
                    className={`w-6 h-6 ${
                      (hoverRating || rating) >= star
                        ? 'text-amber-400 fill-amber-400'
                        : 'text-zinc-700'
                    }`}
                  />
                </button>
              ))}
            </div>

            {/* Comment */}
            <div className="mb-4">
              <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                Comments (Optional)
              </label>
              <textarea
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Share any additional feedback regarding your resolution..."
                className="w-full text-xs p-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none resize-none transition"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="w-1/2 py-2 px-3 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition"
              >
                Dismiss
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleSubmit}
                className="w-1/2 py-2 px-3 text-xs font-medium text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg shadow-sm transition disabled:opacity-50"
              >
                {submitting ? 'Submitting...' : 'Submit Rating'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
