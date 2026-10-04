import { Compass, Search, BookOpen, BrainCircuit, PenTool, CheckCircle2, ChevronDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

const stepConfig = {
  planning: { icon: Compass, label: 'Planning Searches', className: 'planning' },
  searching: { icon: Search, label: 'Searching the Web', className: 'searching' },
  reading: { icon: BookOpen, label: 'Reading Pages', className: 'reading' },
  analyzing: { icon: BrainCircuit, label: 'Analyzing Findings', className: 'analyzing' },
  writing: { icon: PenTool, label: 'Writing Report', className: 'writing' },
  done: { icon: CheckCircle2, label: 'Complete', className: 'done' },
};

export default function ResearchStatus({ steps, progress, isComplete, isRunning = !isComplete, error }) {
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);
  const [showLog, setShowLog] = useState(false);
  useEffect(() => {
    if (isComplete || !isRunning) return undefined;
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [isComplete, isRunning, startedAt]);
  const stages = useMemo(() => [...new Set(steps.map((step) => step.step))], [steps]);
  const latest = steps[steps.length - 1];
  const formatElapsed = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;

  return (
    <div className="status-container">
      <div className="status-header">
        {isRunning && !isComplete && <div className="status-spinner" />}
        <h2>{error ? 'Research stopped' : isComplete ? 'Research complete' : isRunning ? 'Researching' : 'Research stopped'}</h2>
        <span className="status-elapsed">{formatElapsed}</span>
      </div>

      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${Math.max(progress * 100, 2)}%` }}
        />
      </div>

      {latest && <div className="status-step active">
        <div className={`step-icon ${(stepConfig[latest.step] || stepConfig.planning).className}`}>
          {(() => { const Icon = (stepConfig[latest.step] || stepConfig.planning).icon; return <Icon size={16} />; })()}
        </div>
        <div className="step-content">
          <div className="step-title">{(stepConfig[latest.step] || stepConfig.planning).label}</div>
          <div className="step-detail">{latest.detail}</div>
        </div>
      </div>}
      <div className="status-timeline" aria-label="Completed research stages">
        {stages.map((stage) => {
          const config = stepConfig[stage] || stepConfig.planning;
          const Icon = config.icon;
          return <span key={stage} className={stage === latest?.step && !isComplete ? 'current' : ''}><Icon size={14} />{config.label}</span>;
        })}
      </div>
      <button className="status-log-toggle" type="button" onClick={() => setShowLog((value) => !value)} aria-expanded={showLog}>
        <ChevronDown size={14} /> {showLog ? 'Hide activity' : `Show activity (${steps.length})`}
      </button>
      {showLog && <div className="status-steps">
        {steps.map((step, index) => {
          const config = stepConfig[step.step] || stepConfig.planning;
          const Icon = config.icon;
          const isLast = index === steps.length - 1;

          return (
            <div
              key={index}
              className={`status-step${isLast && !isComplete ? ' active' : ''}`}
            >
              <div className={`step-icon ${config.className}`}>
                <Icon size={16} />
              </div>
              <div className="step-content">
                <div className="step-title">
                  {step.iteration > 0 && `[Iteration ${step.iteration}] `}
                  {config.label}
                </div>
                <div className="step-detail">{step.detail}</div>
              </div>
            </div>
          );
        })}
      </div>}
    </div>
  );
}
