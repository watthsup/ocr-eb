import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileImage,
  FileSpreadsheet,
  FileText,
  Maximize2,
  Minimize2,
  RotateCw,
  UploadCloud,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { naturalSortBy } from '../utils/naturalSort';
import { formatBytes } from '../utils/format';

interface Props {
  files: File[];
  selectedPage?: number;
  onPageChange?: (page: number) => void;
  title?: string;
  isProcessing?: boolean;
  onFilesAdded?: (files: File[]) => void;
}

interface PreviewItem {
  index: number;
  pageNo: number;
  file: File;
  name: string;
  url: string;
  isImage: boolean;
  isPdf: boolean;
  isSheet: boolean;
  size: number;
}

export default function DocumentViewer({
  files,
  selectedPage = 1,
  onPageChange,
  title,
  isProcessing = false,
  onFilesAdded,
}: Props) {
  // Sort files naturally so image pages are in order (page_1, page_2, etc.)
  const sortedFiles = useMemo(() => naturalSortBy(files, (f) => f.name), [files]);

  // Create and manage object URLs cleanly without leaking memory
  const [previews, setPreviews] = useState<PreviewItem[]>([]);

  useEffect(() => {
    const list: PreviewItem[] = sortedFiles.map((file, i) => {
      const lower = file.name.toLowerCase();
      const isImage = /\.(jpe?g|png|webp|bmp|gif)$/i.test(lower) || file.type.startsWith('image/');
      const isPdf = lower.endsWith('.pdf') || file.type === 'application/pdf';
      const isSheet = /\.(xlsx|xls|csv)$/i.test(lower);
      const url = URL.createObjectURL(file);
      return {
        index: i,
        pageNo: i + 1,
        file,
        name: file.name,
        url,
        isImage,
        isPdf,
        isSheet,
        size: file.size,
      };
    });

    setPreviews(list);

    return () => {
      list.forEach((item) => URL.revokeObjectURL(item.url));
    };
  }, [sortedFiles]);

  // Determine pages
  const totalPages = previews.length || 1;
  const isMultiImage = previews.length > 1 && previews.every((p) => p.isImage);

  // Active page state
  const [currentPage, setCurrentPage] = useState(1);
  const [jumpAlert, setJumpAlert] = useState<string | null>(null);
  const jumpTimer = useRef<number | null>(null);

  // Sync external selectedPage
  useEffect(() => {
    if (selectedPage && selectedPage >= 1 && selectedPage <= totalPages) {
      setCurrentPage(selectedPage);
      setJumpAlert(`Jumped to Page ${selectedPage}`);
      if (jumpTimer.current) window.clearTimeout(jumpTimer.current);
      jumpTimer.current = window.setTimeout(() => setJumpAlert(null), 2500);
    }
  }, [selectedPage, totalPages]);

  const setPage = useCallback(
    (p: number) => {
      const safe = Math.max(1, Math.min(p, totalPages));
      setCurrentPage(safe);
      onPageChange?.(safe);
    },
    [totalPages, onPageChange],
  );

  // Zoom, pan & rotation for images
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset zoom & pan when page changes
  useEffect(() => {
    setPan({ x: 0, y: 0 });
    // Keep zoom level if user is inspecting multiple pages with same scale
  }, [currentPage]);

  const handleZoomIn = () => setZoom((z) => Math.min(3.5, +(z + 0.25).toFixed(2)));
  const handleZoomOut = () => setZoom((z) => Math.max(0.4, +(z - 0.25).toFixed(2)));
  const handleResetZoom = () => {
    setZoom(1);
    setRotation(0);
    setPan({ x: 0, y: 0 });
  };
  const handleFitWidth = () => {
    setZoom(1.35);
    setPan({ x: 0, y: 0 });
  };
  const handleRotate = () => setRotation((r) => (r + 90) % 360);

  // Drag to pan image
  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoom <= 1) return;
    setIsDragging(true);
    dragStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    setPan({
      x: dragStart.current.panX + dx,
      y: dragStart.current.panY + dy,
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Current preview item
  const currentItem = previews[currentPage - 1] ?? previews[0];
  const emptyInputRef = useRef<HTMLInputElement>(null);

  if (!previews.length) {
    return (
      <div className="doc-viewer-card" style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="doc-viewer-head">
          <div className="doc-viewer-info">
            <FileText size={15} color="#C41230" />
            <span className="doc-name" style={{ fontWeight: 600 }}>Original Document Preview</span>
          </div>
        </div>
        <div
          className="doc-viewer-drop-empty"
          onClick={() => emptyInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (e.dataTransfer.files?.length && onFilesAdded) {
              onFilesAdded(Array.from(e.dataTransfer.files));
            }
          }}
          role="button"
          tabIndex={0}
        >
          <input
            ref={emptyInputRef}
            type="file"
            multiple
            accept=".jpg,.jpeg,.png,.webp,.pdf,.xlsx,.xls,.csv"
            style={{ display: 'none' }}
            onChange={(e) => {
              if (e.target.files?.length && onFilesAdded) {
                onFilesAdded(Array.from(e.target.files));
              }
            }}
          />
          <UploadCloud size={34} color="var(--generali-red)" />
          <h4 style={{ margin: '8px 0 4px', fontSize: '0.92rem' }}>Attach Document to Compare</h4>
          <p className="muted small" style={{ maxWidth: 280, textAlign: 'center', lineHeight: 1.4 }}>
            {title ? `Drop ${title} or click to select` : 'Drop images or PDF to preview side-by-side with extraction results'}
          </p>
          <button type="button" className="btn btn-outline btn-xs" style={{ marginTop: 8 }}>
            Choose document file
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`doc-viewer-card ${isFullscreen ? 'doc-viewer-fullscreen' : ''}`}
      aria-label="Document Preview and Review"
    >
      {/* Viewer Header */}
      <div className="doc-viewer-head">
        <div className="doc-viewer-info">
          <div className="doc-badge-wrap">
            {currentItem?.isImage && <FileImage size={15} color="#0A66C2" />}
            {currentItem?.isPdf && <FileText size={15} color="#C41230" />}
            {currentItem?.isSheet && <FileSpreadsheet size={15} color="#0D8244" />}
            <span className="doc-name" title={currentItem?.name || title}>
              {currentItem?.name || title || 'Document'}
            </span>
          </div>

          {totalPages > 1 && (
            <span className="page-indicator">
              Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
            </span>
          )}

          {jumpAlert && <span className="doc-jump-alert fade-in">{jumpAlert}</span>}
          {isProcessing && <span className="chip chip-xs chip-warning pulse">Analyzing…</span>}
        </div>

        {/* Page navigator & zoom controls */}
        <div className="doc-viewer-controls">
          {totalPages > 1 && (
            <div className="btn-group">
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={() => setPage(currentPage - 1)}
                disabled={currentPage <= 1}
                title="Previous page (Left arrow)"
                aria-label="Previous page"
              >
                <ChevronLeft size={14} />
              </button>
              <select
                className="select select-xs page-dropdown"
                value={currentPage}
                onChange={(e) => setPage(Number(e.target.value))}
                aria-label="Select page"
              >
                {previews.map((p, i) => (
                  <option key={p.pageNo} value={i + 1}>
                    Page {i + 1}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={() => setPage(currentPage + 1)}
                disabled={currentPage >= totalPages}
                title="Next page (Right arrow)"
                aria-label="Next page"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )}

          {/* Zoom & rotate controls for images */}
          {currentItem?.isImage && (
            <div className="btn-group zoom-group">
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={handleZoomOut}
                disabled={zoom <= 0.4}
                title="Zoom out"
                aria-label="Zoom out"
              >
                <ZoomOut size={13} />
              </button>
              <span className="zoom-level">{Math.round(zoom * 100)}%</span>
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={handleZoomIn}
                disabled={zoom >= 3.5}
                title="Zoom in"
                aria-label="Zoom in"
              >
                <ZoomIn size={13} />
              </button>
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={handleFitWidth}
                title="Fit width"
              >
                Fit
              </button>
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={handleRotate}
                title="Rotate 90° clockwise"
                aria-label="Rotate clockwise"
              >
                <RotateCw size={13} />
              </button>
              {(zoom !== 1 || rotation !== 0 || pan.x !== 0 || pan.y !== 0) && (
                <button
                  type="button"
                  className="btn btn-outline btn-xs"
                  onClick={handleResetZoom}
                  title="Reset view"
                >
                  Reset
                </button>
              )}
            </div>
          )}

          <div className="btn-group">
            {currentItem?.url && (
              <a
                href={currentItem.url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-outline btn-xs"
                title="Open file in new tab"
                aria-label="Open in new tab"
              >
                <ExternalLink size={13} />
              </a>
            )}
            <button
              type="button"
              className="btn btn-outline btn-xs"
              onClick={() => setIsFullscreen((f) => !f)}
              title={isFullscreen ? 'Exit fullscreen' : 'Expand viewer'}
              aria-label={isFullscreen ? 'Exit fullscreen' : 'Expand viewer'}
            >
              {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          </div>
        </div>
      </div>

      {/* Main Preview Stage */}
      <div
        className={`doc-viewport ${isDragging ? 'is-dragging' : ''} ${zoom > 1 ? 'can-pan' : ''}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {currentItem?.isImage && (
          <div
            className="doc-image-stage"
            style={{
              transform: `scale(${zoom}) rotate(${rotation}deg) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
              transition: isDragging ? 'none' : 'transform 0.12s ease-out',
            }}
          >
            <img
              src={currentItem.url}
              alt={`Page ${currentPage}: ${currentItem.name}`}
              className="doc-img-rendered"
              draggable={false}
            />
          </div>
        )}

        {currentItem?.isPdf && (
          <div className="doc-pdf-stage">
            <object
              data={`${currentItem.url}#page=${currentPage}&view=FitH`}
              type="application/pdf"
              className="doc-pdf-object"
            >
              <iframe
                src={`${currentItem.url}#page=${currentPage}&view=FitH`}
                className="doc-pdf-object"
                title="PDF document preview"
              />
            </object>
          </div>
        )}

        {currentItem?.isSheet && (
          <div className="doc-sheet-stage">
            <FileSpreadsheet size={40} color="#0D8244" />
            <h4>{currentItem.name}</h4>
            <p className="muted small">
              Spreadsheet file ({formatBytes(currentItem.size)}) · native data grid extracted into
              table view below.
            </p>
            <a href={currentItem.url} download={currentItem.name} className="btn btn-outline btn-sm">
              <Download size={14} /> Download {currentItem.name}
            </a>
          </div>
        )}
      </div>

      {/* Bottom Thumbnail Strip for Multi-Image Documents */}
      {isMultiImage && (
        <div className="doc-thumbnails-bar" role="tablist" aria-label="Document pages">
          {previews.map((p, i) => {
            const pageNo = i + 1;
            const active = pageNo === currentPage;
            return (
              <button
                key={p.pageNo}
                type="button"
                role="tab"
                aria-selected={active}
                className={`thumb-card ${active ? 'active' : ''}`}
                onClick={() => setPage(pageNo)}
                title={`Page ${pageNo}: ${p.name}`}
              >
                <div className="thumb-img-wrap">
                  <img src={p.url} alt={`Thumbnail ${pageNo}`} className="thumb-img" loading="lazy" />
                  <span className="thumb-badge">p.{pageNo}</span>
                </div>
                <span className="thumb-title">{p.name}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
