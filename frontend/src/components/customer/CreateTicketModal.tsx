import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { X, Plus, AlertCircle, Globe, Sliders } from 'lucide-react';
import { ticketsApi, appsApi, ticketTypesApi } from '../../api/client';
import type {
  CustomFieldDefinition,
  CustomFieldValue,
  CustomFieldValues,
  ManagedApp,
  Ticket,
  TicketType,
} from '../../types';
import { Modal } from '../common/Modal';
import { apiErrorMessage, apiFieldErrors, fieldErrorMap } from '../../utils/errors';
import {
  emptyValueFor,
  evaluateForm,
  isFieldRequired,
  validateBaseFields,
  validateCustomFields,
  CUSTOM_FIELD_PREFIX,
} from '../../utils/formLogic';
import { CustomFieldInput } from './CustomFieldInput';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onTicketCreated: (newTicket: Ticket) => void;
  initialTitle?: string;
  initialDescription?: string;
}

/** One rejected input, shown in the summary banner and jumping to the control. */
interface Problem {
  field: string;
  message: string;
}

/** DOM id of the control a field path refers to. */
const BASE_INPUT_IDS: Record<string, string> = {
  title: 'field-title',
  description: 'field-description',
  tags: 'field-tags',
  target_url: 'field-target-url',
  app_id: 'field-app',
  ticket_type_id: 'field-ticket-type',
};

const inputIdFor = (fieldPath: string): string => {
  if (fieldPath.startsWith(CUSTOM_FIELD_PREFIX)) {
    return `cf-${fieldPath.slice(CUSTOM_FIELD_PREFIX.length)}`;
  }
  return BASE_INPUT_IDS[fieldPath] ?? '';
};

const focusField = (fieldPath: string): void => {
  const element = document.getElementById(inputIdFor(fieldPath));
  if (!element) return;
  element.focus();
  element.scrollIntoView({ block: 'center', behavior: 'smooth' });
};

const fieldClass = (hasError: boolean) =>
  `w-full text-xs px-3 py-2 bg-zinc-950 border rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none transition ${
    hasError ? 'border-rose-800 focus:border-rose-600' : 'border-zinc-800 focus:border-zinc-500'
  }`;

/** Inline message shown under a built-in control. */
const FieldError: React.FC<{ id: string; message?: string }> = ({ id, message }) =>
  message ? (
    <p id={id} role="alert" className="mt-1 text-[10px] text-rose-400 flex items-center gap-1">
      <AlertCircle className="w-3 h-3 flex-shrink-0" />
      <span>{message}</span>
    </p>
  ) : null;

