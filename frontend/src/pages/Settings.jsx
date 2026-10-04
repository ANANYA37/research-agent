import { useEffect, useState } from 'react';
import { Activity, Brain, Database, ShieldCheck, SlidersHorizontal, Sparkles, BookOpen, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { apiFetch } from '../api/client';
import { usePreferences, savePreferences, preferenceDefaults } from '../preferences';
import './Workspace.css';

export default function Settings() {
  const [runtime, setRuntime] = useState(null);
  const [error, setError] = useState(null);
  const preferences = usePreferences();
  const update = (patch) => {
    try { savePreferences(patch); } catch { toast.error('Could not save preferences. Check browser storage permissions.'); }
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [configResponse, healthResponse, rateResponse] = await Promise.all([
          apiFetch('/api/config'), apiFetch('/api/health'), apiFetch('/api/rate-limit-stats'),
        ]);
        if (!configResponse.ok || !healthResponse.ok) throw new Error('Service details are unavailable. Your local preferences still work.');
        const [config, health, rate] = await Promise.all([configResponse.json(), healthResponse.json(), rateResponse.ok ? rateResponse.json() : null]);
        if (!cancelled) setRuntime({ config, health, rate });
      } catch (err) { if (!cancelled) setError(err.message); }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="research-studio workspace-page">
      <div className="workspace-inner">
        <header className="workspace-heading">
          <div><div className="studio-kicker"><SlidersHorizontal size={14} /> MAKE IT YOURS</div><h1>A workspace that<br /><em>works your way.</em></h1><p>Small adjustments. A better research rhythm.</p></div>
          <span className="workspace-saved"><span className="studio-status-dot" /> Preferences save automatically</span>
        </header>

        <div className="preferences-layout">
          <aside className="preferences-guide">
            <span className="studio-label">YOUR PREFERENCES</span>
            <a href="#research-defaults"><Sparkles size={16} /> Research defaults</a>
            <a href="#workspace-defaults"><BookOpen size={16} /> Your workspace</a>
            <a href="#service-details"><Activity size={16} /> Service details</a>
            <div className="preferences-note"><Sparkles size={19} /><strong>Set it once. Start faster.</strong><p>Defaults apply to new research. You can still adjust depth before each run.</p><span>Saved in this browser, not synced across devices.</span></div>
          </aside>
          <div className="preferences-sections">
            <section id="research-defaults" className="preference-card">
              <div className="preference-card-heading"><span className="workspace-icon"><Sparkles size={19} /></span><div><h2>Research defaults</h2><p>Give every new question a head start.</p></div></div>
              <div className="preference-row"><div><label htmlFor="default-depth">Default research depth</label><p>More depth explores more sources and takes longer.</p></div><select id="default-depth" value={preferences.depth} onChange={(event) => update({ depth: Number(event.target.value) })}>{['Quick scan', 'Focused overview', 'Balanced research', 'In-depth analysis', 'Comprehensive study'].map((name, index) => <option key={name} value={index + 1}>{index + 1} · {name}</option>)}</select></div>
              <Toggle id="fresh-default" title="Always research fresh" description="Skip matching cached reports and run a new search. May take longer and use more API requests." checked={preferences.fresh} onChange={(fresh) => update({ fresh })} />
              <Toggle id="diagram-default" title="Think visually" description="Ask the agent to include diagrams when useful. Saved reports render them as interactive visuals." checked={preferences.diagrams} onChange={(diagrams) => update({ diagrams })} />
            </section>

            <section id="workspace-defaults" className="preference-card">
              <div className="preference-card-heading"><span className="workspace-icon peach"><BookOpen size={19} /></span><div><h2>Your workspace</h2><p>Keep your everyday tools comfortable.</p></div></div>
              <Toggle id="starter-default" title="A little inspiration" description="Show suggested research questions on the Chat start screen." checked={preferences.starters} onChange={(starters) => update({ starters })} />
              <Toggle id="compact-default" title="Compact library" description="Use tighter report rows to see more saved research at once." checked={preferences.compact} onChange={(compact) => update({ compact })} />
              <div className="preference-row"><div><label htmlFor="default-sort">Default library order</label><p>Choose which reports you see first when opening Library.</p></div><select id="default-sort" value={preferences.sort} onChange={(event) => update({ sort: event.target.value })}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="sources">Most sources</option></select></div>
              <div className="preference-preview"><span className="studio-status-dot" /> {preferences.compact ? 'Compact' : 'Comfortable'} rows · {preferences.sort === 'sources' ? 'Most sources' : preferences.sort === 'oldest' ? 'Oldest first' : 'Newest first'}<Link to="/library">See your library <ArrowUpRight size={14} /></Link></div>
            </section>

            <section id="service-details" className="preference-card">
              <div className="preference-card-heading"><span className="workspace-icon lilac"><Activity size={19} /></span><div><h2>Behind the scenes</h2><p>Read-only details from your research service.</p></div></div>
              {error && <p role="alert" className="workspace-error">{error}</p>}
              <div className="runtime-grid">
                <Runtime icon={Brain} label="AI provider" value={runtime?.config.llm_provider} pending={!error} />
                <Runtime icon={Database} label="Semantic cache" value={runtime ? (runtime.config.semantic_cache ? 'Enabled' : 'Disabled') : null} pending={!error} />
                <Runtime icon={Activity} label="Research queue" value={runtime?.config.queue_mode} pending={!error} />
                <Runtime icon={ShieldCheck} label="Service health" value={runtime?.health.status} pending={!error} />
              </div>
              {runtime?.rate && <p className="runtime-footnote">LLM cache hits: {runtime.rate.cache?.hits ?? 0}</p>}
            </section>
            <div className="preferences-footer"><p>Want a fresh start? Restore only these preferences.</p><button type="button" onClick={() => update(preferenceDefaults)}>Restore defaults</button></div>
          </div>
        </div>
      </div>
    </main>
  );
}
function Toggle({ id, title, description, checked, onChange }) {
  return <div className="preference-row"><div><label htmlFor={id}>{title}</label><p id={id + '-description'}>{description}</p></div><input className="preference-switch" id={id} type="checkbox" role="switch" checked={checked} aria-describedby={id + '-description'} onChange={(event) => onChange(event.target.checked)} /></div>;
}
function Runtime({ icon, label, value, pending }) {
  const IconComponent = icon;
  return <div className="runtime-item"><IconComponent size={16} /><span>{label}</span><strong>{value || (pending ? 'Loading…' : 'Unavailable')}</strong></div>;
}
