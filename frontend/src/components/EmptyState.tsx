import { FileSearch, Upload, Cpu, ClipboardCheck } from 'lucide-react';

export default function EmptyState() {
  return (
    <div className="ui-card">
      <div className="empty-state">
        <div className="empty-state-icon">
          <FileSearch size={28} />
        </div>
        <h4>No document processed yet</h4>
        <p>
          Upload a census roster, a claims history report or a competitor benefit schedule on the left.
          Extracted fields, the plan comparison matrix and the review export will appear here.
        </p>
        <div className="empty-steps">
          <span className="chip"><Upload size={12} /> Upload</span>
          <span className="chip"><Cpu size={12} /> OCR → Classify → Extract</span>
          <span className="chip"><ClipboardCheck size={12} /> Review & export</span>
        </div>
      </div>
    </div>
  );
}
