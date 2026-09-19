import React, { useState, useEffect } from 'react';
import { X, Plus, AlertCircle, Globe, Sliders } from 'lucide-react';
import { ticketsApi, appsApi, ticketTypesApi } from '../../api/client';
import { Ticket, ManagedApp, TicketType } from '../../types';
import { Modal } from '../common/Modal';
import { apiErrorMessage } from '../../utils/errors';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onTicketCreated: (newTicket: Ticket) => void;
  initialTitle?: string;
  initialDescription?: string;
}

/** Values a dynamic custom field can hold locally before being sent to the API. */
type CustomFieldValue = string | number | boolean;

/** Render a custom-field value back into a form control (which only takes text). */
const textValue = (value: CustomFieldValue | undefined): string => {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return value ? 'true' : '';
};

/** Build the initial custom-field values for a ticket type's schema. */
const defaultValuesFor = (type: TicketType): Record<string, CustomFieldValue> => {
  const values: Record<string, CustomFieldValue> = {};
  type.fields_schema.forEach((field) => {
    if (field.type === 'switch') values[field.key] = false;
    else if (field.type === 'select' && field.options && field.options.length > 0) {
      values[field.key] = field.options[0];
    } else {
      values[field.key] = '';
    }
  });
  return values;
};

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
  const [customFields, setCustomFields] = useState<Record<string, CustomFieldValue>>({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setError(null);

    // Load active apps and types (small catalogues, so fetch them all)
    Promise.all([appsApi.listAll(true), ticketTypesApi.listAll(true)])
      .then(([appList, typeList]) => {
        setApps(appList);
        setTicketTypes(typeList);

        setSelectedAppId(appList.length > 0 ? appList[0].id : undefined);

        const firstType = typeList.length > 0 ? typeList[0] : undefined;
        setSelectedTypeId(firstType?.id);
        setCustomFields(firstType ? defaultValuesFor(firstType) : {});
      })
      .catch((err) => console.error('Failed to load apps/types for ticket creation', err));
  }, [isOpen, initialTitle, initialDescription]);

  const handleTypeChange = (typeId: number) => {
    setSelectedTypeId(typeId);
    const chosenType = ticketTypes.find((t) => t.id === typeId);
    setCustomFields(chosenType ? defaultValuesFor(chosenType) : {});
  };

  const handleCustomFieldChange = (key: string, value: CustomFieldValue) => {
    setCustomFields((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const currentType = ticketTypes.find((t) => t.id === selectedTypeId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !description.trim()) {
      setError('Please provide both a title and description.');
      return;
    }

    // Validate required custom fields
    if (currentType) {
      for (const field of currentType.fields_schema) {
        if (field.required) {
          const val = customFields[field.key];
          if (val === undefined || val === null || val === '') {
            setError(`Field "${field.label}" is required.`);
            return;
          }
        }
      }
    }

    setLoading(true);
    setError(null);
    try {
      const ticket = await ticketsApi.create({
        title: title.trim(),
        description: description.trim(),
        category,
        priority,
        tags,
        app_id: selectedAppId,
        target_url: targetUrl.trim() || undefined,
        ticket_type_id: selectedTypeId,
        custom_fields: Object.keys(customFields).length > 0 ? customFields : undefined,
      });
      onTicketCreated(ticket);
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to create ticket. Please try again.'));
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
            <h2 id="create-ticket-modal-title" className="text-base font-semibold text-zinc-100">Submit Engineering Support Ticket</h2>
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

        {error && (
          <div className="mt-3 p-2.5 rounded-lg bg-rose-950/60 border border-rose-900 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5 pt-3 overflow-y-auto flex-1 pr-1">
          {/* Title */}
          <div>
            <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
              Ticket Subject / Issue Summary *
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Cannot access payment invoice history"
              className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition"
            />
          </div>

          {/* App / Website & Target URL */}
          <div className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-lg space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-mono text-zinc-400 font-medium">
              <Globe className="w-3.5 h-3.5 text-zinc-400" />
              <span>Application & Target URL</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
                  Target Application / System
                </label>
                <select
                  value={selectedAppId || ''}
                  onChange={(e) => setSelectedAppId(Number(e.target.value) || undefined)}
                  className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                >
                  <option value="">-- General Platform --</option>
                  {apps.map((app) => (
                    <option key={app.id} value={app.id}>
                      {app.name} ({app.code})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
                  Specific Page URL / Path (optional)
                </label>
                <input
                  type="text"
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="https://example.com/checkout"
                  className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition font-mono"
                />
              </div>
            </div>
          </div>

          {/* Ticket Type & Dynamic Custom Fields */}
          <div className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-mono text-zinc-400 font-medium">
                <Sliders className="w-3.5 h-3.5 text-zinc-400" />
                <span>Ticket Type & Custom Properties</span>
              </div>

              {ticketTypes.length > 0 && (
                <span className="text-[10px] font-mono text-zinc-500">
                  {ticketTypes.length} configured types
                </span>
              )}
            </div>

            {ticketTypes.length > 0 ? (
              <div>
                <label className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">
                  Select Ticket Type
                </label>
                <select
                  value={selectedTypeId || ''}
                  onChange={(e) => handleTypeChange(Number(e.target.value))}
                  className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition font-medium"
                >
                  {ticketTypes.map((tt) => (
                    <option key={tt.id} value={tt.id}>
                      {tt.name} {tt.description ? `— ${tt.description}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="text-[11px] font-mono text-zinc-500">
                Standard Support Request (No specialized custom fields)
              </div>
            )}

            {/* Dynamic Custom Fields Schema */}
            {currentType && currentType.fields_schema.length > 0 && (
              <div className="pt-2 border-t border-zinc-800 space-y-2.5">
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  Required Type Attributes ({currentType.name})
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {currentType.fields_schema.map((field) => (
                    <div key={field.key} className={field.type === 'textarea' ? 'sm:col-span-2' : ''}>
                      <label className="block text-[10px] font-mono uppercase text-zinc-400 mb-1">
                        {field.label} {field.required && <span className="text-rose-400">*</span>}
                      </label>

                      {field.type === 'text' && (
                        <input
                          type="text"
                          required={field.required}
                          value={textValue(customFields[field.key])}
                          onChange={(e) => handleCustomFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder || ''}
                          className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                        />
                      )}

                      {field.type === 'number' && (
                        <input
                          type="number"
                          required={field.required}
                          value={textValue(customFields[field.key])}
                          onChange={(e) => handleCustomFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder || ''}
                          className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                        />
                      )}

                      {field.type === 'url' && (
                        <input
                          type="url"
                          required={field.required}
                          value={textValue(customFields[field.key])}
                          onChange={(e) => handleCustomFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder || 'https://...'}
                          className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition font-mono"
                        />
                      )}

                      {field.type === 'select' && (
                        <select
                          required={field.required}
                          value={textValue(customFields[field.key])}
                          onChange={(e) => handleCustomFieldChange(field.key, e.target.value)}
                          className="w-full text-xs px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
                        >
                          {(field.options || []).map((opt, oIdx) => (
                            <option key={oIdx} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      )}

                      {field.type === 'switch' && (
                        <label className="flex items-center gap-2 cursor-pointer pt-1">
                          <input
                            type="checkbox"
                            checked={Boolean(customFields[field.key])}
                            onChange={(e) => handleCustomFieldChange(field.key, e.target.checked)}
                            className="rounded bg-zinc-900 border-zinc-800 text-emerald-500 focus:ring-0 focus:ring-offset-0 w-4 h-4"
                          />
                          <span className="text-xs text-zinc-300 font-mono">
                            {customFields[field.key] ? 'Enabled (Yes)' : 'Disabled (No)'}
                          </span>
                        </label>
                      )}

                      {field.type === 'textarea' && (
                        <textarea
                          rows={2}
                          required={field.required}
                          value={textValue(customFields[field.key])}
                          onChange={(e) => handleCustomFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder || ''}
                          className="w-full text-xs p-2.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition resize-none"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Priority & Category */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
              >
                <option value="technical">Technical Support</option>
                <option value="billing">Billing & Payment</option>
                <option value="account">Account & Access</option>
                <option value="general">General Inquiries</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-500 focus:outline-none transition"
              >
                <option value="low">Low (Standard)</option>
                <option value="medium">Medium (Normal)</option>
                <option value="high">High (Urgent)</option>
                <option value="urgent">Urgent (Critical Outage)</option>
              </select>
            </div>
          </div>

          {/* Tags */}
          <div>
            <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
              Tags
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="checkout, payment, timeout"
              className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none transition"
            />
            <p className="mt-1 text-[10px] font-mono text-zinc-500">
              Comma-separated labels to help support triage this ticket.
            </p>
          </div>

          {/* Description */}
          <div>
            <label className="block text-[11px] font-mono uppercase text-zinc-400 mb-1">
              Issue Description / Reproduction Details *
            </label>
            <textarea
              rows={3}
              required
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what occurred, steps to reproduce, or relevant background..."
              className="w-full text-xs p-3 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none resize-none transition"
            />
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
