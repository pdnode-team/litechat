import React, { useMemo, useState } from 'react';
import { AlertCircle, GitBranch, Pencil, Plus, Trash2, X } from 'lucide-react';
import type {
  ConditionGroup,
  ConditionOperator,
  CustomFieldDefinition,
  CustomFieldType,
  FieldCondition,
} from '../../types';
import {
  CONDITION_OPERATOR_LABELS,
  CUSTOM_FIELD_TYPES,
  UNARY_CONDITION_OPERATORS,
} from '../../types';
import { validateFieldSchema } from '../../utils/formLogic';

interface Props {
  fields: CustomFieldDefinition[];
  onChange: (fields: CustomFieldDefinition[]) => void;
}

const TYPE_LABELS: Record<CustomFieldType, string> = {
  text: 'Text (single line)',
  textarea: 'Textarea (multi line)',
  select: 'Dropdown (single choice)',
  multi_select: 'Checkboxes (multiple choice)',
  number: 'Number',
  switch: 'Switch (yes / no)',
  url: 'URL',
  date: 'Date',
};

const CHOICE_TYPES: CustomFieldType[] = ['select', 'multi_select'];
const LENGTH_TYPES: CustomFieldType[] = ['text', 'textarea', 'url', 'date'];

/** One editable condition; `value` stays a string so the input stays controlled. */
interface ConditionDraft {
  field: string;
  operator: ConditionOperator;
  value: string;
}

/** Everything the builder edits, kept as strings so inputs stay controlled. */
interface Draft {
  label: string;
  key: string;
  type: CustomFieldType;
  required: boolean;
  placeholder: string;
  help_text: string;
  optionsStr: string;
  allow_other: boolean;
  other_label: string;
  min_length: string;
  max_length: string;
  pattern: string;
  error_message: string;
  min_value: string;
  max_value: string;
  visibleLogic: 'all' | 'any';
  visibleWhen: ConditionDraft[];
  requiredLogic: 'all' | 'any';
  requiredWhen: ConditionDraft[];
}

const newCondition = (): ConditionDraft => ({ field: '', operator: 'equals', value: '' });

const emptyDraft = (): Draft => ({
  label: '',
  key: '',
  type: 'text',
  required: false,
  placeholder: '',
  help_text: '',
  optionsStr: '',
  allow_other: false,
  other_label: 'Other',
  min_length: '',
  max_length: '',
  pattern: '',
  error_message: '',
  min_value: '',
  max_value: '',
  visibleLogic: 'all',
  visibleWhen: [],
  requiredLogic: 'all',
  requiredWhen: [],
});

const slugify = (label: string): string =>
  label
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_{2,}/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40);

const numberOrNull = (raw: string): number | null => {
  const text = raw.trim();
  if (text === '') return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
};

const conditionValueFor = (raw: string, target: CustomFieldDefinition | undefined, operator: ConditionOperator) => {
  if (operator === 'in' || operator === 'not_in') {
    return raw
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
  }
  if (target?.type === 'number') {
    const parsed = Number(raw.trim());
    return Number.isFinite(parsed) ? parsed : raw.trim();
  }
  if (target?.type === 'switch') return raw.trim().toLowerCase() === 'true';
  return raw.trim();
};

const renderConditionValue = (value: unknown): string => {
  if (value === undefined || value === null) return '';
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
};

const toConditionDrafts = (group?: ConditionGroup | null): ConditionDraft[] =>
  (group?.conditions ?? []).map((condition) => ({
    field: condition.field,
    operator: condition.operator,
    value: renderConditionValue(condition.value),
  }));

