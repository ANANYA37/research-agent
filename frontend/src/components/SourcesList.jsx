import { useId, useState } from 'react';
import { ChevronDown, ExternalLink, Globe, Search } from 'lucide-react';

export default function SourcesList({ sources = [], queriesUsed = [] }) {
  const [isOpen, setIsOpen] = useState(true);
  const [query, setQuery] = useState('');
  const listId = useId();
  const needle = query.trim().toLowerCase();
  const filtered = sources.map((source, index) => ({ ...source, number: index + 1 }))
    .filter((source) => !needle || [source.title, source.url, source.snippet].some((value) => String(value || '').toLowerCase().includes(needle)));
  const safeUrl = (value) => {
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url : null; } catch { return null; }
  };

  return (
    <>
      {sources.length > 0 && <section className="sources-container">
        <button type="button" className="sources-header source-review-toggle" onClick={() => setIsOpen((value) => !value)} aria-expanded={isOpen} aria-controls={listId}>
          <span className="source-review-title"><Globe size={16} /> Evidence & sources <span className="sources-count">{sources.length}</span></span>
          <ChevronDown size={18} className={`sources-toggle ${isOpen ? 'open' : ''}`} />
        </button>
        <div id={listId} hidden={!isOpen}>
          <div className="source-review-search"><Search size={15} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a source, website, or keyword..." aria-label="Filter report sources" /><span aria-live="polite">{filtered.length} of {sources.length}</span></div>
          <div className="sources-list">
            {filtered.map((source) => {
              const url = safeUrl(source.url);
              return <article key={source.number} className="source-item">
                <span className="source-number">{source.number}</span>
                <div className="source-info">
                  <div className="source-title">{source.title || 'Untitled source'}</div>
                  {url ? <a href={url.href} target="_blank" rel="noopener noreferrer" className="source-url" title={url.href}>{url.hostname.replace(/^www\./, '')}<ExternalLink size={12} /><span className="source-link-label">Open source</span></a> : <span className="source-url">Source link unavailable</span>}
                  {source.snippet && <details className="source-excerpt"><summary>Read excerpt</summary><p>{source.snippet}</p></details>}
                </div>
              </article>;
            })}
            {filtered.length === 0 && <p className="source-no-results">No matching sources. Try a different keyword.</p>}
          </div>
        </div>
      </section>}
      {queriesUsed.length > 0 && <details className="queries-container source-query-details">
        <summary><Search size={15} /> Search trail <span className="sources-count">{queriesUsed.length}</span></summary>
        <p>The queries used to gather evidence for this report.</p>
        <div className="queries-list">{queriesUsed.map((queryText, index) => <span key={index} className="query-tag">{queryText}</span>)}</div>
      </details>}
    </>
  );
}
