import { useMemo, useState } from 'react';
import { Check, ChevronsDownUp, ChevronsUpDown, Copy, Download } from 'lucide-react';
import type { ExtractionResult } from '../api/client';

export default function JsonView({ result, jobId }: { result: ExtractionResult; jobId: string }) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => JSON.stringify(result, null, 2), [result]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (insecure context) — fall through silently */
    }
  };

  const download = () => {
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${jobId}.result.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="toolbar">
        <span className="small muted">
          <span className="mono">result</span> · {(text.length / 1024).toFixed(1)} KB · {result.groups.length} groups · {result.catalog.length} catalog fields
        </span>
        <div className="json-actions" style={{ marginLeft: 'auto' }}>
          <button type="button" className="btn btn-outline btn-xs" onClick={() => setOpen((o) => !o)}>
            {open ? <ChevronsDownUp size={12} /> : <ChevronsUpDown size={12} />} {open ? 'Collapse' : 'Expand'}
          </button>
          <button type="button" className="btn btn-outline btn-xs" onClick={download}><Download size={12} /> Download</button>
          <button type="button" className="btn btn-subtle btn-xs" onClick={copy}>
            {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? 'Copied' : 'Copy JSON'}
          </button>
        </div>
      </div>
      {open ? <pre className="json-viewer fade-in">{text}</pre> : <div className="card-body muted small">JSON collapsed — click Expand to view.</div>}
    </div>
  );
}
