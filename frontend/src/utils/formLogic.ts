/**
 * Client-side mirror of `backend/app/services/form_logic.py`.
 *
 * The server is authoritative and re-checks everything; this copy exists so the
 * customer gets an answer before the round trip. The two implementations are
 * deliberately written the same way (same operator semantics, same messages, same
 * limits) — when a rule changes in one, change it in the other.
 */
import type {
  ConditionGroup,
  CustomFieldDefinition,
  CustomFieldValue,
  CustomFieldValues,
  FieldCondition,
} from '../types';

/** Prefix the API uses for a rejected dynamic-field answer. */
export const CUSTOM_FIELD_PREFIX = 'custom_fields.';

export const MAX_CUSTOM_FIELDS = 50;
export const MAX_MULTI_SELECT_ITEMS = 50;
export const MAX_OTHER_LENGTH = 255;

export const FIELD_TYPE_MAX_LENGTH: Record<string, number> = {
  text: 500,
  textarea: 5000,
  url: 500,
  date: 10,
  select: MAX_OTHER_LENGTH,
};

export const MIN_TITLE_LENGTH = 3;
export const MAX_TITLE_LENGTH = 255;
export const MIN_DESCRIPTION_LENGTH = 5;
export const MAX_DESCRIPTION_LENGTH = 20000;
export const MAX_TAGS_LENGTH = 500;
export const MAX_TARGET_URL_LENGTH = 500;

export const BASE_CATEGORIES = ['technical', 'billing', 'account', 'general'];
export const BASE_PRIORITIES = ['low', 'medium', 'high', 'urgent'];

export interface CustomFieldError {
  code: string;
  message: string;
}

/** The value a control starts with, before the customer types anything. */
export function emptyValueFor(field: CustomFieldDefinition): CustomFieldValue {
  if (field.type === 'switch') return false;
  if (field.type === 'multi_select') return [];
  return '';
}

// --- Value helpers -----------------------------------------------------------

export function isBlank(value: CustomFieldValue | undefined | null): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (typeof value === 'boolean') return false; // an explicit "No" is an answer
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

function toBool(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const text = value.trim().toLowerCase();
    if (['true', 'yes', 'on', '1'].includes(text)) return true;
    if (['false', 'no', 'off', '0', ''].includes(text)) return false;
  }
  return null;
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'boolean') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const text = value.trim();
    if (text === '' || /^[+-]?0[xX]/.test(text)) return null;
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asItems(value: unknown): string[] {
  if (value === undefined || value === null) return [];
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return [String(value)];
}

function scalarEquals(actual: unknown, expected: unknown): boolean {
  if (typeof actual === 'boolean' || typeof expected === 'boolean') {
    const left = toBool(actual);
    const right = toBool(expected);
    if (left !== null && right !== null) return left === right;
  }
  const leftNumber = toNumber(actual);
  const rightNumber = toNumber(expected);
  if (leftNumber !== null && rightNumber !== null) return leftNumber === rightNumber;
  if (actual === undefined || actual === null || expected === undefined || expected === null) {
    return (actual ?? null) === (expected ?? null);
  }
  return String(actual).trim().toLowerCase() === String(expected).trim().toLowerCase();
}

function matchesScalar(actual: unknown, expected: unknown): boolean {
  if (Array.isArray(actual)) return actual.some((item) => scalarEquals(item, expected));
  return scalarEquals(actual, expected);
}

function contains(actual: unknown, expected: unknown): boolean {
  if (Array.isArray(actual)) return actual.some((item) => contains(item, expected));
  if (actual === undefined || actual === null || expected === undefined || expected === null) return false;
  return String(actual).trim().toLowerCase().includes(String(expected).trim().toLowerCase());
}

function compareNumeric(actual: unknown, expected: unknown, operators: string[]): boolean {
  const left = toNumber(actual);
  const right = toNumber(expected);
  if (left === null || right === null) return false;
  if (operators.includes('gt') && left > right) return true;
  if (operators.includes('gte') && left >= right) return true;
  if (operators.includes('lt') && left < right) return true;
  if (operators.includes('lte') && left <= right) return true;
  return false;
}

// --- Conditions --------------------------------------------------------------

export function conditionMatches(
  condition: FieldCondition,
  values: CustomFieldValues,
): boolean {
  if (!condition?.field) return true;
  const actual = values[condition.field];
  const expected = condition.value;
  const list = Array.isArray(expected) ? expected : [expected];

  switch (condition.operator) {
    case 'is_answered':
      return !isBlank(actual);
    case 'is_empty':
      return isBlank(actual);
    case 'equals':
      return list.some((item) => matchesScalar(actual, item));
    case 'not_equals':
      return !list.some((item) => matchesScalar(actual, item));
    case 'contains':
      return contains(actual, expected);
    case 'not_contains':
      return !contains(actual, expected);
    case 'in':
      return list.some((item) => matchesScalar(actual, item));
    case 'not_in':
      return !list.some((item) => matchesScalar(actual, item));
    case 'gt':
      return compareNumeric(actual, expected, ['gt']);
    case 'gte':
      return compareNumeric(actual, expected, ['gt', 'gte']);
    case 'lt':
      return compareNumeric(actual, expected, ['lt']);
    case 'lte':
      return compareNumeric(actual, expected, ['lt', 'lte']);
    default:
      return true;
  }
}

