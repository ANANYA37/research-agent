import './Reports.css';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, BarChart3, Globe, Search, RefreshCw, PenTool } from 'lucide-react';
import { toast } from 'sonner';
import ResearchStatus from '../components/ResearchStatus';
import ReportViewer from '../components/ReportViewer';
import SourcesList from '../components/SourcesList';
import { apiFetch } from '../api/client';
import { streamResearch } from '../api/stream';

const ACTIVE_RESEARCH_KEY = 'activeResearchTask';

function saveActiveResearch(payload) {
  localStorage.setItem(ACTIVE_RESEARCH_KEY, JSON.stringify({
    ...payload,
    updatedAt: new Date().toISOString(),
  }));
}

function buildActivePayload({ taskId = null, topic, depth, forceFresh, status = 'starting' }) {
  return {
    taskId,
    topic,
    depth,
    forceFresh,
    status,
    createdAt: new Date().toISOString(),
  };
}

function clearActiveResearch(taskId) {
  const saved = localStorage.getItem(ACTIVE_RESEARCH_KEY);
  if (!saved) return;

  try {
    const parsed = JSON.parse(saved);
    if (!taskId || parsed.taskId === taskId) {
      localStorage.removeItem(ACTIVE_RESEARCH_KEY);
    }
  } catch {
    localStorage.removeItem(ACTIVE_RESEARCH_KEY);
  }
}

