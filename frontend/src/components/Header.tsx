import { useCallback, useEffect, useState } from 'react';
import { Layers, ListChecks } from 'lucide-react';
import { getHealth, type CatalogResponse, type HealthResponse } from '../api/client';
import { shortVersion } from '../utils/format';

type HealthState = 'checking' | 'online' | 'offline';

interface Props {
  catalog: CatalogResponse | null;
  catalogError?: string | null;
}

export default function Header({ catalog, catalogError }: Props) {
  const [state, setState] = useState<HealthState>('checking');
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const check = useCallback(async () => {
    try {
      const h = await getHealth();
      setHealth(h);
      setState(h.status === 'healthy' || h.status === 'ok' ? 'online' : 'offline');
    } catch {
      setState('offline');
    }
  }, []);

  useEffect(() => {
    void check();
    const id = window.setInterval(() => void check(), 20_000);
    return () => window.clearInterval(id);
  }, [check]);

  const fieldCount = catalog
    ? Object.values(catalog.doc_types).reduce((n, specs) => n + specs.length, 0)
    : health?.catalog?.field_count ?? null;
  const catalogVersion = catalog?.version ?? health?.catalog?.version ?? null;

  const healthTitle =
    state === 'online' && health
      ? [
          `Service: ${health.service}`,
          `LLM: ${health.llm.provider} / ${health.llm.model} (${health.llm.enabled ? 'enabled' : 'disabled'})`,
          `OCR engine: ${health.ocr_engine}`,
          `Catalog: v${shortVersion(health.catalog?.version)} · ${health.catalog?.field_count ?? '?'} fields`,
        ].join('\n')
      : state === 'offline'
        ? 'Backend unreachable on :8000 — start the FastAPI server'
        : 'Connecting to backend…';

  const pillLabel =
    state === 'online'
      ? `API Online · ${health?.llm?.model ?? 'LLM'} · ${health?.ocr_engine === 'mock' ? 'Mock OCR' : 'Azure DI'}`
      : state === 'offline'
        ? 'API Offline'
        : 'Connecting…';

  return (
    <>
      <div className="top-ribbon" />
      <header className="site-header">
        <div className="header-inner">
          <div className="brand-section">
            <div className="brand-logo-badge" title="Generali Group IDP">G</div>
            <div className="brand-info">
              <h1>Generali Group IDP</h1>
              <div className="brand-subtitle">
                <Layers size={13} color="#C41230" />
                <span>Census · Claims · Benefit Schedule extraction</span>
              </div>
            </div>
          </div>

          <div className="header-actions">
            <span
              className="chip chip-gold"
              title={
                catalogError
                  ? `Catalog unavailable: ${catalogError}`
                  : catalog
                    ? `Field catalog loaded from ${catalog.source}\n` +
                      Object.entries(catalog.doc_types).map(([k, v]) => `${k}: ${v.length}`).join(' · ')
                    : 'Loading field catalog…'
              }
            >
              <ListChecks size={12} />
              {fieldCount !== null ? `${fieldCount} target fields` : 'catalog …'}
              {catalogVersion && <span className="mono" style={{ opacity: 0.8 }}>· v{shortVersion(catalogVersion)}</span>}
            </span>
            <div className={`health-pill ${state === 'online' ? 'online' : state === 'offline' ? 'offline' : ''}`} title={healthTitle}>
              <span className="status-dot" />
              <span>{pillLabel}</span>
            </div>
          </div>
        </div>
      </header>
    </>
  );
}