export function groupMatches(group: ConditionGroup | null | undefined, values: CustomFieldValues): boolean {
  if (!group || !group.conditions || group.conditions.length === 0) return true;
  const results = group.conditions.map((condition) => conditionMatches(condition, values));
  return group.logic === 'any' ? results.some(Boolean) : results.every(Boolean);
}

export interface FormEvaluation {
  visible: CustomFieldDefinition[];
  hiddenKeys: string[];
  /** Lightly trimmed answers, used as the input of every condition. */
  values: CustomFieldValues;
}

/**
 * Resolve visibility in one forward pass: a field is only ever influenced by the
 * fields above it, so hiding a field hides whatever depended on it.
 */
export function evaluateForm(fields: CustomFieldDefinition[], values: CustomFieldValues): FormEvaluation {
  const trimmed: CustomFieldValues = {};
  Object.entries(values).forEach(([key, value]) => {
    trimmed[key] = typeof value === 'string' ? value.trim() : value;
  });

  const visible: CustomFieldDefinition[] = [];
  const hiddenKeys: string[] = [];
  const effective: CustomFieldValues = {};

  fields.forEach((field) => {
    if (groupMatches(field.visible_when, effective)) {
      visible.push(field);
      effective[field.key] = trimmed[field.key];
    } else {
      hiddenKeys.push(field.key);
    }
  });

  return { visible, hiddenKeys, values: trimmed };
}

export function isFieldRequired(field: CustomFieldDefinition, values: CustomFieldValues): boolean {
  if (field.required) return true;
  return Boolean(field.required_when) && groupMatches(field.required_when, values);
}

export function isFieldVisible(field: CustomFieldDefinition, values: CustomFieldValues): boolean {
  return groupMatches(field.visible_when, values);
}

// --- Field validation --------------------------------------------------------

function error(field: CustomFieldDefinition, message: string, code = 'invalid'): CustomFieldError {
  return { code, message };
}

function constraintError(field: CustomFieldDefinition, generated: string, code: string): CustomFieldError {
  return error(field, field.error_message || generated, code);
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(value);
}

function optionListMessage(field: CustomFieldDefinition): string {
  const options = field.options || [];
  const shown = options.slice(0, 8);
  let listing = shown.join(', ');
  if (options.length > shown.length) listing += ', ...';
  return `${field.label} must be one of: ${listing}`;
}

function validateTextLike(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
): { value?: CustomFieldValue; error?: CustomFieldError } {
  if (typeof value === 'boolean' || Array.isArray(value)) {
    return { error: error(field, `${field.label} must be text.`) };
  }
  const text = String(value).trim();
  const minimum = field.min_length || 0;
  const maximum = field.max_length || FIELD_TYPE_MAX_LENGTH[field.type] || 500;

  if (text.length < minimum) {
    return { error: constraintError(field, `${field.label} must be at least ${minimum} characters.`, 'too_short') };
  }
  if (text.length > maximum) {
    return { error: constraintError(field, `${field.label} must be at most ${maximum} characters.`, 'too_long') };
  }
  if (field.pattern) {
    try {
      if (!new RegExp(`^(?:${field.pattern})$`).test(text)) {
        return { error: constraintError(field, `${field.label} has an invalid format.`, 'pattern_mismatch') };
      }
    } catch {
      // A broken pattern must not lock the form; the API rejects it on save.
    }
  }
  if (field.type === 'url' && text !== '') {
    let valid = false;
    try {
      const parsed = new URL(text);
      valid = parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
      valid = false;
    }
    if (!valid) {
      return { error: error(field, `${field.label} must be a full URL starting with http:// or https://`, 'invalid_url') };
    }
  }
  if (field.type === 'date') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
      return { error: error(field, `${field.label} must be a date in YYYY-MM-DD format.`, 'invalid_date') };
    }
    const [year, month, day] = text.split('-').map(Number);
    const parsed = new Date(Date.UTC(year, month - 1, day));
    if (
      parsed.getUTCFullYear() !== year ||
      parsed.getUTCMonth() !== month - 1 ||
      parsed.getUTCDate() !== day
    ) {
      return { error: error(field, `${field.label} must be a date in YYYY-MM-DD format.`, 'invalid_date') };
    }
  }
  return { value: text };
}

