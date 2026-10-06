import { Activity, AlertCircle, CheckCircle2, Circle, Loader2, MinusCircle, Timer, XCircle } from 'lucide-react';
import type { Job, Stage, StageStatus } from '../api/client';
import { formatMs } from '../utils/format';

/** Default stage list used before the first poll returns (mirrors the contract). */
export const DEFAULT_STAGES: Stage[] = [
  { key: 'uploaded', label: 'Uploaded', status: 'running', ms: null },
  { key: 'ocr', label: 'OCR & Layout Analysis (Azure)', status: 'pending', ms: null },
  { key: 'classifying', label: 'Classifying Document', status: 'pending', ms: null },
  { key: 'extracting', label: 'Extracting Fields', status: 'pending', ms: null },
  { key: 'normalizing', label: 'Normalizing & Validating', status: 'pending', ms: null },
  { key: 'ready', label: 'Ready for Review', status: 'pending', ms: null },
];

function StepIcon({ status }: { status: StageStatus }) {
  switch (status) {
    case 'done':
      return <CheckCircle2 size={16} />;
    case 'running':
      return <Loader2 size={16} className="spin" />;
    case 'failed':
      return <XCircle size={16} />;
    case 'skipped':
      return <MinusCircle size={16} />;
    default:
      return <Circle size={14} />;
  }
}

interface Props {
  job: Job | null;
  submitting: boolean;
  elapsedMs: number;
  error: string | null;
}

export default function ProgressTracker({ job, submitting, elapsedMs, error }: Props) {
  const stages: Stage[] = job?.stages?.length ? job.stages : submitting ? DEFAULT_STAGES : DEFAULT_STAGES.map((s) => ({ ...s, status: 'pending' }));
  const showElapsed = job !== null || submitting;

  const statusChip = !job ? null : job.status === 'completed' ? (
    <span className="chip chip-success"><CheckCircle2 size={12} /> Completed</span>
  ) : job.status === 'failed' ? (
    <span className="chip chip-red"><XCircle size={12} /> Failed</span>
  ) : (
    <span className="chip chip-info"><Loader2 size={12} className="spin" /> {job.status === 'queued' ? 'Queued' : 'Processing'}</span>
  );

  return (
    <div className="ui-card">
      <div className="card-header">
        <h3>
          <Activity size={17} color="#C41230" />
          <span>Processing pipeline</span>
        </h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {statusChip}
          {showElapsed && (
            <span className="elapsed-pill" title="Overall elapsed time">
              <Timer size={12} />
              {formatMs(elapsedMs)}
            </span>
          )}
        </div>
      </div>
      <div className="card-body">
        {job && (
          <div className="small muted" style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className="mono" title="Job ID">#{job.job_id.slice(0, 8)}</span>
            {job.case_name && <span>· {job.case_name}</span>}
            <span>· {job.filenames.length} file{job.filenames.length === 1 ? '' : 's'}</span>
          </div>
        )}

        <div className="stepper" aria-live="polite">
          {stages.map((s) => (
            <div key={s.key} className={`step ${s.status}`}>
              <div className="step-icon"><StepIcon status={s.status} /></div>
              <div className="step-label">
                {s.label}
                {s.status === 'running' && <span className="step-sub">in progress…</span>}
                {s.status === 'skipped' && <span className="step-sub" style={{ textDecoration: 'none' }}>skipped</span>}
              </div>
              <div className="step-ms">{s.status === 'done' && s.ms !== null ? formatMs(s.ms) : ''}</div>
              <div className="step-line" />
            </div>
          ))}
        </div>

        {(error || (job?.status === 'failed' && job.error)) && (
          <div className="banner banner-error" style={{ marginTop: 16 }} role="alert">
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <div className="banner-body">
              <strong>{job?.status === 'failed' ? 'Processing failed' : 'Request failed'}</strong>
              {error ?? job?.error}
            </div>
          </div>
        )}

        {!job && !submitting && !error && (
          <p className="small muted" style={{ marginTop: 12 }}>
            Stages update live every 1.5 s while the backend is working.
          </p>
        )}
      </div>
    </div>
  );
}
