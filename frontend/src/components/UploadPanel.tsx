import { useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, FileUp, FileImage, FileSpreadsheet, FileText, Info, Loader2, Play, Trash2, UploadCloud, X } from 'lucide-react';
import type { DocumentType } from '../api/client';
import { formatBytes } from '../utils/format';
import { naturalSortBy } from '../utils/naturalSort';

export const ACCEPT_EXT = ['.jpg', '.jpeg', '.png', '.webp', '.pdf', '.xlsx', '.xls', '.csv'];
const ACCEPT_ATTR = ACCEPT_EXT.join(',');

interface Props {
  busy: boolean;
  onSubmit: (files: File[], docType: DocumentType | '', caseName: string) => void;
}

function hasAllowedExt(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPT_EXT.some((ext) => lower.endsWith(ext));
}

function FileKindIcon({ name }: { name: string }) {
  const lower = name.toLowerCase();
  if (/\.(xlsx|xls|csv)$/.test(lower)) return <FileSpreadsheet size={15} color="#0D8244" />;
  if (lower.endsWith('.pdf')) return <FileText size={15} color="#C41230" />;
  return <FileImage size={15} color="#0A66C2" />;
}

export default function UploadPanel({ busy, onSubmit }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [docType, setDocType] = useState<DocumentType | ''>('');
  const [caseName, setCaseName] = useState('');
  const [rejected, setRejected] = useState<string[]>([]);

  const totalBytes = useMemo(() => files.reduce((n, f) => n + f.size, 0), [files]);
  const imageCount = useMemo(() => files.filter((f) => /\.(jpe?g|png|webp)$/i.test(f.name)).length, [files]);

  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    const ok = list.filter((f) => hasAllowedExt(f.name));
    const bad = list.filter((f) => !hasAllowedExt(f.name)).map((f) => f.name);
    setRejected(bad);
    if (!ok.length) return;
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}|${f.size}`));
      const merged = [...prev, ...ok.filter((f) => !seen.has(`${f.name}|${f.size}`))];
      return naturalSortBy(merged, (f) => f.name);
    });
  };

  const onDrag = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (busy) return;
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  };
  const onInput = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) addFiles(e.target.files);
    e.target.value = '';
  };
  const removeAt = (idx: number) => setFiles((prev) => prev.filter((_, i) => i !== idx));

  const moveUp = (idx: number) => {
    if (idx <= 0) return;
    setFiles((prev) => {
      const next = [...prev];
      const temp = next[idx - 1];
      next[idx - 1] = next[idx];
      next[idx] = temp;
      return next;
    });
  };

  const moveDown = (idx: number) => {
    setFiles((prev) => {
      if (idx >= prev.length - 1) return prev;
      const next = [...prev];
      const temp = next[idx + 1];
      next[idx + 1] = next[idx];
      next[idx] = temp;
      return next;
    });
  };

  const reSort = () => {
    setFiles((prev) => naturalSortBy(prev, (f) => f.name));
  };

  const canSubmit = files.length > 0 && !busy;

  return (
    <div className="ui-card">
      <div className="card-header">
        <h3>
          <FileUp size={17} color="#C41230" />
          <span>Upload &amp; Process</span>
        </h3>
        {files.length > 0 && (
          <button type="button" className="btn btn-outline btn-sm" onClick={() => setFiles([])} disabled={busy} title="Remove all files">
            <Trash2 size={13} /> Clear all
          </button>
        )}
      </div>

      <div className="card-body">
        <input ref={inputRef} type="file" multiple accept={ACCEPT_ATTR} style={{ display: 'none' }} onChange={onInput} />

        <div
          className={`dropzone ${dragActive ? 'drag-active' : ''} ${busy ? 'disabled' : ''}`}
          onDragEnter={onDrag}
          onDragLeave={onDrag}
          onDragOver={onDrag}
          onDrop={onDrop}
          onClick={() => !busy && inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ' ') && !busy) inputRef.current?.click();
          }}
          aria-label="Upload document files"
        >
          <div className="dropzone-icon">
            <UploadCloud size={22} />
          </div>
          <div>
            <p className="dropzone-text">Click or drag &amp; drop files here</p>
            <p className="dropzone-hint">
              Images (JPG, PNG, WEBP) · PDF · Excel (XLSX, XLS) · CSV
              <br />
              Multiple images = one multi-page document
            </p>
          </div>
        </div>

        {rejected.length > 0 && (
          <div className="banner banner-warning" style={{ marginTop: 12 }}>
            <Info size={15} />
            <div className="banner-body">
              Skipped unsupported file{rejected.length > 1 ? 's' : ''}: {rejected.join(', ')}
            </div>
          </div>
        )}

        {files.length > 0 && (
          <>
            <div className="file-list">
              {files.map((f, i) => (
                <div key={`${f.name}|${f.size}`} className="file-row">
                  <span className="file-idx">{i + 1}</span>
                  <FileKindIcon name={f.name} />
                  <span className="file-name" title={f.name}>{f.name}</span>
                  <span className="file-size">{formatBytes(f.size)}</span>
                  <div className="file-actions">
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => moveUp(i)}
                      disabled={busy || i === 0}
                      title="Move file up"
                      aria-label={`Move ${f.name} up`}
                    >
                      <ArrowUp size={13} />
                    </button>
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => moveDown(i)}
                      disabled={busy || i === files.length - 1}
                      title="Move file down"
                      aria-label={`Move ${f.name} down`}
                    >
                      <ArrowDown size={13} />
                    </button>
                    <button type="button" className="btn-icon" onClick={() => removeAt(i)} disabled={busy} title="Remove file" aria-label={`Remove ${f.name}`}>
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="file-list-meta">
              <span>
                {files.length} file{files.length > 1 ? 's' : ''} · {formatBytes(totalBytes)}
              </span>
              <button
                type="button"
                className="btn-link"
                onClick={reSort}
                disabled={busy}
                title="Reset to natural filename order"
                style={{ background: 'none', border: 'none', color: 'var(--brand-primary)', cursor: 'pointer', fontSize: '0.76rem', display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                <ArrowUpDown size={12} /> Natural order
              </button>
            </div>
            {imageCount > 1 && (
              <div className="hint-note">
                <Info size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>
                  {imageCount} images will be treated as <strong>one logical document</strong>, paged in the order shown
                  (page_1, page_2, page_2_cont, page_10 …).
                </span>
              </div>
            )}
          </>
        )}

        <div className="form-grid">
          <div className="form-field">
            <label className="form-label" htmlFor="doc-type">
              Document type hint <span className="opt">(optional)</span>
            </label>
            <select id="doc-type" className="select" value={docType} onChange={(e) => setDocType(e.target.value as DocumentType | '')} disabled={busy}>
              <option value="">Auto-detect</option>
              <option value="BENEFIT_SCHEDULE">Benefit schedule</option>
              <option value="CLAIMS">Claims history</option>
              <option value="CENSUS">Census</option>
            </select>
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="case-name">
              Case name <span className="opt">(optional)</span>
            </label>
            <input
              id="case-name"
              className="input"
              placeholder="e.g. ACME Co. renewal 2026"
              value={caseName}
              onChange={(e) => setCaseName(e.target.value)}
              disabled={busy}
              maxLength={120}
            />
          </div>
        </div>

        <div style={{ marginTop: 18 }}>
          <button type="button" className="btn btn-primary btn-full" disabled={!canSubmit} onClick={() => onSubmit(files, docType, caseName)}>
            {busy ? (
              <>
                <Loader2 size={17} className="spin" />
                <span>Processing…</span>
              </>
            ) : (
              <>
                <Play size={17} />
                <span>Process document</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
