import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, ArrowLeft, RefreshCw, Pause, Play, Trash2, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import ReportViewer from '../components/ReportViewer';
import './Reports.css';
import '../components/Watchlists.css';

const date = (value) => value ? new Date(value * 1000).toLocaleString() : 'Not checked yet';
const safeUrl = (url) => { try { return ['https:', 'http:'].includes(new URL(url).protocol) ? url : null; } catch { return null; } };

export default function Watchlists() {
  const { id } = useParams();
  return id ? <WatchDetail key={id} id={id} /> : <WatchIndex />;
}
function WatchIndex() {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['watchlists', user.id], queryFn: api.watchlists, refetchInterval: 15000 });
  return <main className="research-studio workspace-page"><div className="workspace-inner">
    <header className="watch-heading"><div><span className="studio-kicker"><Bell size={15} /> STAY INFORMED</span><h1>Research watchlists</h1><p>Follow a topic. See how the report and its sources change.</p></div><Link className="workspace-action" to="/library">Watch a saved report</Link></header>
    <p className="watch-service-note">Weekly and 30-day schedules run while the API service is online. Overdue checks resume after restart. Each check uses fresh research and may consume API credits.</p>
    {query.isPending && <p role="status">Loading watchlists…</p>}
    {query.error && <p role="alert">{query.error.message} <button onClick={() => query.refetch()}>Retry</button></p>}
    <div className="watch-grid">{query.data?.map((watch) => <Link className="watch-card" to={`/watchlists/${watch.id}`} key={watch.id}><div><Bell size={18} /><span className="watch-badge">{watch.active_run_id ? 'Checking…' : watch.paused ? 'Paused' : watch.unread ? 'Update to review' : 'Watching'}</span></div><h2>{watch.topic}</h2><p>{watch.frequency === 'monthly' ? 'Every 30 days' : 'Weekly'} · Depth {watch.depth}</p><dl><dt>Last check</dt><dd>{date(watch.last_check)}</dd><dt>Next scheduled</dt><dd>{watch.paused ? 'Paused' : date(watch.next_check)}</dd></dl><span className="watch-open">View changes →</span></Link>)}</div>
    {query.data?.length === 0 && <div className="watch-empty"><Bell size={30} /><h2>Keep an eye on what matters.</h2><p>Open a saved report and select “Watch this topic” to start.</p><Link to="/library" className="workspace-action">Open Library</Link></div>}
  </div></main>;
}
function WatchDetail({ id }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const query = useQuery({ queryKey: ['watchlist', user.id, id], queryFn: () => api.watchlist(id), refetchInterval: 5000 });
  const version = useQuery({ queryKey: ['watch-snapshot', user.id, id, snapshot], queryFn: () => api.watchlistRun(id, snapshot), enabled: !!snapshot });
  const watch = query.data;
  const action = async (operation, remove = false) => {
    if (busy) return;
    setBusy(true);
    try {
      await operation();
      if (remove) {
        await client.cancelQueries({ queryKey: ['watchlists', user.id] });
        client.setQueryData(['watchlists', user.id], (items = []) => items.filter((item) => item.id !== id));
        navigate('/watchlists');
        client.removeQueries({ queryKey: ['watchlist', user.id, id] });
        client.removeQueries({ queryKey: ['watch-snapshot', user.id, id] });
      } else await client.invalidateQueries({ queryKey: ['watchlist', user.id, id] });
      await client.invalidateQueries({ queryKey: ['watchlists', user.id] });
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return <main className="research-studio workspace-page report-workspace"><div className="workspace-inner">
    <Link className="report-breadcrumb" to="/watchlists"><ArrowLeft size={15} /> Watchlists</Link>
    {query.isPending && <p role="status">Loading watchlist…</p>}
    {query.error && <p role="alert">{query.error.message} <button onClick={() => query.refetch()}>Retry</button></p>}
    {watch && <>
      <header className="watch-heading"><div><span className="studio-kicker">TOPIC WATCHLIST</span><h1>{watch.topic}</h1><p>Baseline and every completed version are kept separately.</p></div><button className="workspace-action" disabled={busy || !!watch.active_run_id || !!watch.paused} onClick={() => action(() => api.checkWatchlist(id))}><RefreshCw size={15} />{watch.active_run_id ? 'Checking…' : 'Check now'}</button></header>
      <div className="watch-controls"><label>Frequency <select disabled={busy} value={watch.frequency} onChange={(event) => action(() => api.updateWatchlist(id, { frequency: event.target.value }))}><option value="weekly">Weekly</option><option value="monthly">Every 30 days</option></select></label><button disabled={busy} onClick={() => action(() => api.updateWatchlist(id, { paused: !watch.paused }))}>{watch.paused ? <Play size={14} /> : <Pause size={14} />}{watch.paused ? 'Resume' : 'Pause'}</button>{!!watch.unread && <button disabled={busy} onClick={() => action(() => api.updateWatchlist(id, { mark_read: true }))}>Mark reviewed</button>}<button disabled={busy || !!watch.active_run_id} onClick={() => setConfirmDelete((value) => !value)}><Trash2 size={14} />Remove</button></div>
      {confirmDelete && <div className="watch-delete"><p>Remove this watchlist and its snapshots? Your original Library report will remain.</p><button disabled={busy} onClick={() => action(() => api.deleteWatchlist(id), true)}>Remove watchlist</button><button onClick={() => setConfirmDelete(false)}>Cancel</button></div>}
      <p className="watch-service-note">{watch.paused ? 'Scheduled checks are paused.' : `Next scheduled: ${date(watch.next_check)}.`} Last check: {date(watch.last_check)}. The service must be online to run checks.</p>
      <h2 className="watch-section-title">Check history & changes</h2>
      <p className="watch-service-note">This is a text and source-link comparison. Rewording does not necessarily mean a conclusion changed. Review the sources before drawing conclusions.</p>
      <div className="watch-runs">{watch.runs.map((run) => <article key={run.id} className="watch-run">
        <div className="watch-run-heading"><strong>{run.status === 'baseline' ? 'Original baseline' : run.status === 'running' ? 'Research in progress' : run.status === 'failed' ? 'Check failed' : run.changes.changed ? 'Changes found' : 'No text or source changes'}</strong><time>{date(run.created_at)}</time></div>
        {run.status === 'failed' && <p role="status">{run.error}</p>}
        {run.status === 'running' && <p role="status">Searching and preparing a new snapshot. This page updates automatically.</p>}
        {run.status === 'success' && <><p>{run.changes.added_sources.length} new source links · {run.changes.removed_sources.length} removed · {run.changes.text_changes.length} text changes</p>
          {run.changes.changed && <details><summary>What changed?</summary>
            <SourceChanges label="Added sources" sources={run.changes.added_sources} /><SourceChanges label="Removed sources" sources={run.changes.removed_sources} />
            {run.changes.text_changes.map((change, index) => <div className="watch-diff" key={index}>{change.before && <section><h4>Previous version</h4><p>{change.before}</p></section>}{change.after && <section><h4>New version</h4><p>{change.after}</p></section>}</div>)}
          </details>}
        </>}
        {['baseline', 'success'].includes(run.status) && <button className="report-action-btn" onClick={() => setSnapshot(run.id)}>{snapshot === run.id ? 'Viewing this snapshot' : 'Read snapshot'}</button>}
      </article>)}</div>
      {snapshot && <section className="watch-snapshot"><div className="watch-run-heading"><h2>Saved snapshot</h2><button onClick={() => setSnapshot(null)}>Close snapshot</button></div>{version.isPending && <p role="status">Loading snapshot…</p>}{version.error && <p role="alert">{version.error.message}</p>}{version.data && <><p className="watch-service-note">Captured {date(version.data.created_at)}. Markdown download is available; PDF and Word exports remain available on Library reports.</p><ReportViewer report={version.data.result.report} /><SourceChanges label="Snapshot sources" sources={version.data.result.sources || []} /></>}</section>}
    </>}
  </div></main>;
}
function SourceChanges({ label, sources }) {
  if (!sources.length) return null;
  return <section className="watch-source-changes"><h3>{label}</h3><ul>{sources.map((source, index) => <li key={index}>{safeUrl(source.url) ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title || source.url}<ExternalLink size={12} /></a> : <span>{source.title || 'Source link unavailable'}</span>}</li>)}</ul></section>;
}
