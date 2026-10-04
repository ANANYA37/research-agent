import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, RefreshCw, BookOpen, Tags, Globe2, Search, Layers3, Clock } from 'lucide-react';
import { toast } from 'sonner';
import ReportViewer from '../components/ReportViewer';
import SourcesList from '../components/SourcesList';
import WatchTopic from '../components/WatchTopic';
import EvidenceExplorer from '../components/EvidenceExplorer';
import { api, apiFetch } from '../api/client';
import './Reports.css';

export default function ReportDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [collections, setCollections] = useState([]);
  const [tags, setTags] = useState([]);
  const [selectedCollections, setSelectedCollections] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);

  useEffect(() => {
    let cancelled = false;
    const loadReport = async () => {
      setLoading(true);
      setError(null);
      try {
        const [response, collectionItems, tagItems] = await Promise.all([
          apiFetch(`/api/history/${id}`), api.collections(), api.tags(),
        ]);
        if (!response.ok) throw new Error('Could not open report. Please return to Library and try again.');
        const item = await response.json();
        if (cancelled) return;
        setReport(item);
        setCollections(collectionItems);
        setTags(tagItems);
        setSelectedCollections(item.collections?.map((value) => value.id) || []);
        setSelectedTags(item.tags?.map((value) => value.id) || []);
      } catch (err) {
        if (!cancelled) { setError(err.message); setReport(null); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadReport();
    return () => { cancelled = true; };
  }, [id]);

  const regenerate = () => {
    if (!report) return;
    navigate('/research', { state: { topic: report.topic, depth: report.depth, forceFresh: true } });
  };
  const toggle = (setter, values, value) => setter(values.includes(value) ? values.filter((itemId) => itemId !== value) : [...values, value]);
  const saveMetadata = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const item = await api.updateReportMetadata(id, { collection_ids: selectedCollections, tag_ids: selectedTags });
      setReport(item);
      toast.success('Report organization saved');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const sources = report?.sources || [];
  const queries = report?.queries_used || [];
  const readingMinutes = Math.max(1, Math.ceil((report?.report?.trim().split(/\s+/).length || 0) / 220));

  return (
    <main className="research-studio workspace-page report-workspace">
      <div className="workspace-inner">
        <nav className="report-breadcrumb" aria-label="Breadcrumb"><Link to="/library"><ArrowLeft size={15} /> Library</Link><span>/</span><span>Saved report</span></nav>
        {loading && <div className="report-state" role="status"><BookOpen size={27} /><h1>Opening your research…</h1><p>Gathering the report and its sources.</p></div>}
        {error && <div className="report-state" role="alert"><BookOpen size={27} /><h1>We couldn’t open this report.</h1><p>{error}</p><Link className="workspace-action" to="/library">Back to Library</Link></div>}
        {!loading && report && (
          <>
            <header className="workspace-heading report-cover">
              <div><div className="studio-kicker"><BookOpen size={14} /> SAVED RESEARCH</div><h1>{report.topic}</h1><p>Saved research{report.updated_at && <> · Updated {new Date(report.updated_at).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}</>}</p></div>
              <button type="button" className="workspace-action" onClick={regenerate}><RefreshCw size={15} /> Research again</button>
            </header>
            <div className="report-facts" aria-label="Report overview">
              <span><Globe2 size={15} /><strong>{sources.length}</strong> sources</span>
              <span><Search size={15} /><strong>{queries.length}</strong> searches</span>
              <span><Layers3 size={15} />Depth <strong>{report.depth}</strong></span>
              <span><Clock size={15} />About {readingMinutes} min read</span>
            </div>
            <WatchTopic key={id} reportId={id} />
            <EvidenceExplorer key={id + (report.updated_at || '')} historyId={id} topic={report.topic} depth={report.depth} />
            <ReportViewer report={report.report} historyId={report.id || report.history_id || id} />
            <section className="report-evidence" aria-label="Research evidence">
              <SourcesList sources={sources} queriesUsed={queries} />
              {sources.length === 0 && <p className="report-no-sources">No source links were saved with this report.</p>}
            </section>
            <section className="report-organization" aria-labelledby="organization-heading">
              <div className="report-organization-heading"><span className="workspace-icon peach"><Tags size={19} /></span><div><h2 id="organization-heading">Organize report</h2><p>Add this report to your collections and tags.</p></div><Link to="/library">Manage in Library</Link></div>
              {(collections.length > 0 || tags.length > 0) ? (
                <>
                  {collections.length > 0 && <fieldset><legend>Collections</legend><div className="report-choices">{collections.map((item) => <label key={item.id}><input type="checkbox" disabled={saving} checked={selectedCollections.includes(item.id)} onChange={() => toggle(setSelectedCollections, selectedCollections, item.id)} />{item.name}</label>)}</div></fieldset>}
                  {tags.length > 0 && <fieldset><legend>Tags</legend><div className="report-choices">{tags.map((item) => <label key={item.id}><input type="checkbox" disabled={saving} checked={selectedTags.includes(item.id)} onChange={() => toggle(setSelectedTags, selectedTags, item.id)} /><span className="tag-dot" style={{ background: item.color }} />{item.name}</label>)}</div></fieldset>}
                  <button type="button" className="report-action-btn" onClick={saveMetadata} disabled={saving}>{saving ? 'Saving…' : 'Save organization'}</button>
                </>
              ) : <p className="report-organization-empty">Create your first collection or tag in Library, then return here to organize this report.</p>}
            </section>
            <p className="studio-footnote"><BookOpen size={13} /> Explore widely. Check the sources. Make it your own.</p>
          </>
        )}
      </div>
    </main>
  );
}