const draftFromField = (field: CustomFieldDefinition): Draft => ({
  label: field.label,
  key: field.key,
  type: field.type,
  required: Boolean(field.required),
  placeholder: field.placeholder ?? '',
  help_text: field.help_text ?? '',
  optionsStr: (field.options ?? []).join(', '),
  allow_other: Boolean(field.allow_other),
  other_label: field.other_label || 'Other',
  min_length: field.min_length === null || field.min_length === undefined ? '' : String(field.min_length),
  max_length: field.max_length === null || field.max_length === undefined ? '' : String(field.max_length),
  pattern: field.pattern ?? '',
  error_message: field.error_message ?? '',
  min_value: field.min_value === null || field.min_value === undefined ? '' : String(field.min_value),
  max_value: field.max_value === null || field.max_value === undefined ? '' : String(field.max_value),
  visibleLogic: field.visible_when?.logic ?? 'all',
  visibleWhen: toConditionDrafts(field.visible_when),
  requiredLogic: field.required_when?.logic ?? 'all',
  requiredWhen: toConditionDrafts(field.required_when),
});

const buildField = (draft: Draft, targets: CustomFieldDefinition[]): CustomFieldDefinition => {
  const options = draft.optionsStr
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);

  const group = (logic: 'all' | 'any', drafts: ConditionDraft[]): ConditionGroup | null => {
    const conditions: FieldCondition[] = drafts
      // A row with no field selected is an unfinished rule, not a rule.
      .filter((candidate) => candidate.field)
      .map((candidate) => {
        const target = targets.find((field) => field.key === candidate.field);
        const condition: FieldCondition = { field: candidate.field, operator: candidate.operator };
        if (!UNARY_CONDITION_OPERATORS.includes(candidate.operator)) {
          condition.value = conditionValueFor(candidate.value, target, candidate.operator);
        }
        return condition;
      });
    if (conditions.length === 0) return null;
    return { logic, conditions };
  };

  return {
    key: draft.key.trim() || slugify(draft.label),
    label: draft.label.trim(),
    type: draft.type,
    required: draft.required,
    placeholder: draft.placeholder.trim(),
    help_text: draft.help_text.trim(),
    options,
    allow_other: CHOICE_TYPES.includes(draft.type) ? draft.allow_other : false,
    other_label: draft.other_label.trim() || 'Other',
    min_length: LENGTH_TYPES.includes(draft.type) ? numberOrNull(draft.min_length) : null,
    max_length: LENGTH_TYPES.includes(draft.type) ? numberOrNull(draft.max_length) : null,
    pattern: LENGTH_TYPES.includes(draft.type) && draft.pattern.trim() ? draft.pattern.trim() : null,
    min_value: draft.type === 'number' ? numberOrNull(draft.min_value) : null,
    max_value: draft.type === 'number' ? numberOrNull(draft.max_value) : null,
    error_message: draft.error_message.trim() || null,
    visible_when: group(draft.visibleLogic, draft.visibleWhen),
    required_when: group(draft.requiredLogic, draft.requiredWhen),
  };
};

const describeCondition = (condition: FieldCondition): string => {
  const operator = CONDITION_OPERATOR_LABELS[condition.operator] ?? condition.operator;
  if (UNARY_CONDITION_OPERATORS.includes(condition.operator)) {
    return `${condition.field} ${operator}`;
  }
  const value = Array.isArray(condition.value) ? condition.value.join(' / ') : String(condition.value ?? '');
  return `${condition.field} ${operator} "${value}"`;
};

/** "a is X" or "a is X and b is Y" — the stored group as one readable line. */
const describeGroup = (group?: ConditionGroup | null): string => {
  const conditions = group?.conditions ?? [];
  if (conditions.length === 0) return '';
  const joiner = group?.logic === 'any' ? ' or ' : ' and ';
  return conditions.map(describeCondition).join(joiner);
};

const inputClass =
  'w-full text-xs p-1.5 bg-zinc-900 border border-zinc-800 rounded text-zinc-100 placeholder-zinc-600 focus:border-zinc-500 focus:outline-none';
const labelClass = 'block text-[10px] font-mono uppercase text-zinc-500 mb-1';

