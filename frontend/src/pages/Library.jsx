import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, ArrowRight, Search, FileText, FolderPlus, Tag, SlidersHorizontal, Plus, Globe2, BookOpen, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, apiFetch } from '../api/client';
import { readPreferences, usePreferences } from '../preferences';
import './Library.css';

export default function Library() {

  const preferences = usePreferences();
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(null);
  const [history, setHistory] = useState([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState(null);
  const [collectionName, setCollectionName] = useState('');
  const [tagName, setTagName] = useState('');
  const [collections, setCollections] = useState([]);
  const [tags, setTags] = useState([]);
  const [filter, setFilter] = useState({ type: 'all', id: null });
  const [sort, setSort] = useState(() => readPreferences().sort);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const [response, collectionItems, tagItems] = await Promise.all([
          apiFetch('/api/history'), api.collections(), api.tags(),
        ]);
        if (!response.ok) throw new Error('Could not load report library');
        setHistory(await response.json());
        setCollections(collectionItems);
        setTags(tagItems);
      } catch (err) {
        setError(err.message);
        toast.error('Failed to load library');
      }
    };

    loadHistory().finally(() => setLoading(false));
  }, []);

  const addCollection = async (event) => {
    event.preventDefault();
    if (!collectionName.trim() || creating) return;
    setCreating('collection');
    try {
      const created = await api.createCollection({ name: collectionName.trim() });
      setCollections((items) => [...items, created]);
      setCollectionName('');
    } catch (err) { toast.error(err.message); } finally { setCreating(null); }
  };

  const addTag = async (event) => {
    event.preventDefault();
    if (!tagName.trim() || creating) return;
    setCreating('tag');
    try {
      const created = await api.createTag({ name: tagName.trim() });
      setTags((items) => [...items, created]);
      setTagName('');
    } catch (err) { toast.error(err.message); } finally { setCreating(null); }
  };

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return history.filter((item) => {
      const matchesQuery = !needle || item.topic.toLowerCase().includes(needle);
      const attached = filter.type === 'collection' ? item.collections?.some((value) => value.id === filter.id)
        : filter.type === 'tag' ? item.tags?.some((value) => value.id === filter.id) : true;
      return matchesQuery && attached;
    }).sort((a, b) => sort === 'sources' ? (b.sources_count || 0) - (a.sources_count || 0)
      : sort === 'oldest' ? new Date(a.updated_at) - new Date(b.updated_at)
        : new Date(b.updated_at) - new Date(a.updated_at));
  }, [history, query, filter, sort]);

  const activeName = filter.type === 'all' ? 'All reports'
    : (filter.type === 'collection' ? collections : tags).find((item) => item.id === filter.id)?.name || 'Filtered reports';
  const totalSources = history.reduce((sum, item) => sum + (item.sources_count || 0), 0);
  const formatDate = (value) => {
    if (!value || Number.isNaN(new Date(value).getTime())) return 'Date unavailable';
    return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <main className={`research-studio workspace-page lib-page ${preferences.compact ? 'lib-compact' : ''}`}>
      <div className="workspace-inner">
        <header className="lib-heading">
          <div><span className="lib-eyebrow">WORKSPACE / LIBRARY</span><h1>Research library</h1><p>Your saved reports, organized and ready to revisit.</p></div>
          <Link className="lib-primary" to="/chat"><Plus size={16} /> New research</Link>
        </header>
        {!loading && !error && <div className="lib-overview" aria-label="Library overview"><span><FileText size={14} /><strong>{history.length}</strong> reports</span><span><FolderPlus size={14} /><strong>{collections.length}</strong> collections</span><span><Globe2 size={14} /><strong>{totalSources}</strong> source references</span></div>}

        <div className="lib-layout">
          <aside className="lib-sidebar" aria-label="Organize and filter reports">
            <button type="button" className={`lib-filter ${filter.type === 'all' ? 'selected' : ''}`} aria-pressed={filter.type === 'all'} onClick={() => setFilter({ type: 'all', id: null })}><Archive size={16} /><span>All reports</span><small>{history.length}</small></button>
            <section className="lib-filter-section" aria-labelledby="lib-collections">
              <h2 id="lib-collections">Collections <span>{collections.length}</span></h2>
              {collections.map((item) => <button type="button" key={item.id} className={`lib-filter ${filter.type === 'collection' && filter.id === item.id ? 'selected' : ''}`} aria-pressed={filter.type === 'collection' && filter.id === item.id} onClick={() => setFilter({ type: 'collection', id: item.id })}><FolderPlus size={15} /><span>{item.name}</span></button>)}
              {!loading && collections.length === 0 && <p className="lib-sidebar-hint">Group related research into a collection.</p>}
              <details className="lib-create"><summary><Plus size={13} /> New collection</summary><form onSubmit={addCollection}><label htmlFor="lib-collection-name">Collection name</label><input id="lib-collection-name" value={collectionName} onChange={(event) => setCollectionName(event.target.value)} placeholder="e.g. Market research" maxLength={100} required disabled={creating === 'collection'} /><button type="submit" disabled={!collectionName.trim() || creating === 'collection'}>{creating === 'collection' ? 'Creating…' : 'Create collection'}</button></form></details>
            </section>
            <section className="lib-filter-section" aria-labelledby="lib-tags">
              <h2 id="lib-tags">Tags <span>{tags.length}</span></h2>
              {tags.map((item) => <button type="button" key={item.id} className={`lib-filter ${filter.type === 'tag' && filter.id === item.id ? 'selected' : ''}`} aria-pressed={filter.type === 'tag' && filter.id === item.id} onClick={() => setFilter({ type: 'tag', id: item.id })}><Tag size={14} /><span>{item.name}</span></button>)}
              {!loading && tags.length === 0 && <p className="lib-sidebar-hint">Label topics to find them faster.</p>}
              <details className="lib-create"><summary><Plus size={13} /> New tag</summary><form onSubmit={addTag}><label htmlFor="lib-tag-name">Tag name</label><input id="lib-tag-name" value={tagName} onChange={(event) => setTagName(event.target.value)} placeholder="e.g. To review" maxLength={100} required disabled={creating === 'tag'} /><button type="submit" disabled={!tagName.trim() || creating === 'tag'}>{creating === 'tag' ? 'Creating…' : 'Create tag'}</button></form></details>
            </section>
            <p className="lib-sidebar-note"><BookOpen size={15} /> Assign collections and tags from any saved report.</p>
          </aside>

          <section className="lib-results" aria-labelledby="lib-results-title" aria-busy={loading}>
            <div className="lib-results-title"><h2 id="lib-results-title">{activeName}<span>{loading ? '…' : filtered.length}</span></h2>{filter.type !== 'all' && <button type="button" onClick={() => setFilter({ type: 'all', id: null })}>Clear filter <X size={13} /></button>}</div>
            <div className="lib-tools">
              <div className="lib-search"><Search size={17} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search reports by title…" aria-label="Search saved reports" /></div>
              <label className="lib-sort"><SlidersHorizontal size={15} /><select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort reports"><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="sources">Most sources</option></select></label>
            </div>

            {error && <div className="lib-state lib-error" role="alert"><h3>Unable to load your library</h3><p>{error}</p></div>}
            {loading && <div className="lib-state" role="status">Loading your reports…</div>}
            {!loading && !error && filtered.length > 0 && (
              <div className="lib-report-list">
                <div className="lib-column-head" aria-hidden="true"><span>Report</span><span>Sources</span><span>Last updated</span><span /></div>
                <ul>
                  {filtered.map((item) => (
                    <li key={item.id}><Link className="lib-report-row" to={`/reports/${item.id}`}>
                      <div className="lib-report-main"><span className="lib-document-icon"><FileText size={19} strokeWidth={1.5} /></span><div className="lib-report-info"><h3>{item.topic}</h3><div className="lib-report-meta"><span>Depth {item.depth}</span><span>{item.queries_used?.length || 0} searches</span>{item.tags?.map((tag) => <span className="lib-tag" key={tag.id}>{tag.name}</span>)}</div></div></div>
                      <span className="lib-source-count"><Globe2 size={13} />{item.sources_count || 0}<span className="lib-mobile-label"> sources</span></span>
                      <time className="lib-report-date" dateTime={item.updated_at || undefined}>{formatDate(item.updated_at)}</time>
                      <ArrowRight size={16} className="lib-report-arrow" />
                    </Link></li>
                  ))}
                </ul>
                <div className="lib-list-footer">{filtered.length === history.length ? `${filtered.length} saved report${filtered.length === 1 ? '' : 's'}` : `Showing ${filtered.length} of ${history.length} reports`}<span>Open a report to read, export, or organize it.</span></div>
              </div>
            )}
            {!loading && !error && filtered.length === 0 && <div className="lib-state"><FileText size={29} /><h3>{history.length ? 'No matching reports' : 'Build your research library'}</h3><p>{history.length ? 'Try another title or clear your filters.' : 'Start a research question. Saved reports will appear here.'}</p>{history.length ? <button type="button" className="lib-primary" onClick={() => { setQuery(''); setFilter({ type: 'all', id: null }); }}>Clear search and filters</button> : <Link className="lib-primary" to="/chat"><Plus size={15} /> Start research</Link>}</div>}
          </section>
        </div>
      </div>
    </main>
  );
}
