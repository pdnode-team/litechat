import React, { useState } from 'react';
import { AlertCircle, Check } from 'lucide-react';
import type { CustomFieldDefinition, CustomFieldValue } from '../../types';

interface Props {
  field: CustomFieldDefinition;
  value: CustomFieldValue | undefined;
  /** Message from client-side validation, or from the server's 422 payload. */
  error?: string;
  onChange: (value: CustomFieldValue) => void;
  /** Runs client-side validation for this field as soon as the user leaves it. */
  onBlur?: () => void;
  disabled?: boolean;
}

/** Sentinel for the "Other" entry of a select; never sent to the API. */
const OTHER = '__other__';

const inputClass =
  'w-full text-xs px-2.5 py-1.5 bg-zinc-900 border rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none transition';

const borderFor = (hasError: boolean) =>
  hasError ? 'border-rose-800 focus:border-rose-600' : 'border-zinc-800 focus:border-zinc-500';

const optionsOf = (field: CustomFieldDefinition): string[] => field.options ?? [];

/**
 * One question of a dynamic ticket form.
 *
 * Choice fields support multi-select and an "Other" answer: an answer that is not
 * one of the configured options is the custom text, which is what gets stored, so
 * no extra bookkeeping is needed to round-trip it.
 */
export const CustomFieldInput: React.FC<Props> = ({
  field,
  value,
  error,
  onChange,
  onBlur,
  disabled = false,
}) => {
  const options = optionsOf(field);
  const inputId = `cf-${field.key}`;
  const describedBy = error ? `${inputId}-error` : field.help_text ? `${inputId}-help` : undefined;

  const stringValue = typeof value === 'string' ? value : typeof value === 'number' ? String(value) : '';
  const items = Array.isArray(value) ? value : [];
  const customItem = items.find((item) => !options.includes(item)) ?? '';

  // The "Other" control is only open once the customer picked it; an existing
  // custom answer reopens it so editing a saved answer shows the same form.
  const [otherOpen, setOtherOpen] = useState(() => stringValue !== '' && !options.includes(stringValue));
  const [otherChecked, setOtherChecked] = useState(() => customItem !== '');

  const common = {
    id: inputId,
    disabled,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy,
    onBlur,
  } as const;

  const renderControl = () => {
    switch (field.type) {
      case 'textarea':
        return (
          <textarea
            {...common}
            rows={3}
            value={stringValue}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder || ''}
            className={`${inputClass} ${borderFor(Boolean(error))} resize-none`}
          />
        );

      case 'number':
        return (
          <input
            {...common}
            type="number"
            value={stringValue}
            min={field.min_value ?? undefined}
            max={field.max_value ?? undefined}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder || ''}
            className={`${inputClass} ${borderFor(Boolean(error))}`}
          />
        );

      case 'date':
        return (
          <input
            {...common}
            type="date"
            value={stringValue}
            onChange={(e) => onChange(e.target.value)}
            className={`${inputClass} ${borderFor(Boolean(error))}`}
          />
        );

      case 'url':
      case 'text':
        return (
          <input
            {...common}
            type="text"
            inputMode={field.type === 'url' ? 'url' : undefined}
            value={stringValue}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder || (field.type === 'url' ? 'https://…' : '')}
            className={`${inputClass} ${borderFor(Boolean(error))} ${field.type === 'url' ? 'font-mono' : ''}`}
          />
        );

      case 'switch':
        return (
          <label className="flex items-center gap-2 cursor-pointer pt-1">
            <input
              {...common}
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(e.target.checked)}
              className="rounded bg-zinc-900 border-zinc-800 text-emerald-500 focus:ring-0 focus:ring-offset-0 w-4 h-4"
            />
            <span className="text-xs text-zinc-300 font-mono">
              {value ? 'Enabled (Yes)' : 'Disabled (No)'}
            </span>
          </label>
        );

      case 'select': {
        const inOptions = options.includes(stringValue);
        const showOtherInput = otherOpen && !inOptions;
        return (
          <div className="space-y-1.5">
            <select
              {...common}
              value={showOtherInput ? OTHER : stringValue}
              onChange={(e) => {
                if (e.target.value === OTHER) {
                  setOtherOpen(true);
                  onChange('');
                } else {
                  setOtherOpen(false);
                  onChange(e.target.value);
                }
              }}
              className={`${inputClass} ${borderFor(Boolean(error))}`}
            >
              <option value="">-- Select --</option>
              {options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
              {field.allow_other && <option value={OTHER}>{field.other_label || 'Other'}</option>}
            </select>

            {showOtherInput && (
              <input
                type="text"
                value={stringValue}
                onChange={(e) => onChange(e.target.value)}
                onBlur={onBlur}
                placeholder={field.placeholder || 'Please specify…'}
                aria-label={`${field.label} — ${field.other_label || 'Other'}`}
                aria-invalid={error ? true : undefined}
                aria-describedby={describedBy}
                className={`${inputClass} ${borderFor(Boolean(error))}`}
              />
            )}
          </div>
        );
      }

      case 'multi_select': {
        const selected = items.filter((item) => options.includes(item));
        const toggle = (option: string, checked: boolean) => {
          const next = checked ? [...selected, option] : selected.filter((item) => item !== option);
          onChange(customItem ? [...next, customItem] : next);
        };
        return (
          <div className="space-y-1.5">
            <div className="flex flex-wrap gap-1.5">
              {options.map((option) => {
                const checked = selected.includes(option);
                return (
                  <label
                    key={option}
                    className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border text-[11px] cursor-pointer transition ${
                      checked
                        ? 'border-emerald-800 bg-emerald-950/50 text-emerald-200'
                        : 'border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-zinc-700'
                    } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={(e) => toggle(option, e.target.checked)}
                      onBlur={onBlur}
                      className="sr-only"
                    />
                    {checked && <Check className="w-3 h-3" />}
                    {option}
                  </label>
                );
              })}

              {field.allow_other && (
                <label
                  className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border text-[11px] cursor-pointer transition ${
                    otherChecked
                      ? 'border-emerald-800 bg-emerald-950/50 text-emerald-200'
                      : 'border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-zinc-700'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={otherChecked}
                    disabled={disabled}
                    onChange={(e) => {
                      setOtherChecked(e.target.checked);
                      if (!e.target.checked) onChange(selected);
                    }}
                    className="sr-only"
                  />
                  {otherChecked && <Check className="w-3 h-3" />}
                  {field.other_label || 'Other'}
                </label>
              )}
            </div>

            {field.allow_other && otherChecked && (
              <input
                type="text"
                value={customItem}
                onChange={(e) =>
                  onChange(e.target.value.trim() === '' ? selected : [...selected, e.target.value])
                }
                onBlur={onBlur}
                placeholder="Please specify…"
                aria-label={`${field.label} — ${field.other_label || 'Other'}`}
                className={`${inputClass} ${borderFor(Boolean(error))}`}
              />
            )}
          </div>
        );
      }

      default:
        return (
          <input
            {...common}
            type="text"
            value={stringValue}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder || ''}
            className={`${inputClass} ${borderFor(Boolean(error))}`}
          />
        );
    }
  };

  return (
    <div className={field.type === 'textarea' || field.type === 'multi_select' ? 'sm:col-span-2' : ''}>
      <label htmlFor={inputId} className="block text-[10px] font-mono uppercase text-zinc-400 mb-1">
        {field.label} {field.required && <span className="text-rose-400">*</span>}
      </label>

      {renderControl()}

      {field.help_text && !error && (
        <p id={`${inputId}-help`} className="mt-1 text-[10px] font-mono text-zinc-500">
          {field.help_text}
        </p>
      )}

      {error && (
        <p id={`${inputId}-error`} role="alert" className="mt-1 text-[10px] text-rose-400 flex items-center gap-1">
          <AlertCircle className="w-3 h-3 flex-shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
};