function validateNumber(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
): { value?: CustomFieldValue; error?: CustomFieldError } {
  const number = toNumber(value);
  if (number === null) {
    return { error: constraintError(field, `${field.label} must be a number.`, 'not_a_number') };
  }
  if (field.min_value !== undefined && field.min_value !== null && number < field.min_value) {
    return {
      error: constraintError(field, `${field.label} must be at least ${formatNumber(field.min_value)}.`, 'too_small'),
    };
  }
  if (field.max_value !== undefined && field.max_value !== null && number > field.max_value) {
    return {
      error: constraintError(field, `${field.label} must be at most ${formatNumber(field.max_value)}.`, 'too_large'),
    };
  }
  return { value: number };
}

function validateSwitch(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
): { value?: CustomFieldValue; error?: CustomFieldError } {
  const boolean = toBool(value);
  if (boolean === null) return { error: error(field, `${field.label} must be yes or no.`) };
  return { value: boolean };
}

function validateSelect(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
): { value?: CustomFieldValue; error?: CustomFieldError } {
  if (Array.isArray(value) || typeof value === 'boolean') {
    return { error: error(field, `${field.label} must be a single choice.`) };
  }
  const text = String(value).trim();
  const options = field.options || [];
  if (options.includes(text)) return { value: text };
  if (field.allow_other) {
    if (text.length > MAX_OTHER_LENGTH) {
      return {
        error: error(
          field,
          `${field.label}: a custom answer must be at most ${MAX_OTHER_LENGTH} characters.`,
          'too_long',
        ),
      };
    }
    return { value: text };
  }
  return { error: error(field, optionListMessage(field), 'not_an_option') };
}

function validateMultiSelect(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
): { value?: CustomFieldValue; error?: CustomFieldError } {
  if (typeof value === 'boolean' || typeof value === 'number') {
    return { error: error(field, `${field.label} must be a list of choices.`) };
  }
  const items = asItems(value);
  if (items.length > MAX_MULTI_SELECT_ITEMS) {
    return {
      error: error(field, `${field.label} accepts at most ${MAX_MULTI_SELECT_ITEMS} choices.`, 'too_many_choices'),
    };
  }

  const options = field.options || [];
  const selected: string[] = [];
  const custom: string[] = [];

  for (const item of items) {
    const text = item.trim();
    if (!text) continue;
    if (options.includes(text)) {
      if (!selected.includes(text)) selected.push(text);
    } else if (field.allow_other) {
      if (text.length > MAX_OTHER_LENGTH) {
        return {
          error: error(
            field,
            `${field.label}: a custom answer must be at most ${MAX_OTHER_LENGTH} characters.`,
            'too_long',
          ),
        };
      }
      custom.push(text);
    } else {
      return { error: error(field, optionListMessage(field), 'not_an_option') };
    }
  }

  if (custom.length > 1) {
    return {
      error: error(field, `${field.label} accepts a single custom answer.`, 'too_many_custom_answers'),
    };
  }
  custom.forEach((text) => {
    if (!selected.includes(text)) selected.push(text);
  });
  return { value: selected };
}

export function validateField(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
): { value?: CustomFieldValue; error?: CustomFieldError } {
  switch (field.type) {
    case 'number':
      return validateNumber(field, value);
    case 'switch':
      return validateSwitch(field, value);
    case 'select':
      return validateSelect(field, value);
    case 'multi_select':
      return validateMultiSelect(field, value);
    default:
      return validateTextLike(field, value);
  }
}

export interface CustomFieldValidation {
  /** Visible, valid answers only — exactly what should be sent to the API. */
  values: CustomFieldValues;
  /** Keyed by field key (no `custom_fields.` prefix). */
  errors: Record<string, CustomFieldError>;
}

/**
 * Validate a whole dynamic form. Reports every problem at once rather than
 * stopping at the first, so the customer can fix the form in one pass.
 */
export function validateCustomFields(
  fields: CustomFieldDefinition[],
  values: CustomFieldValues,
): CustomFieldValidation {
  const errors: Record<string, CustomFieldError> = {};
  const evaluation = evaluateForm(fields, values);
  const cleaned: CustomFieldValues = {};

  evaluation.visible.forEach((field) => {
    const value = evaluation.values[field.key];
    const required = isFieldRequired(field, evaluation.values);

    if (isBlank(value)) {
      if (required) errors[field.key] = error(field, `${field.label} is required.`, 'required');
      return;
    }

    const result = validateField(field, value as CustomFieldValue);
    if (result.error) {
      errors[field.key] = result.error;
      return;
    }
    if (isBlank(result.value)) {
      if (required) errors[field.key] = error(field, `${field.label} is required.`, 'required');
      return;
    }
    cleaned[field.key] = result.value;
  });

  return { values: cleaned, errors };
}

// --- Built-in ticket fields --------------------------------------------------

