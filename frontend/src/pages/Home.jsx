import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Globe, FileText, Clock, Library, Activity } from 'lucide-react';
import { toast } from 'sonner';
import SearchBar from '../components/SearchBar';
import { apiFetch } from '../api/client';

const ACTIVE_RESEARCH_KEY = 'activeResearchTask';

export default function Home() {
  const navigate = useNavigate();
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState(null);
  const [loadingHistoryId, setLoadingHistoryId] = useState(null);
  const [activeResearch, setActiveResearch] = useState(null);

  const handleSubmit = ({ topic, depth, forceFresh, visual_planner }) => {
    navigate('/research', { state: { topic, depth, forceFresh, visual_planner } });
  };

  const handleOpenHistory = (itemId) => {
    navigate(`/reports/${itemId}`);
  };

  const handleResumeResearch = async () => {
    if (!activeResearch) return;

    if (activeResearch.taskId) {
      try {
        const response = await apiFetch(`/api/research/task/${activeResearch.taskId}`);
        if (response.ok) {
          const status = await response.json();
          if (status.status === 'SUCCESS' && status.result) {
            localStorage.removeItem(ACTIVE_RESEARCH_KEY);
            navigate('/research', { state: { cachedResult: status.result } });
            return;
          }
          if (status.status === 'FAILURE') {
            localStorage.removeItem(ACTIVE_RESEARCH_KEY);
            setActiveResearch(null);
            setHistoryError(status.error || 'Previous research task failed');
            return;
          }
        }
      } catch {
        // Continue to the research page; it can show the connection error.
      }
    }

    navigate('/research', { state: { resumeTask: activeResearch } });
  };

  const handleDismissActiveResearch = () => {
    localStorage.removeItem(ACTIVE_RESEARCH_KEY);
    setActiveResearch(null);
    toast.info('Task dismissed');
  };

  useEffect(() => {
    const saved = localStorage.getItem(ACTIVE_RESEARCH_KEY);
    if (saved) {
      try {
        setActiveResearch(JSON.parse(saved));
      } catch {
        localStorage.removeItem(ACTIVE_RESEARCH_KEY);
      }
    }

    const loadHistory = async () => {
      try {
        const response = await apiFetch('/api/history');
        if (!response.ok) return;
        const data = await response.json();
        setHistory(data);
      } catch {
        setHistory([]);
      }
    };

    loadHistory();
  }, []);

  const totalSources = history.reduce((sum, item) => sum + item.sources_count, 0);
  const totalQueries = history.reduce((sum, item) => sum + item.queries_used.length, 0);
  const recentReports = history.slice(0, 5);

  return (
    <main className="dashboard-page">
      <section className="dashboard-hero">
        <div>
          <div className="hero-badge">
            <span className="hero-badge-dot" />
            Research workspace
          </div>
          <h1 className="dashboard-title">
            Deep research, organized like a product.
          </h1>
          <p className="dashboard-description">
            Start a research run, resume active work, and manage saved reports from one polished workspace.
          </p>
        </div>
        <div className="dashboard-command">
          <SearchBar onSubmit={handleSubmit} isLoading={false} />
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard icon={FileText} label="Reports" value={history.length} />
        <MetricCard icon={Globe} label="Sources" value={totalSources} />
        <MetricCard icon={Zap} label="Queries" value={totalQueries} />
        <MetricCard icon={Activity} label="Queue" value={activeResearch ? 'Active' : 'Ready'} />
      </section>

      {activeResearch && (
        <section className="active-research-card" aria-label="Active research">
          <div>
            <strong>{activeResearch.taskId ? 'Research still running' : 'Research was interrupted before it fully started'}</strong>
            <p>{activeResearch.topic}</p>
          </div>
          <div className="active-research-actions">
            <button type="button" onClick={handleResumeResearch}>
              Resume
            </button>
            <button type="button" className="secondary" onClick={handleDismissActiveResearch}>
              Dismiss
            </button>
          </div>
        </section>
      )}

      {recentReports.length > 0 && (
        <section className="history-section" aria-labelledby="history-heading">
          <div className="history-header">
            <h2 id="history-heading">
              <Clock size={18} />
              Recent Reports
            </h2>
            <button className="text-link-btn" onClick={() => navigate('/library')}>
              <Library size={15} />
              Open library
            </button>
          </div>

          {historyError && <div className="history-error">{historyError}</div>}

          <div className="history-list">
            {recentReports.map((item) => (
              <button
                key={item.id}
                type="button"
                className="history-item"
                onClick={() => handleOpenHistory(item.id)}
                disabled={loadingHistoryId === item.id}
              >
                <span className="history-topic">{item.topic}</span>
                <span className="history-meta">
                  Depth {item.depth} &middot; {item.sources_count} sources &middot; {item.queries_used.length} queries
                </span>
                <span className="history-open">
                  {loadingHistoryId === item.id ? 'Opening...' : 'Open saved report'}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function MetricCard({ icon, label, value }) {
  const IconComponent = icon;
  return (
    <div className="metric-card">
      <div className="metric-icon">
        <IconComponent size={18} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
