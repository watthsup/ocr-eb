import { useEffect, useState, type KeyboardEvent } from 'react';
import { Loader2, PencilLine } from 'lucide-react';
import type { FieldResult, FieldValue } from '../api/client';
import { coerceInput, editableValue, formatValue } from '../utils/format';

interface Props {
  field: FieldResult;
  saving: boolean;
  disabled?: boolean;
  onCommit: (value: FieldValue) => void;
}

/** Inline editor: commits on blur / Enter when changed, Escape reverts. */
export default function EditableValue({ field, saving, disabled, onCommit }: Props) {
  const original = editableValue(field.value);
  const [text, setText] = useState(original);

  useEffect(() => {
    setText(editableValue(field.value));
  }, [field.value, field.edited]);

  const commit = () => {
    if (text === original) return;
    onCommit(coerceInput(text, field.type));
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      (e.target as HTMLInputElement).blur();
    } else if (e.key === 'Escape') {
      setText(original);
      (e.target as HTMLInputElement).blur();
    }
  };

  const placeholder = field.status === 'not_found' ? 'not found — type to add' : 'empty';
  const list = field.type === 'Enum' || field.type === 'Flag' ? `${field.field_code}-options` : undefined;
  const showRaw = field.raw_value && field.raw_value !== formatValue(field.value) && field.raw_value !== text;

  return (
    <div className="value-cell">
      <div className="value-edit">
        <input
          className={`value-input ${text === '' ? 'empty' : ''}`}
          value={text}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          onKeyDown={onKey}
          disabled={disabled || saving}
          list={list}
          title={`${field.type}${field.edited ? ' · edited by reviewer' : ''}\nEnter to save · Esc to revert`}
          aria-label={`Value for ${field.name_en}`}
        />
        {saving ? (
          <span className="value-saving" title="Saving…"><Loader2 size={13} className="spin" /></span>
        ) : field.edited ? (
          <span className="value-edited" title="Edited by reviewer"><PencilLine size={13} /></span>
        ) : null}
      </div>
      {showRaw && <div className="value-raw" title="As printed / raw value">raw: {field.raw_value}</div>}
      {field.issues.length > 0 && (
        <div className="issue-list" title={field.issues.join('\n')}>
          {field.issues.slice(0, 2).join(' · ')}
          {field.issues.length > 2 ? ` · +${field.issues.length - 2} more` : ''}
        </div>
      )}
    </div>
  );
}