/** One "field / operator / value" row of a conditional rule. */
const ConditionRow: React.FC<{
  targets: CustomFieldDefinition[];
  condition: ConditionDraft;
  onChange: (patch: Partial<ConditionDraft>) => void;
  onRemove: () => void;
}> = ({ targets, condition, onChange, onRemove }) => {
  const target = targets.find((candidate) => candidate.key === condition.field);
  const isUnary = UNARY_CONDITION_OPERATORS.includes(condition.operator);
  const isList = condition.operator === 'in' || condition.operator === 'not_in';
  const choices = target && CHOICE_TYPES.includes(target.type) ? target.options ?? [] : [];

  return (
    <div className="flex items-end gap-2">
      <div className="flex-1 min-w-0">
        <select
          aria-label="Condition field"
          value={condition.field}
          onChange={(e) => onChange({ field: e.target.value, value: '' })}
          className={inputClass}
        >
          <option value="">— pick a field —</option>
          {targets.map((candidate) => (
            <option key={candidate.key} value={candidate.key}>
              {candidate.label}
            </option>
          ))}
        </select>
      </div>

      <div className="w-44 flex-shrink-0">
        <select
          aria-label="Condition operator"
          value={condition.operator}
          disabled={!condition.field}
          onChange={(e) => onChange({ operator: e.target.value as ConditionOperator })}
          className={`${inputClass} disabled:opacity-40`}
        >
          {(Object.keys(CONDITION_OPERATOR_LABELS) as ConditionOperator[]).map((candidate) => (
            <option key={candidate} value={candidate}>
              {CONDITION_OPERATOR_LABELS[candidate]}
            </option>
          ))}
        </select>
      </div>

      <div className="w-40 flex-shrink-0">
        {isUnary ? (
          <div className="text-[10px] font-mono text-zinc-600 px-1.5 py-2">no value needed</div>
        ) : choices.length > 0 && !isList ? (
          <select
            aria-label="Condition value"
            value={condition.value}
            disabled={!condition.field}
            onChange={(e) => onChange({ value: e.target.value })}
            className={`${inputClass} disabled:opacity-40`}
          >
            <option value="">— select —</option>
            {choices.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            aria-label="Condition value"
            value={condition.value}
            disabled={!condition.field}
            onChange={(e) => onChange({ value: e.target.value })}
            placeholder={isList ? 'a, b, c' : 'value to compare'}
            className={`${inputClass} disabled:opacity-40`}
          />
        )}
      </div>

      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove condition"
        title="Remove condition"
        className="text-zinc-500 hover:text-rose-400 p-1.5 flex-shrink-0"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

/** A rule = zero or more conditions, combined with all/any. */
const ConditionGroupEditor: React.FC<{
  title: string;
  hint: string;
  targets: CustomFieldDefinition[];
  logic: 'all' | 'any';
  conditions: ConditionDraft[];
  onLogicChange: (logic: 'all' | 'any') => void;
  onChange: (index: number, patch: Partial<ConditionDraft>) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}> = ({ title, hint, targets, logic, conditions, onLogicChange, onChange, onAdd, onRemove }) => (
  <div className="space-y-1.5">
    <div className="flex items-center justify-between gap-2">
      <span className="text-[10px] font-mono uppercase text-zinc-400">{title}</span>
      <div className="flex items-center gap-2">
        {conditions.length > 1 && (
          <label className="flex items-center gap-1 text-[10px] font-mono text-zinc-500">
            match
            <select
              aria-label={`${title} — how conditions combine`}
              value={logic}
              onChange={(e) => onLogicChange(e.target.value as 'all' | 'any')}
              className="bg-zinc-900 border border-zinc-800 rounded px-1 py-0.5 text-[10px] text-zinc-200"
            >
              <option value="all">all</option>
              <option value="any">any</option>
            </select>
          </label>
        )}
        <button
          type="button"
          onClick={onAdd}
          disabled={targets.length === 0}
          className="text-[10px] font-mono text-zinc-400 hover:text-zinc-100 disabled:opacity-40 flex items-center gap-1"
        >
          <Plus className="w-3 h-3" /> Add condition
        </button>
      </div>
    </div>

    {conditions.length === 0 ? (
      <div className="text-[10px] font-mono text-zinc-600 px-1">{hint}</div>
    ) : (
      conditions.map((condition, index) => (
        <ConditionRow
          key={index}
          targets={targets}
          condition={condition}
          onChange={(patch) => onChange(index, patch)}
          onRemove={() => onRemove(index)}
        />
      ))
    )}
  </div>
);

/**
 * Editor for a ticket type's dynamic form.
 *
 * Conditions may only reference fields defined *above* the one being edited,
 * which is what keeps the evaluation order well defined; the picker therefore
 * only ever offers earlier fields.
 */
export const CustomFieldBuilder: React.FC<Props> = ({ fields, onChange }) => {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const targets = useMemo(
    () => (editingIndex === null ? fields : fields.slice(0, editingIndex)),
    [fields, editingIndex],
  );

  const patch = (next: Partial<Draft>) => setDraft((prev) => ({ ...prev, ...next }));

  const patchCondition = (rule: 'visibleWhen' | 'requiredWhen', index: number, next: Partial<ConditionDraft>) =>
    setDraft((prev) => ({
      ...prev,
      [rule]: prev[rule].map((condition, position) =>
        position === index ? { ...condition, ...next } : condition,
      ),
    }));

  const addCondition = (rule: 'visibleWhen' | 'requiredWhen') =>
    setDraft((prev) => ({ ...prev, [rule]: [...prev[rule], newCondition()] }));

  const removeCondition = (rule: 'visibleWhen' | 'requiredWhen', index: number) =>
    setDraft((prev) => ({ ...prev, [rule]: prev[rule].filter((_, position) => position !== index) }));

  const resetDraft = () => {
    setDraft(emptyDraft());
    setEditingIndex(null);
    setProblem(null);
  };

  const handleSave = () => {
    if (!draft.label.trim()) {
      setProblem('A label is required.');
      return;
    }
    const candidate = buildField(draft, targets);
    const nextFields =
      editingIndex === null
        ? [...fields, candidate]
        : fields.map((existing, index) => (index === editingIndex ? candidate : existing));

    const problems = validateFieldSchema(nextFields);
    const address = `fields_schema.${editingIndex === null ? nextFields.length - 1 : editingIndex}`;
    // Prefer a problem on the field being saved; fall back to anything the edit
    // broke elsewhere (renaming a key can orphan a later field's condition).
    const targeted = problems.filter((entry) => entry.field === address);
    const relevant = targeted.length > 0 ? targeted : problems;
    if (relevant.length > 0) {
      setProblem(relevant[0].message);
      return;
    }

    onChange(nextFields);
    resetDraft();
  };

  const startEditing = (index: number) => {
    setDraft(draftFromField(fields[index]));
    setEditingIndex(index);
    setProblem(null);
  };

  const remove = (index: number) => {
    onChange(fields.filter((_, position) => position !== index));
    if (editingIndex === index) resetDraft();
    else if (editingIndex !== null && editingIndex > index) setEditingIndex(editingIndex - 1);
  };

  const isChoice = CHOICE_TYPES.includes(draft.type);
  const isLength = LENGTH_TYPES.includes(draft.type);
  const isNumber = draft.type === 'number';

  return (
    <div className="p-3 bg-zinc-950 rounded-lg border border-zinc-800 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-mono font-semibold text-zinc-300">
          Custom Properties Schema Builder
        </div>
        {editingIndex !== null && (
          <span className="text-[10px] font-mono text-amber-400">
            Editing field #{editingIndex + 1}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <label className={labelClass}>Field Label *</label>
          <input
            type="text"
            value={draft.label}
            onChange={(e) => patch({ label: e.target.value })}
            placeholder="e.g. Browser Version"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Field Key (auto)</label>
          <input
            type="text"
            value={draft.key}
            onChange={(e) => patch({ key: slugify(e.target.value) })}
            placeholder={slugify(draft.label) || 'browser_version'}
            className={`${inputClass} font-mono`}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <label className={labelClass}>Field Type</label>
          <select
            value={draft.type}
            onChange={(e) => patch({ type: e.target.value as CustomFieldType })}
            className={`${inputClass} font-mono`}
          >
            {CUSTOM_FIELD_TYPES.map((type) => (
              <option key={type} value={type}>
                {TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass}>Placeholder</label>
          <input
            type="text"
            value={draft.placeholder}
            onChange={(e) => patch({ placeholder: e.target.value })}
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label className={labelClass}>Help Text</label>
        <input
          type="text"
          value={draft.help_text}
          onChange={(e) => patch({ help_text: e.target.value })}
          placeholder="Shown under the input to explain what is expected"
          className={inputClass}
        />
      </div>

      {isChoice && (
        <div className="space-y-2 p-2 rounded border border-zinc-800 bg-zinc-900/40">
          <div>
            <label className={labelClass}>Options (comma-separated)</label>
            <input
              type="text"
              value={draft.optionsStr}
              onChange={(e) => patch({ optionsStr: e.target.value })}
              placeholder="Chrome, Firefox, Safari, Edge"
              className={`${inputClass} font-mono`}
            />
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 cursor-pointer text-[11px] text-zinc-400 font-mono">
              <input
                type="checkbox"
                checked={draft.allow_other}
                onChange={(e) => patch({ allow_other: e.target.checked })}
                className="rounded bg-zinc-900 border-zinc-800 text-emerald-500 focus:ring-0"
              />
              Allow an “Other” answer
            </label>
            {draft.allow_other && (
              <input
                type="text"
                value={draft.other_label}
                onChange={(e) => patch({ other_label: e.target.value })}
                placeholder="Other"
                className={`${inputClass} w-40`}
              />
            )}
          </div>
        </div>
      )}

      {(isLength || isNumber) && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          {isLength && (
            <>
              <div>
                <label className={labelClass}>Min Length</label>
                <input
                  type="number"
                  value={draft.min_length}
                  onChange={(e) => patch({ min_length: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Max Length</label>
                <input
                  type="number"
                  value={draft.max_length}
                  onChange={(e) => patch({ max_length: e.target.value })}
                  className={inputClass}
                />
              </div>
            </>
          )}
          {isNumber && (
            <>
              <div>
                <label className={labelClass}>Min Value</label>
                <input
                  type="number"
                  value={draft.min_value}
                  onChange={(e) => patch({ min_value: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Max Value</label>
                <input
                  type="number"
                  value={draft.max_value}
                  onChange={(e) => patch({ max_value: e.target.value })}
                  className={inputClass}
                />
              </div>
            </>
          )}
        </div>
      )}

      {isLength && (
        <div>
          <label className={labelClass}>Regular Expression (whole value must match)</label>
          <input
            type="text"
            value={draft.pattern}
            onChange={(e) => patch({ pattern: e.target.value })}
            placeholder="e.g. \\d{5}"
            className={`${inputClass} font-mono`}
          />
        </div>
      )}

      <div>
        <label className={labelClass}>Custom Error Message (optional)</label>
        <input
          type="text"
          value={draft.error_message}
          onChange={(e) => patch({ error_message: e.target.value })}
          placeholder="Replaces the generated wording for length / format / range failures"
          className={inputClass}
        />
      </div>

      <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-400 font-mono">
        <input
          type="checkbox"
          checked={draft.required}
          onChange={(e) => patch({ required: e.target.checked })}
          className="rounded bg-zinc-900 border-zinc-800 text-emerald-500 focus:ring-0"
        />
        Required field
      </label>

      {/* Conditional logic */}
      <div className="p-2 rounded border border-zinc-800 bg-zinc-900/40 space-y-3">
        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase text-zinc-500">
          <GitBranch className="w-3 h-3" />
          Conditional logic
          {targets.length === 0 && (
            <span className="text-zinc-600 normal-case">— add a field above first</span>
          )}
        </div>

        <ConditionGroupEditor
          title="Show only when"
          hint="No rule — always shown."
          targets={targets}
          logic={draft.visibleLogic}
          conditions={draft.visibleWhen}
          onLogicChange={(logic) => patch({ visibleLogic: logic })}
          onChange={(index, next) => patchCondition('visibleWhen', index, next)}
          onAdd={() => addCondition('visibleWhen')}
          onRemove={(index) => removeCondition('visibleWhen', index)}
        />

        <ConditionGroupEditor
          title="Required only when"
          hint="No rule — required only if the checkbox above is on."
          targets={targets}
          logic={draft.requiredLogic}
          conditions={draft.requiredWhen}
          onLogicChange={(logic) => patch({ requiredLogic: logic })}
          onChange={(index, next) => patchCondition('requiredWhen', index, next)}
          onAdd={() => addCondition('requiredWhen')}
          onRemove={(index) => removeCondition('requiredWhen', index)}
        />
      </div>

      {problem && (
        <div role="alert" className="p-2 rounded bg-rose-950/60 border border-rose-900 text-rose-300 text-[11px] flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{problem}</span>
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        {editingIndex !== null && (
          <button
            type="button"
            onClick={resetDraft}
            className="px-2.5 py-1 text-xs font-mono text-zinc-400 hover:text-zinc-200"
          >
            Cancel edit
          </button>
        )}
        <button
          type="button"
          onClick={handleSave}
          disabled={!draft.label.trim()}
          className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono rounded transition disabled:opacity-40 flex items-center gap-1"
        >
          {editingIndex === null ? <Plus className="w-3 h-3" /> : <Pencil className="w-3 h-3" />}
          {editingIndex === null ? 'Add Field' : 'Update Field'}
        </button>
      </div>

      {/* Configured fields */}
      {fields.length > 0 && (
        <div className="pt-2 border-t border-zinc-800 space-y-1.5">
          <div className="text-[10px] font-mono text-zinc-500 uppercase">
            Configured Fields ({fields.length}):
          </div>
          {fields.map((field, index) => {
            const condition = describeGroup(field.visible_when);
            const requiredWhen = describeGroup(field.required_when);
            return (
              <div
                key={`${field.key}-${index}`}
                className={`bg-zinc-900 border p-2 rounded text-xs ${
                  editingIndex === index ? 'border-amber-800' : 'border-zinc-800'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate">
                      <span className="font-semibold text-zinc-200">{field.label}</span>{' '}
                      <span className="text-[10px] font-mono text-zinc-500">
                        {field.key} · {field.type}
                      </span>
                      {field.required && <span className="text-rose-400 ml-1 font-mono text-[10px]">*req</span>}
                      {condition && (
                        <span className="text-sky-400 ml-1 font-mono text-[10px]">if {condition}</span>
                      )}
                      {requiredWhen && (
                        <span className="text-amber-400 ml-1 font-mono text-[10px]">
                          required if {requiredWhen}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] font-mono text-zinc-500 truncate">
                      {(field.options ?? []).length > 0 && (
                        <span>Options: {(field.options ?? []).join(', ')}</span>
                      )}
                      {field.allow_other && <span className="ml-1 text-emerald-500">+ Other</span>}
                      {field.help_text && <span className="ml-1">— {field.help_text}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => startEditing(index)}
                      aria-label={`Edit field ${field.label}`}
                      className="text-zinc-500 hover:text-zinc-200 p-1"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(index)}
                      aria-label={`Remove field ${field.label}`}
                      className="text-zinc-500 hover:text-rose-400 p-1"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
