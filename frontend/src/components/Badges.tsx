import { AlertTriangle, CheckCircle2, CircleDashed, FileCheck, FileSpreadsheet, FileText, FileX, Hash, Sparkles, UserCheck, Users } from 'lucide-react';
import type { DocumentType, FieldStatus, FieldVerification } from '../api/client';
import { docTypeLabel, STATUS_LABEL } from '../utils/format';

/** Extraction status badge — icon + label, never colour alone. */
export function StatusBadge({ status, compact = false }: { status: FieldStatus; compact?: boolean }) {
  const cls = status === 'extracted' ? 'badge-success' : status === 'needs_review' ? 'badge-warning' : 'badge-neutral';
  const Icon = status === 'extracted' ? CheckCircle2 : status === 'needs_review' ? AlertTriangle : CircleDashed;
  const label = compact && status === 'not_found' ? 'Not Found' : STATUS_LABEL[status];
  return (
    <span className={`badge ${cls}`} title={STATUS_LABEL[status]}>
      <Icon size={12} />
      {label}
    </span>
  );
}

export function DocTypeBadge({ type, size = 13 }: { type: DocumentType | string; size?: number }) {
  const Icon = type === 'BENEFIT_SCHEDULE' ? FileText : type === 'CLAIMS' ? FileSpreadsheet : Users;
  return (
    <span className={`doc-badge ${type}`}>
      <Icon size={size} />
      {docTypeLabel(type)}
    </span>
  );
}

/** Verification chip showing deterministic code-checked result */
export function VerificationChip({ verification }: { verification?: FieldVerification }) {
  if (!verification || verification === 'not_checked') return null;
  const config = {
    in_source: { label: 'In Source', cls: 'chip-in-source', Icon: FileCheck },
    not_in_source: { label: 'Missing in Text', cls: 'chip-not-in-source', Icon: FileX },
    derived: { label: 'Derived', cls: 'chip-derived', Icon: Sparkles },
    edited: { label: 'Edited', cls: 'chip-edited', Icon: UserCheck },
  }[verification];
  if (!config) return null;
  const Icon = config.Icon;
  return (
    <span className={`verification-chip ${config.cls}`} title={`Source verification: ${config.label}`}>
      <Icon size={11} />
      {config.label}
    </span>
  );
}

export function PageChip({ page, onClick }: { page: number | null | undefined; onClick?: () => void }) {
  if (page === null || page === undefined) return null;
  return (
    <span
      className={`page-chip ${onClick ? 'clickable' : ''}`}
      title={onClick ? `View page ${page} in document preview` : `Page ${page}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <Hash size={9} />p.{page}
    </span>
  );
}