export const CreateTicketModal: React.FC<Props> = ({
  isOpen,
  onClose,
  onTicketCreated,
  initialTitle = '',
  initialDescription = '',
}) => {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('technical');
  const [priority, setPriority] = useState('medium');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');

  // Apps & Ticket Types
  const [apps, setApps] = useState<ManagedApp[]>([]);
  const [ticketTypes, setTicketTypes] = useState<TicketType[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<number | undefined>(undefined);
  const [targetUrl, setTargetUrl] = useState('');
  const [selectedTypeId, setSelectedTypeId] = useState<number | undefined>(undefined);
  const [customFields, setCustomFields] = useState<CustomFieldValues>({});

  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  /** Keyed by API field path, so a custom field with key `title` cannot collide. */
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [dropdownError, setDropdownError] = useState<Record<string, string | undefined>>({});

  const currentType = useMemo(
    () => ticketTypes.find((t) => t.id === selectedTypeId),
    [ticketTypes, selectedTypeId],
  );
  const schema: CustomFieldDefinition[] = useMemo(
    () => currentType?.fields_schema ?? [],
    [currentType],
  );

  // Which questions are on screen right now, and which were hidden away.
  const evaluation = useMemo(() => evaluateForm(schema, customFields), [schema, customFields]);

  const resetProblemState = () => {
    setSummary(null);
    setProblems([]);
    setFieldErrors({});
    setDropdownError({});
  };

  useEffect(() => {
    if (!isOpen) return;

    // Reset to a clean slate every time the modal opens, then apply any prefill
    // coming from the FAQ escalation flow. Without this the previous ticket's
    // title/description/category linger into the next creation.
    setTitle(initialTitle);
    setDescription(initialDescription);
    setCategory('technical');
    setPriority('medium');
    setTags('');
    setTargetUrl('');
    setCustomFields({});
    resetProblemState();

    // Load active apps and types (small catalogues, so fetch them all)
    Promise.all([appsApi.listAll(true), ticketTypesApi.listAll(true)])
      .then(([appList, typeList]) => {
        setApps(appList);
        setTicketTypes(typeList);
        setSelectedAppId(appList.length > 0 ? appList[0].id : undefined);
        setSelectedTypeId(undefined);
      })
      .catch((err) => {
        console.error('Failed to load apps/types for ticket creation', err);
        setSummary(apiErrorMessage(err, 'Could not load the ticket form. Please reopen this dialog.'));
      });
  }, [isOpen, initialTitle, initialDescription]);

  const handleTypeChange = (typeId: number | undefined) => {
    setSelectedTypeId(typeId);
    // Answers belong to the questions of the previous type, so they go away.
    setCustomFields({});
    resetProblemState();
  };

  const clearFieldError = (fieldPath: string) => {
    setFieldErrors((prev) => {
      if (!(fieldPath in prev)) return prev;
      const next = { ...prev };
      delete next[fieldPath];
      return next;
    });
    setProblems((prev) => prev.filter((problem) => problem.field !== fieldPath));
  };

  const handleCustomFieldChange = (field: CustomFieldDefinition, value: CustomFieldValue) => {
    const nextValues = { ...customFields, [field.key]: value };
    setCustomFields(nextValues);

    const nextEvaluation = evaluateForm(schema, nextValues);
    clearFieldError(`${CUSTOM_FIELD_PREFIX}${field.key}`);
    // Errors on questions that just disappeared must not stay on screen.
    nextEvaluation.hiddenKeys.forEach((key) => clearFieldError(`${CUSTOM_FIELD_PREFIX}${key}`));
  };

  /** Validate one field as soon as the customer leaves it, without nagging. */
  const handleCustomFieldBlur = (fieldKey: string) => {
    const result = validateCustomFields(schema, customFields);
    const problem = result.errors[fieldKey];
    const path = `${CUSTOM_FIELD_PREFIX}${fieldKey}`;
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (problem) next[path] = problem.message;
      else delete next[path];
      return next;
    });
  };

  /** Same idea for a built-in field; only the blurred field is reported. */
  const validateBaseField = (name: 'title' | 'description' | 'tags' | 'target_url') => {
    const result = validateBaseFields({ title, description, tags, target_url: targetUrl, category, priority });
    const message = result.errors[name];
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (message) next[name] = message;
      else delete next[name];
      return next;
    });
  };

  const runValidation = useCallback(() => {
    const base = validateBaseFields({ title, description, tags, target_url: targetUrl, category, priority });
    const custom = validateCustomFields(schema, customFields);

    const errors: Record<string, string> = { ...base.errors };
    const found: Problem[] = Object.entries(base.errors).map(([field, message]) => ({ field, message }));

    Object.entries(custom.errors).forEach(([key, problem]) => {
      const path = `${CUSTOM_FIELD_PREFIX}${key}`;
      errors[path] = problem.message;
      found.push({ field: path, message: problem.message });
    });

    return { errors, problems: found, values: custom.values };
  }, [title, description, tags, targetUrl, category, priority, schema, customFields]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const validation = runValidation();
    if (validation.problems.length > 0) {
      setFieldErrors(validation.errors);
      setProblems(validation.problems);
      setSummary(
        validation.problems.length === 1
          ? validation.problems[0].message
          : `${validation.problems.length} problems need your attention.`,
      );
      focusField(validation.problems[0].field);
      return;
    }

    setLoading(true);
    setSummary(null);
    setProblems([]);
    setFieldErrors({});
    setDropdownError({});

    try {
      const cleaned = validateBaseFields({ title, description, tags, target_url: targetUrl, category, priority });
      const ticket = await ticketsApi.create({
        title: cleaned.cleaned.title,
        description: cleaned.cleaned.description,
        category,
        priority,
        tags: cleaned.cleaned.tags,
        app_id: selectedAppId,
        target_url: cleaned.cleaned.target_url,
        ticket_type_id: selectedTypeId,
        // `values` holds the *validated* answers of the visible questions only:
        // hidden answers are dropped here as well as on the server.
        custom_fields: schema.length > 0 ? validation.values : undefined,
      });
      onTicketCreated(ticket);
      onClose();
    } catch (err) {
      const serverErrors = fieldErrorMap(err, { stripCustomPrefix: false });
      const serverProblems = apiFieldErrors(err).map((entry) => ({
        field: entry.field,
        message: entry.message,
      }));

      setFieldErrors(serverErrors);
      setDropdownError({
        app_id: serverErrors.app_id,
        ticket_type_id: serverErrors.ticket_type_id,
      });
      setProblems(serverProblems);
      // A field-level rejection lists the problems themselves; anything else
      // (403, 500, offline) only has a message - and the message of a 500
      // carries the request reference to quote in a bug report.
      setSummary(
        serverProblems.length > 0
          ? `${serverProblems.length} problems need your attention.`
          : apiErrorMessage(err, 'Failed to create ticket. Please try again.'),
      );
      if (serverProblems.length > 0) focusField(serverProblems[0].field);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      labelledBy="create-ticket-modal-title"
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
      panelClassName="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl max-w-xl w-full p-5 relative my-8 animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col"
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
        <div>
          <div className="font-mono text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">
            OFFICIAL ESCALATION
          </div>
          <h2 id="create-ticket-modal-title" className="text-base font-semibold text-zinc-100">
            Submit Engineering Support Ticket
          </h2>
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

      {summary && (
        <div
          role="alert"
          className="mt-3 p-2.5 rounded-lg bg-rose-950/60 border border-rose-900 text-rose-300 text-xs"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{summary}</span>
          </div>
          {problems.length > 1 && (
            <ul className="mt-2 space-y-1 pl-6 list-disc">
              {problems.map((problem) => (
                <li key={problem.field}>
                  <button
                    type="button"
                    onClick={() => focusField(problem.field)}
                    className="text-left underline decoration-dotted hover:text-rose-200"
                  >
                    {problem.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* noValidate: the browser's own bubbles would pre-empt the messages below. */}
      <form onSubmit={handleSubmit} noValidate className="space-y-3.5 pt-3 overflow-y-auto flex-1 pr-1">
        {/* Title */}
        <div>
          <label htmlFor="field-title" className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
            Ticket Subject / Issue Summary *
          </label>
          <input
            id="field-title"
            type="text"
            value={title}
            aria-invalid={fieldErrors.title ? true : undefined}
            aria-describedby={fieldErrors.title ? 'field-title-error' : undefined}
            onChange={(e) => {
              setTitle(e.target.value);
              clearFieldError('title');
            }}
            onBlur={() => validateBaseField('title')}
            placeholder="e.g. Cannot access payment invoice history"
            className={fieldClass(Boolean(fieldErrors.title))}
          />
          <FieldError id="field-title-error" message={fieldErrors.title} />
        </div>

        {/* App / Website & Target URL */}
        <div className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-lg space-y-2.5">
          <div className="flex items-center gap-1.5 text-xs font-mono text-zinc-400 font-medium">
            <Globe className="w-3.5 h-3.5 text-zinc-400" />
            <span>Application &amp; Target URL</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <div>
              <label htmlFor="field-app" className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
                Target Application / System
              </label>
              <select
                id="field-app"
                value={selectedAppId || ''}
                onChange={(e) => {
                  setSelectedAppId(Number(e.target.value) || undefined);
                  setDropdownError((prev) => ({ ...prev, app_id: '' }));
                }}
                aria-invalid={dropdownError.app_id ? true : undefined}
                className={`w-full text-xs px-2.5 py-1.5 bg-zinc-900 border rounded-lg text-zinc-100 focus:outline-none transition ${
                  dropdownError.app_id ? 'border-rose-800' : 'border-zinc-800 focus:border-zinc-500'
                }`}
              >
                <option value="">-- General Platform --</option>
                {apps.map((app) => (
                  <option key={app.id} value={app.id}>
                    {app.name} ({app.code})
                  </option>
                ))}
              </select>
              <FieldError id="field-app-error" message={dropdownError.app_id} />
            </div>

            <div>
              <label htmlFor="field-target-url" className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
                Specific Page URL / Path (optional)
              </label>
              <input
                id="field-target-url"
                type="text"
                value={targetUrl}
                aria-invalid={fieldErrors.target_url ? true : undefined}
                aria-describedby={fieldErrors.target_url ? 'field-target-url-error' : undefined}
                onChange={(e) => {
                  setTargetUrl(e.target.value);
                  clearFieldError('target_url');
                }}
                onBlur={() => validateBaseField('target_url')}
                placeholder="https://example.com/checkout"
                className={`${fieldClass(Boolean(fieldErrors.target_url))} font-mono`}
              />
              <FieldError id="field-target-url-error" message={fieldErrors.target_url} />
            </div>
          </div>
        </div>

        {/* Ticket Type & Dynamic Custom Fields */}
        <div className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-lg space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-mono text-zinc-400 font-medium">
              <Sliders className="w-3.5 h-3.5 text-zinc-400" />
              <span>Ticket Type &amp; Custom Properties</span>
            </div>

            {ticketTypes.length > 0 && (
              <span className="text-[10px] font-mono text-zinc-500">
                {ticketTypes.length} configured types
              </span>
            )}
          </div>

          {ticketTypes.length > 0 ? (
            <div>
              <label
                htmlFor="field-ticket-type"
                className="block text-[10px] font-mono uppercase text-zinc-500 mb-1"
              >
                Select Ticket Type
              </label>
              <select
                id="field-ticket-type"
                value={selectedTypeId || ''}
                onChange={(e) => handleTypeChange(e.target.value ? Number(e.target.value) : undefined)}
                aria-invalid={dropdownError.ticket_type_id ? true : undefined}
                className={`w-full text-xs px-2.5 py-1.5 bg-zinc-900 border rounded-lg text-zinc-100 focus:outline-none transition font-medium ${
                  dropdownError.ticket_type_id ? 'border-rose-800' : 'border-zinc-800 focus:border-zinc-500'
                }`}
              >
                <option value="">Standard request</option>
                {ticketTypes.map((tt) => (
                  <option key={tt.id} value={tt.id}>
                    {tt.name} {tt.description ? `— ${tt.description}` : ''}
                  </option>
                ))}
              </select>
              <FieldError id="field-ticket-type-error" message={dropdownError.ticket_type_id} />
            </div>
          ) : (
            <div className="text-[11px] font-mono text-zinc-500">
              Standard Support Request (No specialized custom fields)
            </div>
          )}

          {/* Dynamic Custom Fields Schema */}
          {schema.length > 0 && (
            <div className="pt-2 border-t border-zinc-800 space-y-2.5">
              <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                {currentType?.name} attributes
              </div>

              {evaluation.visible.length === 0 ? (
                <div className="text-[11px] font-mono text-zinc-500">
                  This ticket type has no questions to answer right now.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {evaluation.visible.map((field) => (
                    <CustomFieldInput
                      key={`${currentType?.id ?? 0}-${field.key}`}
                      field={field}
                      value={customFields[field.key] ?? emptyValueFor(field)}
                      error={fieldErrors[`${CUSTOM_FIELD_PREFIX}${field.key}`]}
                      onChange={(value) => handleCustomFieldChange(field, value)}
                      onBlur={() => handleCustomFieldBlur(field.key)}
                      disabled={loading}
                      required={isFieldRequired(field, customFields)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Priority & Category */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="field-category" className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
              Category
            </label>
            <select
              id="field-category"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                clearFieldError('category');
              }}
              className={fieldClass(Boolean(fieldErrors.category))}
            >
              <option value="technical">Technical Support</option>
              <option value="billing">Billing &amp; Payment</option>
              <option value="account">Account &amp; Access</option>
              <option value="general">General Inquiries</option>
            </select>
            <FieldError id="field-category-error" message={fieldErrors.category} />
          </div>

          <div>
            <label htmlFor="field-priority" className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
              Priority
            </label>
            <select
              id="field-priority"
              value={priority}
              onChange={(e) => {
                setPriority(e.target.value);
                clearFieldError('priority');
              }}
              className={fieldClass(Boolean(fieldErrors.priority))}
            >
              <option value="low">Low (Standard)</option>
              <option value="medium">Medium (Normal)</option>
              <option value="high">High (Urgent)</option>
              <option value="urgent">Urgent (Critical Outage)</option>
            </select>
            <FieldError id="field-priority-error" message={fieldErrors.priority} />
          </div>
        </div>

        {/* Tags */}
        <div>
          <label htmlFor="field-tags" className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
            Tags
          </label>
          <input
            id="field-tags"
            type="text"
            value={tags}
            aria-invalid={fieldErrors.tags ? true : undefined}
            aria-describedby={fieldErrors.tags ? 'field-tags-error' : 'field-tags-help'}
            onChange={(e) => {
              setTags(e.target.value);
              clearFieldError('tags');
            }}
            onBlur={() => validateBaseField('tags')}
            placeholder="checkout, payment, timeout"
            className={fieldClass(Boolean(fieldErrors.tags))}
          />
          {!fieldErrors.tags && (
            <p id="field-tags-help" className="mt-1 text-[10px] font-mono text-zinc-500">
              Comma-separated labels to help support triage this ticket.
            </p>
          )}
          <FieldError id="field-tags-error" message={fieldErrors.tags} />
        </div>

        {/* Description */}
        <div>
          <label htmlFor="field-description" className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
            Issue Description / Reproduction Details *
          </label>
          <textarea
            id="field-description"
            rows={3}
            value={description}
            aria-invalid={fieldErrors.description ? true : undefined}
            aria-describedby={fieldErrors.description ? 'field-description-error' : undefined}
            onChange={(e) => {
              setDescription(e.target.value);
              clearFieldError('description');
            }}
            onBlur={() => validateBaseField('description')}
            placeholder="Describe what occurred, steps to reproduce, or relevant background..."
            className={`${fieldClass(Boolean(fieldErrors.description))} resize-none`}
          />
          <FieldError id="field-description-error" message={fieldErrors.description} />
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-800">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-1.5 text-xs font-medium text-zinc-950 bg-zinc-100 hover:bg-white rounded-lg transition disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            {loading ? 'Submitting...' : 'Dispatch Ticket'}
          </button>
        </div>
      </form>
    </Modal>
  );
};