export interface BaseTicketInput {
  title: string;
  description: string;
  tags?: string;
  target_url?: string;
  category: string;
  priority: string;
}

export interface BaseTicketValidation {
  cleaned: {
    title: string;
    description: string;
    tags: string;
    target_url: string | undefined;
    category: string;
    priority: string;
  };
  /** Keyed by the API field name: `title`, `description`, `tags`, `target_url`, … */
  errors: Record<string, string>;
}

/** Mirror of `validate_base_fields` in `app/services/form_logic.py`. */
export function validateBaseFields(input: BaseTicketInput): BaseTicketValidation {
  const errors: Record<string, string> = {};

  const title = (input.title || '').trim();
  if (!title) {
    errors.title = 'A ticket subject is required.';
  } else if (title.length < MIN_TITLE_LENGTH) {
    errors.title = `The ticket subject must be at least ${MIN_TITLE_LENGTH} characters.`;
  } else if (title.length > MAX_TITLE_LENGTH) {
    errors.title = `The ticket subject must be at most ${MAX_TITLE_LENGTH} characters.`;
  }

  const description = (input.description || '').trim();
  if (!description) {
    errors.description = 'A description of the problem is required.';
  } else if (description.length < MIN_DESCRIPTION_LENGTH) {
    errors.description = `The description must be at least ${MIN_DESCRIPTION_LENGTH} characters.`;
  } else if (description.length > MAX_DESCRIPTION_LENGTH) {
    errors.description = `The description must be at most ${MAX_DESCRIPTION_LENGTH} characters.`;
  }

  const tags = (input.tags || '').trim().replace(/^,+|,+$/g, '').trim();
  if (tags.length > MAX_TAGS_LENGTH) {
    errors.tags = `Tags must be at most ${MAX_TAGS_LENGTH} characters.`;
  }

  const rawUrl = (input.target_url || '').trim();
  let targetUrl: string | undefined;
  if (rawUrl) {
    if (rawUrl.length > MAX_TARGET_URL_LENGTH) {
      errors.target_url = `The page URL must be at most ${MAX_TARGET_URL_LENGTH} characters.`;
    } else if (!/^https?:\/\/[^\s]+$/i.test(rawUrl)) {
      errors.target_url = 'The page URL must start with http:// or https://';
    } else {
      targetUrl = rawUrl;
    }
  }

  if (!BASE_CATEGORIES.includes(input.category)) {
    errors.category = `Unknown category '${input.category}'.`;
  }
  if (!BASE_PRIORITIES.includes(input.priority)) {
    errors.priority = `Unknown priority '${input.priority}'.`;
  }

  return {
    cleaned: {
      title,
      description,
      tags,
      target_url: targetUrl,
      category: input.category,
      priority: input.priority,
    },
    errors,
  };
}

// --- Admin-side schema linting -----------------------------------------------

export interface SchemaProblem {
  /** `fields_schema.<index>` for a per-field problem. */
  field: string;
  message: string;
  code: string;
}

/** Mirror of `validate_field_schema`; the API enforces the same rules on save. */
export function validateFieldSchema(fields: CustomFieldDefinition[]): SchemaProblem[] {
  const problems: SchemaProblem[] = [];
  if (fields.length > MAX_CUSTOM_FIELDS) {
    return [
      {
        field: 'fields_schema',
        message: `A ticket type can define at most ${MAX_CUSTOM_FIELDS} fields.`,
        code: 'too_many_fields',
      },
    ];
  }

  const seen = new Map<string, number>();
  fields.forEach((field, index) => {
    if (seen.has(field.key)) {
      problems.push({
        field: `fields_schema.${index}`,
        message: `Duplicate field key '${field.key}' (also used by field #${(seen.get(field.key) || 0) + 1}).`,
        code: 'duplicate_key',
      });
    } else {
      seen.set(field.key, index);
    }
  });

  fields.forEach((field, index) => {
    const address = `fields_schema.${index}`;
    (['visible_when', 'required_when'] as const).forEach((attribute) => {
      const group = field[attribute];
      if (!group) return;
      group.conditions.forEach((condition) => {
        if (condition.field === field.key) {
          problems.push({
            field: address,
            message: `'${field.label}' cannot depend on itself (${attribute}).`,
            code: 'self_reference',
          });
          return;
        }
        if (!seen.has(condition.field)) {
          problems.push({
            field: address,
            message: `'${field.label}' depends on an unknown field '${condition.field}' (${attribute}).`,
            code: 'unknown_reference',
          });
          return;
        }
        if ((seen.get(condition.field) as number) >= index) {
          problems.push({
            field: address,
            message: `'${field.label}' can only depend on fields defined above it ('${condition.field}' comes later).`,
            code: 'forward_reference',
          });
        }
      });
    });
  });

  return problems;
}
