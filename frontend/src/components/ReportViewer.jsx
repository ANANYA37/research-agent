import { useState, useEffect, useRef, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import mermaid from 'mermaid';
import remarkGfm from 'remark-gfm';
import { Copy, Check, Download, FileText, Maximize2, Minimize2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../api/client';

// Retain the dark palette and select the diagram theme at render time.
const darkDiagramConfig = {
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    darkMode: true,
    background: '#0c1020',
    mainBkg: '#121832',
    primaryColor: '#3b82f6',
    primaryTextColor: '#f1f5f9',
    primaryBorderColor: '#3b82f6',
    secondaryColor: '#8b5cf6',
    secondaryTextColor: '#f1f5f9',
    tertiaryColor: '#1e293b',
    lineColor: '#64748b',
    textColor: '#94a3b8',
    fontSize: '14px',
    fontFamily: 'Inter, sans-serif',
    nodeBorder: '#3b82f6',
    clusterBkg: 'rgba(59, 130, 246, 0.08)',
    clusterBorder: 'rgba(59, 130, 246, 0.25)',
    edgeLabelBackground: '#121832',
    nodeTextColor: '#f1f5f9',
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 16,
    useMaxWidth: true,
  },
  sequence: { useMaxWidth: true },
  gantt: { useMaxWidth: true },
};

const lightDiagramConfig = {
  ...darkDiagramConfig,
  theme: 'base',
  themeVariables: {
    darkMode: false,
    background: '#fbfaf7',
    mainBkg: '#e4eee5',
    primaryColor: '#e4eee5',
    primaryTextColor: '#243c32',
    primaryBorderColor: '#2a6d53',
    secondaryColor: '#e3f3f5',
    secondaryTextColor: '#243c32',
    secondaryBorderColor: '#0e697b',
    tertiaryColor: '#f0eafb',
    tertiaryTextColor: '#243c32',
    tertiaryBorderColor: '#6d43b5',
    lineColor: '#68736c',
    textColor: '#243c32',
    fontSize: '14px',
    fontFamily: 'Inter, sans-serif',
    nodeBorder: '#2a6d53',
    clusterBkg: '#eff4ed',
    clusterBorder: '#9cb6a4',
    edgeLabelBackground: '#ffffff',
    nodeTextColor: '#243c32',
  },
};

// Mermaid configuration is global; serialize initialization and rendering.
let diagramRenderQueue = Promise.resolve();
function renderDiagram(chart, theme, isCancelled) {
  const result = diagramRenderQueue.then(async () => {
    if (isCancelled()) return null;
    mermaid.initialize({
      ...(theme === 'light' ? lightDiagramConfig : darkDiagramConfig),
      suppressErrorRendering: true,
      securityLevel: 'strict',
    });
    const valid = await mermaid.parse(chart, { suppressErrors: true });
    if (!valid) throw new Error('Invalid diagram definition');
    if (isCancelled()) return null;

    // Keep Mermaid's temporary DOM isolated, including any failed renders.
    const staging = document.createElement('div');
    staging.style.position = 'absolute';
    staging.style.visibility = 'hidden';
    staging.style.pointerEvents = 'none';
    staging.setAttribute('aria-hidden', 'true');
    document.body.appendChild(staging);
    try {
      return await mermaid.render(`mermaid-${++mermaidIdCounter}`, chart, staging);
    } finally {
      staging.remove();
    }
  });
  diagramRenderQueue = result.catch(() => {});
  return result;
}

// Counter for unique mermaid IDs across the application
let mermaidIdCounter = 0;

function MermaidChart({ chart }) {
  const containerRef = useRef(null);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'dark');

  useEffect(() => {
    const syncTheme = () => setTheme(document.documentElement.dataset.theme || 'dark');
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    syncTheme();
    return () => observer.disconnect();
  }, []);
  const [renderState, setRenderState] = useState(null);
  const status = renderState?.chart === chart && renderState?.theme === theme
    ? renderState.status : 'loading';
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !chart) return;

    let cancelled = false;
    containerRef.current.replaceChildren();

    // Clean the chart definition — strip common LLM formatting artifacts
    const cleanedChart = chart
      .replace(/\\n/g, '\n')        // literal \n → newline
      .replace(/^\s*```\w*\s*/m, '') // leading fence
      .replace(/\s*```\s*$/m, '')    // trailing fence
      .trim();

    renderDiagram(cleanedChart, theme, () => cancelled)
      .then((result) => {
        if (!cancelled && result && containerRef.current) {
          containerRef.current.innerHTML = result.svg;

          // Make the SVG responsive
          const svgEl = containerRef.current.querySelector('svg');
          if (svgEl) {
            svgEl.style.maxWidth = '100%';
            svgEl.style.height = 'auto';
            svgEl.removeAttribute('width');
          }
          setRenderState({ chart, theme, status: 'success' });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRenderState({ chart, theme, status: 'error' });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [chart, theme]);

  return (
    <div className={`mermaid-wrapper ${expanded ? 'expanded' : ''}`}>
      {status === 'error' && (
        <div className="mermaid-error" role="status">
          <div className="mermaid-error-header">
            <AlertTriangle size={16} />
            <span>This diagram could not be displayed.</span>
          </div>
          <p>The report text and sources are still available.</p>
          <details>
            <summary>View diagram source</summary>
            <pre className="mermaid-error-code">{chart}</pre>
          </details>
        </div>
      )}
      {status === 'loading' && (
        <div className="mermaid-loading">
          <div className="mermaid-loading-spinner" />
          <span>Rendering diagram…</span>
        </div>
      )}
      <div
        ref={containerRef}
        className="mermaid-chart"
        hidden={status !== 'success'}
      />
      {status === 'success' && (
        <button
          className="mermaid-expand-btn"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? 'Collapse diagram' : 'Expand diagram'}
        >
          {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
      )}
    </div>
  );
}

function ReportCode({ className, children, ...props }) {
  const match = /language-(\w+)/.exec(className || '');
  if (match?.[1] === 'mermaid') {
    return <MermaidChart chart={String(children).replace(/\n$/, '')} />;
  }
  return <code className={className} {...props}>{children}</code>;
}

export default function ReportViewer({ report, historyId }) {
  const [copied, setCopied] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [textSize, setTextSize] = useState('standard');
  const readerRef = useRef(null);
  useEffect(() => {
    if (!focusMode) return;
    const exitFocus = (event) => { if (event.key === 'Escape') setFocusMode(false); };
    document.addEventListener('keydown', exitFocus);
    return () => document.removeEventListener('keydown', exitFocus);
  }, [focusMode]);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [exporting, setExporting] = useState(null);
  const exportLock = useRef(false);
  const headings = useMemo(() => report ? report.split('\n').flatMap((line) => {
    const match = line.match(/^(#{1,3})\s+(.+)$/);
    if (!match) return [];
    const title = match[2].replace(/[*_`]/g, '').trim();
    const id = title.toLowerCase().replace(/[^a-z0-9\s-]/g, '').trim().replace(/\s+/g, '-');
    return [{ title, id }];
  }) : [], [report]);

  if (!report) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report);
      setCopied(true);
      toast.success('Report copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
      toast.error('Could not copy the report. Please try again.');
    }
  };

  const downloadBlob = (blob, format) => {
    const title = report.match(/^#\s+(.+)$/m)?.[1] || 'research-report';
    const filename = title.normalize('NFKD').replace(/[^a-zA-Z0-9\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 80).toLowerCase() || 'research-report';
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleExport = async (format) => {
    if (exportLock.current || (format !== 'md' && !historyId)) return;
    exportLock.current = true;
    setExporting(format);
    try {
      let blob;
      if (format === 'md') {
        blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
      } else {
        const response = await apiFetch(`/api/history/${historyId}/export/${format}`);
        if (!response.ok) throw new Error('Could not prepare the file. Please try again.');
        blob = await response.blob();
      }
      downloadBlob(blob, format);
      toast.success('Your download is ready');
      setActionsOpen(false);
    } catch (err) {
      toast.error(err.message || 'Download failed');
    } finally {
      exportLock.current = false;
      setExporting(null);
    }
  };

  // Detect if the report contains mermaid diagrams
  const hasDiagrams = report.includes('```mermaid');

  return (
    <div ref={readerRef} className={`report-container ${focusMode ? 'reader-focus' : ''}`}>
      <div className="report-toolbar">
        <h2>
          <FileText size={20} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
          Research Report
          {hasDiagrams && (
            <span className="report-badge diagram-badge">
              ✦ Contains Diagrams
            </span>
          )}
        </h2>
        <div className="report-reading-tools">
          <label className="report-text-size">Text <select aria-label="Report text size" value={textSize} onChange={(event) => setTextSize(event.target.value)}><option value="standard">Standard</option><option value="large">Large</option><option value="larger">Extra large</option></select></label>
          <button type="button" className="report-action-btn" aria-pressed={focusMode} onClick={() => { setFocusMode((value) => !value); readerRef.current?.scrollIntoView({ block: 'start' }); }}>{focusMode ? <Minimize2 size={14} /> : <Maximize2 size={14} />}{focusMode ? 'Exit focus' : 'Focus'}</button>
          <button type="button" className="report-action-btn" onClick={handleCopy}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}</button>
        <details className="report-actions-menu report-export-menu" open={actionsOpen} onToggle={(event) => setActionsOpen(event.currentTarget.open)}>
          <summary className="report-action-btn" aria-label="Download report"><Download size={14} /> Download</summary>
          <div className="report-actions-menu-items export-options">
            <div className="export-options-heading"><strong>Download report</strong><span>Choose how you want to use it.</span></div>
            {[{ format: 'pdf', name: 'PDF document', detail: 'Paginated report for reading and sharing', badge: 'PDF' }, { format: 'docx', name: 'Word document', detail: 'Editable headings, tables, and text', badge: 'DOCX' }, { format: 'md', name: 'Markdown source', detail: 'Original text, links, and diagram definitions', badge: 'MD' }].map(({ format, name, detail, badge }) => (
              <button key={format} type="button" className="export-format-option" disabled={!!exporting || (format !== 'md' && !historyId)} onClick={() => handleExport(format)}>
                <span className="export-format-badge">{badge}</span><span><strong>{exporting === format ? 'Preparing download…' : name}</strong><small>{detail}</small></span><Download size={14} />
              </button>
            ))}
            <p className="export-options-note">{!historyId ? 'PDF and Word become available when the report is saved.' : 'Diagrams are included as source definitions, not rendered images.'}</p>
            <span className="export-status" role="status">{exporting ? 'Preparing your file. Please wait.' : ''}</span>
          </div>
        </details></div>
      </div>

      {focusMode && <p className="reader-focus-note">Focus mode · Press Escape or choose Exit focus to return to the full report.</p>}
      <div className="report-reader">
      {headings.length > 2 && <details className="report-toc" open>
        <summary>On this page</summary>
        <ol>{headings.map((heading) => <li key={heading.id}><a href={`#${heading.id}`}>{heading.title}</a></li>)}</ol>
      </details>}
      <div className="report-card">
        <div className="report-content" style={{ fontSize: textSize === 'large' ? '1.08rem' : textSize === 'larger' ? '1.2rem' : undefined }}>
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            components={{
              h1({ children, ...props }) { const title = String(children); const id = title.toLowerCase().replace(/[^a-z0-9\s-]/g, '').trim().replace(/\s+/g, '-'); return <h1 id={id} {...props}>{children}</h1>; },
              h2({ children, ...props }) { const title = String(children); const id = title.toLowerCase().replace(/[^a-z0-9\s-]/g, '').trim().replace(/\s+/g, '-'); return <h2 id={id} {...props}>{children}</h2>; },
              h3({ children, ...props }) { const title = String(children); const id = title.toLowerCase().replace(/[^a-z0-9\s-]/g, '').trim().replace(/\s+/g, '-'); return <h3 id={id} {...props}>{children}</h3>; },
              code: ReportCode
            }}
          >
            {report}
          </ReactMarkdown>
        </div>
      </div>
      </div>
    </div>
  );
}
