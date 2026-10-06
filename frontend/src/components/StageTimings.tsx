import { useMemo, useState } from 'react';
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Columns3,
  Eye,
  ShieldCheck,
  Sparkles,
  Timer,
  UploadCloud,
} from 'lucide-react';
import type { ExtractionResult, Job, Stage } from '../api/client';
import { formatMs } from '../utils/format';

interface Props {
  job: Job;
  result: ExtractionResult;
  defaultOpen?: boolean;
}

interface TimingStageItem {
  key: string;
  label: string;
  shortLabel: string;
  sublabel: string;
  ms: number | null;
  pct: number;
  color: string;
  Icon: typeof Clock;
}

export default function StageTimings({ job, result, defaultOpen = true }: Props) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const { timings_ms } = result;

  const totalMs = timings_ms.total || 1;

  // Granular stage items
  const stageItems = useMemo<TimingStageItem[]>(() => {
    const stageMap = new Map<string, Stage>();
    (job.stages || []).forEach((s) => stageMap.set(s.key, s));

    const uploadMs = stageMap.get('uploaded')?.ms ?? null;
    const ocrMs = timings_ms.ocr ?? stageMap.get('ocr')?.ms ?? null;
    const classifyMs = timings_ms.classifying ?? stageMap.get('classifying')?.ms ?? null;
    const extractMs = timings_ms.extracting ?? stageMap.get('extracting')?.ms ?? null;
    const normMs = timings_ms.normalizing ?? stageMap.get('normalizing')?.ms ?? null;

    const calcPct = (ms: number | null) => (ms && totalMs > 0 ? Math.round((ms / totalMs) * 100) : 0);

    const items: TimingStageItem[] = [
      {
        key: 'uploaded',
        label: 'Upload & Ingest',
        shortLabel: 'Upload',
        sublabel: `${job.filenames.length} file${job.filenames.length === 1 ? '' : 's'}`,
        ms: uploadMs,
        pct: calcPct(uploadMs),
        color: '#64748B',
        Icon: UploadCloud,
      },
      {
        key: 'ocr',
        label: 'OCR & Layout Analysis',
        shortLabel: 'OCR',
        sublabel: 'Azure Document Intelligence',
        ms: ocrMs,
        pct: calcPct(ocrMs),
        color: '#0A66C2',
        Icon: Eye,
      },
      {
        key: 'classifying',
        label: 'Classify Document',
        shortLabel: 'Classify',
        sublabel: result.document_type,
        ms: classifyMs,
        pct: calcPct(classifyMs),
        color: '#7C3AED',
        Icon: Brain,
      },
      {
        key: 'extracting',
        label: 'Extract Fields',
        shortLabel: 'Extract',
        sublabel: `${result.shards.length} shard${result.shards.length === 1 ? '' : 's'} · ${result.llm_calls} call${result.llm_calls === 1 ? '' : 's'}`,
        ms: extractMs,
        pct: calcPct(extractMs),
        color: '#C41230',
        Icon: Sparkles,
      },
      {
        key: 'normalizing',
        label: 'Normalize & Verify',
        shortLabel: 'Normalize',
        sublabel: 'Rules & source-text check',
        ms: normMs,
        pct: calcPct(normMs),
        color: '#0D8244',
        Icon: ShieldCheck,
      },
      {
        key: 'ready',
        label: 'Total Pipeline',
        shortLabel: 'Total',
        sublabel: 'Ready for Review',
        ms: timings_ms.total,
        pct: 100,
        color: '#C5A059',
        Icon: CheckCircle2,
      },
    ];

    return items;
  }, [job, result, totalMs, timings_ms]);

  // Computational segments for the visual distribution bar
  const distSegments = useMemo(() => {
    const compKeys = ['ocr', 'classifying', 'extracting', 'normalizing'];
    return stageItems
      .filter((s) => compKeys.includes(s.key) && s.ms && s.ms > 0)
      .map((s) => ({
        ...s,
        widthPct: Math.max(3, Math.round(((s.ms || 0) / totalMs) * 100)),
      }));
  }, [stageItems, totalMs]);

  // Shard specific timings if present
  const shardTimings = useMemo(() => {
    const list: { id: string; ms: number }[] = [];
    Object.entries(timings_ms).forEach(([k, v]) => {
      if (k.startsWith('extract_') && k !== 'extracting' && typeof v === 'number') {
        list.push({ id: k.replace(/^extract_/, ''), ms: v });
      }
    });
    return list;
  }, [timings_ms]);

  return (
    <div className="pipeline-timings-card">
      <div className="timings-header-row" onClick={() => setIsOpen((v) => !v)} role="button" tabIndex={0} aria-expanded={isOpen}>
        <div className="timings-title-left">
          <Timer size={15} color="var(--generali-red)" />
          <span className="timings-main-title">Stage Timings & Pipeline Performance</span>
          <span className="chip chip-xs chip-info">
            <Clock size={11} /> <strong>{formatMs(timings_ms.total)}</strong> total
          </span>
          <span className="timings-meta-summary">
            OCR: {formatMs(timings_ms.ocr)} · Classify: {formatMs(timings_ms.classifying)} · Extract: {formatMs(timings_ms.extracting)} · Normalize: {formatMs(timings_ms.normalizing)}
          </span>
        </div>
        <button
          type="button"
          className="btn btn-outline btn-xs timings-toggle-btn"
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen((v) => !v);
          }}
          aria-label={isOpen ? 'Fold stage timings' : 'Expand stage timings'}
        >
          {isOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          <span>{isOpen ? 'Fold' : 'Details'}</span>
        </button>
      </div>

      {/* Visual Proportional Distribution Bar (Always visible) */}
      <div className="timings-dist-bar-wrap" title={`Pipeline breakdown: OCR ${formatMs(timings_ms.ocr)} · Classify ${formatMs(timings_ms.classifying)} · Extract ${formatMs(timings_ms.extracting)} · Normalize ${formatMs(timings_ms.normalizing)}`}>
        <div className="timings-dist-bar">
          {distSegments.map((seg) => (
            <div
              key={seg.key}
              className="timings-dist-seg"
              style={{ width: `${seg.widthPct}%`, backgroundColor: seg.color }}
              title={`${seg.label}: ${formatMs(seg.ms)} (${seg.pct}% of total)`}
            >
              {seg.widthPct >= 12 && (
                <span className="timings-dist-label">
                  {seg.shortLabel} {seg.pct}%
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {isOpen && (
        <div className="timings-expanded-body fade-in">
          {/* Stage Cards Grid */}
          <div className="timings-stages-grid" role="list">
            {stageItems.map((st) => {
              const Icon = st.Icon;
              const isTotal = st.key === 'ready';
              return (
                <div key={st.key} className={`timing-stage-card ${isTotal ? 'is-total' : ''}`} role="listitem">
                  <div className="timing-card-top">
                    <span className="timing-stage-icon" style={{ color: st.color }}>
                      <Icon size={14} />
                    </span>
                    <span className="timing-stage-name">{st.label}</span>
                    {!isTotal && st.pct > 0 && <span className="timing-pct-badge">{st.pct}%</span>}
                    {isTotal && <span className="timing-pct-badge total-badge">100%</span>}
                  </div>
                  <div className="timing-stage-value">{formatMs(st.ms)}</div>
                  <div className="timing-stage-sub">{st.sublabel}</div>
                </div>
              );
            })}
          </div>

          {/* Shard Sub-timings if multiple shards executed */}
          {shardTimings.length > 0 && (
            <div className="timings-shards-strip">
              <span className="shards-strip-title">
                <Columns3 size={12} /> Parallel Shard Times:
              </span>
              {shardTimings.map((sh) => (
                <span key={sh.id} className="chip chip-xs">
                  Shard {sh.id}: <strong>{formatMs(sh.ms)}</strong>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
