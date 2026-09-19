import React, { useEffect, useId, useRef } from 'react';

/**
 * A reusable accessible dialog.
 *
 * It owns the behaviour that every modal in the app used to re-implement (or
 * lacked entirely): the `dialog`/`aria-modal` semantics, a focus trap, focus
 * restore, Escape-to-close and backdrop-click-to-close. Visual styling stays
 * with the caller through `className` (the fixed overlay) and `panelClassName`
 * (the panel itself), so existing markup keeps its look.
 */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

const getFocusableElements = (container: HTMLElement): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));

export interface ModalProps {
  isOpen: boolean;
  /** Called for Escape, a backdrop click, or an explicit close button. */
  onClose: () => void;
  /** Id of the visible heading that names this dialog; used by `aria-labelledby`. */
  labelledBy?: string;
  /** Fallback accessible name when `labelledBy` points at nothing usable. */
  label?: string;
  /** Classes for the fixed overlay. Defaults to the standard dark blurred backdrop. */
  className?: string;
  /** Classes for the dialog panel. */
  panelClassName?: string;
  children: React.ReactNode;
}

/** Standard overlay used by every dialog in the app. */
const DEFAULT_OVERLAY_CLASSNAME =
  'fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50';

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  labelledBy,
  label,
  className = DEFAULT_OVERLAY_CLASSNAME,
  panelClassName = '',
  children,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const generatedId = useId();
  const fallbackTitleId = `${generatedId}-title`;
  const titleId = labelledBy ?? (label ? fallbackTitleId : undefined);

  // Move focus into the dialog on open and hand it back to the trigger on close.
  useEffect(() => {
    if (!isOpen) return;

    previouslyFocusedRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const panel = panelRef.current;
    if (panel) {
      const [firstFocusable] = getFocusableElements(panel);
      (firstFocusable ?? panel).focus();
    }

    return () => {
      previouslyFocusedRef.current?.focus();
    };
  }, [isOpen]);

  // Escape closes; Tab and Shift+Tab cycle inside the dialog.
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      const panel = panelRef.current;
      if (!panel) return;

      const focusable = getFocusableElements(panel);
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const isInside = active instanceof HTMLElement && panel.contains(active);

      if (event.shiftKey) {
        if (!isInside || active === first) {
          event.preventDefault();
          last.focus();
        }
      } else if (!isInside || active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className={className}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={panelClassName}
        onClick={(event) => event.stopPropagation()}
      >
        {!labelledBy && label && (
          <h2 id={fallbackTitleId} className="sr-only">
            {label}
          </h2>
        )}
        {children}
      </div>
    </div>
  );
};
