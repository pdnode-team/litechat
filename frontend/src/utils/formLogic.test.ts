import { describe, expect, it } from 'vitest';
import type { CustomFieldDefinition } from '../types';
import {
  evaluateForm,
  isFieldRequired,
  isFieldVisible,
  validateCustomFields,
} from './formLogic';

function field(partial: Partial<CustomFieldDefinition> & Pick<CustomFieldDefinition, 'key' | 'label'>): CustomFieldDefinition {
  return {
    type: 'text',
    required: false,
    ...partial,
  };
}

describe('condition evaluation', () => {
  it('treats equals as case-insensitive and type-tolerant', () => {
    const target = field({
      key: 'extra',
      label: 'Extra',
      visible_when: { logic: 'all', conditions: [{ field: 'severity', operator: 'equals', value: 'High' }] },
    });
    expect(isFieldVisible(target, { severity: ' high ' })).toBe(true);
    expect(isFieldVisible(target, { severity: 'HIGH' })).toBe(true);
    expect(isFieldVisible(target, { severity: 'Low' })).toBe(false);
    expect(isFieldVisible(target, {})).toBe(false);
  });

  it('combines all/any groups', () => {
    const first = { field: 'a', operator: 'equals' as const, value: '1' };
    const second = { field: 'b', operator: 'equals' as const, value: '2' };
    const both = field({
      key: 'x',
      label: 'X',
      visible_when: { logic: 'all', conditions: [first, second] },
    });
    const either = field({
      key: 'y',
      label: 'Y',
      visible_when: { logic: 'any', conditions: [first, second] },
    });
    expect(isFieldVisible(both, { a: '1', b: '2' })).toBe(true);
    expect(isFieldVisible(both, { a: '1' })).toBe(false);
    expect(isFieldVisible(either, { a: '1' })).toBe(true);
    expect(isFieldVisible(either, { c: '3' })).toBe(false);
  });
});

describe('visibility', () => {
  const schema: CustomFieldDefinition[] = [
    field({ key: 'severity', label: 'Severity', type: 'select', options: ['Low', 'High'] }),
    field({
      key: 'crash_id',
      label: 'Crash id',
      visible_when: { logic: 'all', conditions: [{ field: 'severity', operator: 'equals', value: 'High' }] },
    }),
    field({
      key: 'trace',
      label: 'Trace',
      visible_when: { logic: 'all', conditions: [{ field: 'crash_id', operator: 'is_answered' }] },
    }),
  ];

  it('hides dependents of a hidden field', () => {
    const low = evaluateForm(schema, { severity: 'Low', crash_id: 'abc', trace: 'boom' });
    expect(low.visible.map((item) => item.key)).toEqual(['severity']);
    expect(low.hiddenKeys).toEqual(['crash_id', 'trace']);
  });

  it('drops answers to hidden fields instead of storing them', () => {
    const result = validateCustomFields(
      [
        field({ key: 'severity', label: 'Severity', type: 'select', options: ['Low', 'High'] }),
        field({
          key: 'downtime',
          label: 'Downtime',
          type: 'number',
          visible_when: { logic: 'all', conditions: [{ field: 'severity', operator: 'equals', value: 'High' }] },
        }),
      ],
      { severity: 'Low', downtime: 90 },
    );
    expect(result.errors).toEqual({});
    expect(result.values).toEqual({ severity: 'Low' });
  });

  it('applies required_when only while the condition holds', () => {
    const conditional = field({
      key: 'crash_id',
      label: 'Crash id',
      required_when: { logic: 'all', conditions: [{ field: 'severity', operator: 'equals', value: 'High' }] },
    });
    expect(isFieldRequired(conditional, { severity: 'High' })).toBe(true);
    expect(isFieldRequired(conditional, { severity: 'Low' })).toBe(false);
  });
});

describe('field constraints', () => {
  it('uses the administrator message for length failures', () => {
    const schema = [
      field({
        key: 'order',
        label: 'Order number',
        min_length: 6,
        max_length: 8,
        error_message: 'Order numbers are 6 to 8 characters.',
      }),
    ];
    const short = validateCustomFields(schema, { order: '123' });
    expect(short.errors.order?.message).toBe('Order numbers are 6 to 8 characters.');

    const ok = validateCustomFields(schema, { order: ' 123456 ' });
    expect(ok.errors).toEqual({});
    expect(ok.values).toEqual({ order: '123456' });
  });

  it('requires a pattern to match the whole value', () => {
    const schema = [field({ key: 'zip', label: 'ZIP', pattern: String.raw`\d{5}` })];
    expect(validateCustomFields(schema, { zip: '12345' }).errors).toEqual({});
    expect(validateCustomFields(schema, { zip: '123456' }).errors.zip?.code).toBe('pattern_mismatch');
    expect(validateCustomFields(schema, { zip: 'x12345' }).errors.zip).toBeTruthy();
  });

  it('enforces numeric range', () => {
    const schema = [field({ key: 'count', label: 'Count', type: 'number', min_value: 1, max_value: 10 })];
    expect(validateCustomFields(schema, { count: 5 }).values).toEqual({ count: 5 });
    expect(validateCustomFields(schema, { count: 0 }).errors.count).toBeTruthy();
    expect(validateCustomFields(schema, { count: 11 }).errors.count).toBeTruthy();
  });

  it('does not require a required field that is currently hidden', () => {
    const schema = [
      field({ key: 'severity', label: 'Severity', type: 'select', options: ['Low', 'High'] }),
      field({
        key: 'crash_id',
        label: 'Crash id',
        required: true,
        visible_when: { logic: 'all', conditions: [{ field: 'severity', operator: 'equals', value: 'High' }] },
      }),
    ];
    const hidden = validateCustomFields(schema, { severity: 'Low' });
    expect(hidden.errors).toEqual({});
    const shown = validateCustomFields(schema, { severity: 'High' });
    expect(shown.errors.crash_id?.code).toBe('required');
  });
});