export default function Research() {
  const location = useLocation();
  const navigate = useNavigate();
  const abortControllerRef = useRef(null);
  const typingIntervalRef = useRef(null);
  const cachedResult = location.state?.cachedResult;
  const resumeTask = location.state?.resumeTask;
  const topic = cachedResult?.topic || resumeTask?.topic || location.state?.topic;
  const depth = cachedResult?.depth || resumeTask?.depth || location.state?.depth || 3;
  const forceFresh = Boolean(resumeTask?.forceFresh || location.state?.forceFresh);
  const visualPlanner = Boolean(
    resumeTask?.visual_planner ?? location.state?.visual_planner ?? localStorage.getItem('visualPlanner') === 'true'
  );

  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const [progress, setProgress] = useState(0);
  const [report, setReport] = useState(null);
  const [sources, setSources] = useState([]);
  const [queriesUsed, setQueriesUsed] = useState([]);
  const [iterationsCompleted, setIterationsCompleted] = useState(0);
  const [historyId, setHistoryId] = useState(cachedResult?.id || cachedResult?.history_id || null);
  const [error, setError] = useState(null);

  const applyResult = useCallback((data, taskId = null) => {
    setReport(data.report);
    setSources(data.sources || []);
    setQueriesUsed(data.queries_used || []);
    setIterationsCompleted(data.iterations_completed || 0);
    setHistoryId(data.history_id || data.id || null);
    setProgress(1);
    if (taskId) clearActiveResearch(taskId);
  }, []);

  const applyStreamedResult = useCallback((data) => {
    setSources(data.sources || []);
    setQueriesUsed(data.queries_used || []);
    setIterationsCompleted(data.iterations_completed || 0);
    setHistoryId(data.history_id || data.id || null);
    setProgress(1);
    
    // Typewriter effect for the report
    const fullText = data.report || '';
    let currentIndex = 0;
    setReport(''); // Start empty
    
    const chunkSize = Math.max(1, Math.floor(fullText.length / 100)); // Show in ~100 steps
    
    if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
    
    const interval = setInterval(() => {
      currentIndex += chunkSize;
      if (currentIndex >= fullText.length) {
        setReport(fullText);
        clearInterval(interval);
      } else {
        setReport(fullText.substring(0, currentIndex));
      }
    }, 20); // 20ms per chunk

    clearActiveResearch();
    typingIntervalRef.current = interval;
  }, []);

  const pollTask = useCallback(async (taskId, signal) => {
    const MAX_POLLS = 300;
    let pollCount = 0;
    let errorDelay = 2000;

    while (!signal.aborted) {
      if (pollCount >= MAX_POLLS) {
        clearActiveResearch(taskId);
        throw new Error('Research timed out');
      }
      pollCount++;

      await new Promise((resolve) => setTimeout(resolve, errorDelay));
      
      if (signal.aborted) return;
      let statusResponse;
      try {
        statusResponse = await apiFetch(`/api/research/task/${taskId}`, { signal });
        if (!statusResponse.ok) {
          throw new Error('Could not read background task status');
        }
        errorDelay = 2000; // Reset on success
      } catch {
        if (signal.aborted) return;
        errorDelay = Math.min(errorDelay * 2, 30000);
        continue;
      }

      const status = await statusResponse.json();
      if (signal.aborted) return;
      if (status.status === 'SUCCESS' && status.result) {
        applyResult(status.result, taskId);
        setSteps((prev) => [
          ...prev,
          {
            step: 'done',
            detail: 'Research complete',
            progress: 1,
            iteration: status.result.iterations_completed || 0,
          },
        ]);
        toast.success('Research complete!');
        return;
      }

      if (status.status === 'FAILURE') {
        clearActiveResearch(taskId);
        toast.error('Research failed: ' + (status.error || 'Background research failed'));
        throw new Error(status.error || 'Background research failed');
      }

      const meta = status.meta || {};
      setProgress((prev) => Math.max(prev, meta.progress || 0.12));
      setSteps((prev) => {
        const detail = meta.detail || `Background task status: ${status.status}`;
        const next = {
          step: meta.step || 'searching',
          detail,
          progress: meta.progress || 0.12,
          iteration: meta.iteration || 1,
        };
        return prev.length && prev[prev.length - 1].detail === detail ? prev : [...prev, next];
      });
    }
  }, [applyResult]);

  const startResearch = useCallback(async () => {
    if (!topic) return;

    abortControllerRef.current?.abort();
    if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const { signal } = controller;
    setIsLoading(true);
    setSteps([]);
    setProgress(0);
    setReport(null);
    setSources([]);
    setQueriesUsed([]);
    setHistoryId(null);
    setError(null);

    if (cachedResult) {
      clearActiveResearch();
      applyResult(cachedResult);
      setSteps([{
        step: 'done',
        detail: 'Loaded saved research from history',
        progress: 1,
        iteration: cachedResult.iterations_completed || 0,
      }]);
      setIsLoading(false);
      return;
    }

    try {
      toast.info('Starting research...');
      if (resumeTask?.taskId) {
        setSteps([{
          step: 'searching',
          detail: 'Resuming background research...',
          progress: 0.12,
          iteration: 1,
        }]);
        await pollTask(resumeTask.taskId, signal);
        return;
      }

      saveActiveResearch(buildActivePayload({
        topic,
        depth,
        forceFresh,
        status: 'starting',
      }));

      
      await streamResearch({
        topic,
        depth,
        forceFresh,
        visualPlanner,
        signal,
        onStatus: (data) => {
          if (signal.aborted) return;
          setProgress((prev) => Math.max(prev, data.progress || 0.12));
          setSteps((prev) => {
            const next = {
              step: data.step || 'searching',
              detail: data.detail || 'Streaming status update...',
              progress: data.progress || 0.12,
              iteration: data.iteration || 1,
            };
            return prev.length && prev[prev.length - 1].detail === next.detail ? prev : [...prev, next];
          });
        },
        onResult: (data) => {
          if (signal.aborted) return;
          clearActiveResearch();
          if (data.from_cache) {
            applyResult(data);
          } else {
            applyStreamedResult(data);
          }
        },
        onDone: (data) => {
          if (signal.aborted) return;
          setSteps((prev) => {
            const iteration = prev.length ? prev[prev.length - 1].iteration : 0;
            return [
              ...prev,
              {
                step: 'done',
                detail: data.message || 'Research complete',
                progress: 1,
                iteration,
              },
            ];
          });
        },
        onError: (err) => {
          throw new Error(err || 'Streaming error');
        }
      });
    } catch (err) {
      if (signal.aborted) return;
      clearActiveResearch();
      setError(err.message);
      toast.error('Research failed: ' + err.message);
    } finally {
      if (!signal.aborted) setIsLoading(false);
    }
  }, [topic, depth, forceFresh, visualPlanner, cachedResult, resumeTask, applyResult, applyStreamedResult, pollTask]);

  useEffect(() => {
    if (!topic) {
      navigate('/');
      return;
    }
    // StrictMode replays effects. Cancel the scheduled start during cleanup,
    // then let the next setup start a fresh request instead of blocking it.
    const startTimer = setTimeout(() => { void startResearch(); }, 0);
    return () => {
      clearTimeout(startTimer);
      abortControllerRef.current?.abort();
      if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
    };
  }, [topic, startResearch, navigate]);

  if (!topic) return null;

  return (
    <main className="research-studio workspace-page report-workspace"><div className="workspace-inner">
      <button className="back-btn" onClick={() => navigate('/')}>
        <ArrowLeft size={16} />
        New Research
      </button>

      <div className="research-topic">
        {cachedResult ? 'Saved research:' : 'Researching:'} <strong>{topic}</strong>
        {visualPlanner && (
          <span className="research-badge diagram-active-badge">
            <PenTool size={12} />
            Diagrams enabled
          </span>
        )}
      </div>

      {error && (
        <div className="error-banner">
          Warning: {error}
          <button onClick={startResearch}>Retry</button>
        </div>
      )}

      {report && (
        <div className="stats-bar">
          <div className="stat-item">
            <BarChart3 size={16} className="stat-icon" />
            <span className="stat-label">Iterations:</span>
            <span className="stat-value">{iterationsCompleted}</span>
          </div>
          <div className="stat-item">
            <Globe size={16} className="stat-icon" />
            <span className="stat-label">Sources:</span>
            <span className="stat-value">{sources.length}</span>
          </div>
          <div className="stat-item">
            <Search size={16} className="stat-icon" />
            <span className="stat-label">Queries:</span>
            <span className="stat-value">{queriesUsed.length}</span>
          </div>
          <div className="stat-item">
            <RefreshCw size={16} className="stat-icon" />
            <span className="stat-label">Depth:</span>
            <span className="stat-value">{depth}</span>
          </div>
        </div>
      )}

      {steps.length > 0 && (
        <ResearchStatus
          steps={steps}
          progress={progress}
          isComplete={!!report}
          isRunning={isLoading}
          error={error}
        />
      )}

      <ReportViewer report={report} historyId={historyId} />
      <section className="report-evidence" aria-label="Research evidence"><SourcesList sources={sources} queriesUsed={queriesUsed} /></section>
    </div></main>
  );
}
