import { useState } from 'react';
import { readPreferences, savePreferences } from '../preferences';
import { Search, Sparkles, PenTool, SlidersHorizontal } from 'lucide-react';

export default function SearchBar({ onSubmit, isLoading }) {
  const [topic, setTopic] = useState('');
  const [depth, setDepth] = useState(() => readPreferences().depth);
  const [forceFresh, setForceFresh] = useState(() => readPreferences().fresh);
  const [visualPlanner, setVisualPlanner] = useState(
    () => localStorage.getItem('visualPlanner') === 'true'
  );
  const [showOptions, setShowOptions] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (topic.trim() && !isLoading) {
      onSubmit({ topic: topic.trim(), depth, forceFresh, visual_planner: visualPlanner });
    }
  };

  const handleKeyDown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') handleSubmit(event);
  };

  const toggleVisualPlanner = () => {
    const next = !visualPlanner;
    setVisualPlanner(next);
    savePreferences({ diagrams: next });
  };

  const depthLabels = ['', 'Quick', 'Basic', 'Standard', 'Deep', 'Exhaustive'];

  return (
    <div className="search-container">
      <form onSubmit={handleSubmit}>
        <div className="search-box">
          <div className="search-input-row">
            <div className="search-icon">
              <Search size={20} />
            </div>
            <input
              id="research-topic-input"
              type="text"
              className="search-input"
              placeholder="Enter a research topic... e.g., 'Impact of AI on healthcare'"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              autoFocus
            />
            <button
              id="research-submit-btn"
              type="submit"
              className="search-submit-btn"
              disabled={!topic.trim() || isLoading}
            >
              <Sparkles size={16} />
              {isLoading ? 'Researching...' : 'Research'}
            </button>
          </div>
          <div className="search-options">
            <button type="button" className="search-options-trigger" onClick={() => setShowOptions((value) => !value)} aria-expanded={showOptions}>
              <SlidersHorizontal size={14} /> Options
            </button>
            <span className="search-shortcut">Ctrl/Cmd + Enter</span>
          </div>
          <div className="search-extra-options" hidden={!showOptions}>
            <div className="depth-control">
              <span>Depth:</span>
              <input
                id="depth-slider"
                type="range"
                className="depth-slider"
                min={1}
                max={5}
                value={depth}
                onChange={(e) => setDepth(Number(e.target.value))}
                disabled={isLoading}
                aria-label="Depth"
              />
              <span className="depth-value">{depth}</span>
              <span>({depthLabels[depth]})</span>
            </div>
            <div className="search-options-right">
              <button
                type="button"
                className={`visual-planner-toggle ${visualPlanner ? 'active' : ''}`}
                onClick={toggleVisualPlanner}
                title={visualPlanner ? 'Diagrams enabled — click to disable' : 'Click to enable Mermaid diagrams in the report'}
              >
                <PenTool size={14} />
                <span>Diagrams</span>
                <span className={`toggle-dot ${visualPlanner ? 'on' : ''}`} />
              </button>
              <label className="fresh-control">
                <input
                  type="checkbox"
                  checked={forceFresh}
                  onChange={(e) => setForceFresh(e.target.checked)}
                  disabled={isLoading}
                />
                <span>Force fresh research</span>
              </label>
            </div>
          </div>
        </div>
      </form>
      <div className="prompt-suggestions" aria-label="Example research topics">
        {['Compare leading approaches', 'Summarize recent evidence', 'Map risks and tradeoffs'].map((suggestion) => (
          <button key={suggestion} type="button" onClick={() => setTopic(suggestion)}>{suggestion}</button>
        ))}
      </div>
    </div>
  );
}
