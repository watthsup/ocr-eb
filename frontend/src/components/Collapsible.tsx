import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface Props {
  title: ReactNode;
  right?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
}

export default function Collapsible({ title, right, defaultOpen = false, children, className = '' }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`collapsible ${className}`}>
      <button type="button" className="collapsible-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="grow">{title}</span>
        {right}
      </button>
      {open && <div className="collapsible-body fade-in">{children}</div>}
    </div>
  );
}
