import { createElement, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ArrowUp, Bot, BookOpen, Compass, Globe2, Layers3, LoaderCircle, Plus, Search, SlidersHorizontal, Sparkles, User, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { streamResearch } from '../api/stream';
import './Chat.css';
import { readPreferences, usePreferences } from '../preferences';

const starterGroups = [
  {
    icon: Globe2, category: 'Explore a topic', tone: 'mint',
    ideas: [
      { title: 'The next chapter in clean energy', prompt: 'Explore promising developments in clean energy. Compare the evidence, practical applications, costs, and remaining challenges.' },
      { title: 'How cities can stay cool', prompt: 'Research how cities can reduce extreme heat. Compare trees, cool roofs, and urban design using evidence from real projects.' },
      { title: 'What makes learning stick?', prompt: 'Compare the evidence for spaced repetition, retrieval practice, and rereading. Explain when each approach helps and the limitations of the research.' },
      { title: 'A closer look at ocean restoration', prompt: 'Explore approaches to restoring marine ecosystems. Compare evidence for coral restoration, seagrass protection, and marine reserves.' },
      { title: 'Where robotics meets everyday life', prompt: 'Research practical uses of robotics outside factories. Compare adoption barriers, demonstrated benefits, and unresolved safety questions.' },
    ],
  },
  {
    icon: Layers3, category: 'Compare options', tone: 'peach',
    ideas: [
      { title: 'PostgreSQL or MongoDB?', prompt: 'Compare PostgreSQL and MongoDB for a new SaaS product. Explain data modeling, scaling, and maintenance tradeoffs with sources.' },
      { title: 'Build, buy, or use open source?', prompt: 'Compare building custom software, buying a SaaS product, and adopting open source for a small business. Analyze total cost, control, and maintenance.' },
      { title: 'Batteries or pumped hydro?', prompt: 'Compare battery storage and pumped hydro for electricity grids. Examine costs, geography, duration, and environmental tradeoffs with sources.' },
      { title: 'Remote, hybrid, or office-first?', prompt: 'Compare evidence on remote, hybrid, and office-first work. Separate findings on productivity, collaboration, retention, and employee preferences.' },
      { title: 'A monolith or microservices?', prompt: 'Compare a modular monolith and microservices for a small engineering team. Analyze deployment complexity, reliability, and the conditions that justify migration.' },
    ],
  },
  {
    icon: Compass, category: 'Challenge an assumption', tone: 'lilac',
    ideas: [
      { title: 'Is open-source AI always cheaper?', prompt: 'Investigate whether open-source AI is cheaper than hosted models. Compare infrastructure, staffing, performance, and usage assumptions with evidence.' },
      { title: 'Does more data mean better AI?', prompt: 'Evaluate the claim that more training data always improves AI. Look for evidence about data quality, duplication, model size, and diminishing returns.' },
      { title: 'Do four-day weeks improve output?', prompt: 'Investigate evidence for and against four-day workweeks. Compare study methods, industry differences, selection bias, and long-term results.' },
      { title: 'Are electric cars always cleaner?', prompt: 'Examine lifecycle emissions of electric and combustion cars. Explain how electricity mix, manufacturing, mileage, and battery size change the comparison.' },
      { title: 'Can recycling solve plastic waste?', prompt: 'Assess the claim that recycling alone can solve plastic waste. Compare collection rates, material losses, reuse, and reduction strategies with sources.' },
    ],
  },
];

const depthNames = ['Quick scan', 'Focused overview', 'Balanced research', 'In-depth analysis', 'Comprehensive study'];

export default function Chat() {
  const queryClient = useQueryClient();
  const preferences = usePreferences();
  const [topic, setTopic] = useState('');
  const [ideaRound, setIdeaRound] = useState(() => Math.floor(Math.random() * 5));
  const [ideasRefreshed, setIdeasRefreshed] = useState(false);
  const starters = starterGroups.map(({ ideas, ...group }) => ({
    ...group, ...ideas[ideaRound % ideas.length],
  }));
  const refreshIdeas = () => {
    setIdeaRound((round) => round + 1);
    setIdeasRefreshed(true);
  };
  const [depth, setDepth] = useState(() => readPreferences().depth);
  const [messages, setMessages] = useState([]);
  const [running, setRunning] = useState(false);
  const inputRef = useRef(null);
  const empty = messages.length === 0;

  const submit = async (event) => {
    event.preventDefault();
    const prompt = topic.trim();
    if (!prompt || running) return;
    setTopic('');
    setRunning(true);
    setMessages((current) => [...current, { role: 'user', content: prompt }, { role: 'assistant', content: '', status: 'Planning research...' }]);
    await streamResearch({
      topic: prompt,
      depth,
      forceFresh: preferences.fresh,
      visualPlanner: preferences.diagrams,
      onStatus: (data) => setMessages((current) => current.map((message, index) => index === current.length - 1 ? { ...message, status: data.detail } : message)),
      onResult: (data) => {
        setMessages((current) => current.map((message, index) => index === current.length - 1 ? { ...message, content: data.report, status: data.from_cache ? 'Loaded from your library' : 'Research complete', historyId: data.history_id } : message));
        queryClient.invalidateQueries({ queryKey: ['history'] });
      },
      onError: (error) => setMessages((current) => current.map((message, index) => index === current.length - 1 ? { ...message, content: `Research failed: ${error}`, status: 'Unable to complete research' } : message)),
    });
    setRunning(false);
    inputRef.current?.focus();
  };

  const newResearch = () => {
    if (running) return;
    setMessages([]);
    setDepth(readPreferences().depth);
    setTopic('');
    inputRef.current?.focus();
  };

  return (
    <main className="research-studio">
      <aside className="studio-sidebar" aria-label="Research controls">
        <div className="studio-workspace"><span className="studio-workspace-icon"><Compass size={19} /></span><div><strong>Your workspace</strong><span>A little curiosity goes a long way.</span></div></div>
        <button className="studio-new" onClick={newResearch} disabled={running}><Plus size={17} /> New research <span>↗</span></button>
        <Link className="studio-library" to="/library"><BookOpen size={17} /> Saved reports <ArrowUpRight size={15} /></Link>

        <section className="studio-depth" aria-labelledby="depth-heading">
          <h2 id="depth-heading"><SlidersHorizontal size={14} /> Research depth</h2>
          <div className="studio-depth-options" role="group" aria-label="Research depth">
            {depthNames.map((name, index) => <button key={name} type="button" aria-pressed={depth === index + 1} aria-label={`Level ${index + 1}: ${name}`} title={name} disabled={running} onClick={() => setDepth(index + 1)}>{index + 1}</button>)}
          </div>
          <strong>{depthNames[depth - 1]}</strong>
          <p>Higher depth explores more sources and takes longer.</p>
        </section>

        <div className="studio-process">
          <span className="studio-label">FROM QUESTION TO CLARITY</span>
          <ol><li><Search size={15} /><span>Search the web</span></li><li><Layers3 size={15} /><span>Connect the evidence</span></li><li><BookOpen size={15} /><span>Build a sourced report</span></li></ol>
        </div>
        <div className="studio-tip"><Sparkles size={17} /><strong>Better questions. Better research.</strong><p>Add a goal, a time frame, or a comparison to focus your results.</p></div>
      </aside>

      <div className={`studio-main ${empty ? 'is-empty' : 'has-messages'}`}>
        <div className="studio-topline"><span><span className="studio-status-dot" /> Research studio</span><span>Built for curious minds</span></div>
        {empty ? (
          <section className="studio-intro" aria-labelledby="studio-heading">
            <div className="studio-kicker"><Sparkles size={14} /> A SPACE FOR YOUR NEXT BIG IDEA</div>
            <h1 id="studio-heading">Big questions.<br /><em>Clearer answers.</em></h1>
            <p>Follow your curiosity. Turn a question into<br className="studio-desktop-break" /> a thoughtful report, backed by sources.</p>
          </section>
        ) : (
          <section className="studio-thread" aria-label="Research conversation" aria-live="polite" aria-busy={running}>
            {messages.map((message, index) => (
              <article key={index} className={`studio-message ${message.role}`}>
                <div className="studio-avatar">{message.role === 'user' ? <User size={17} /> : <Bot size={17} />}</div>
                <div className="studio-bubble">
                  <span className="studio-message-label">{message.role === 'user' ? 'Your question' : 'ResearchAgent'}</span>
                  {message.content ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown> : <span className="studio-progress"><LoaderCircle size={16} className={running ? 'studio-spinner' : ''} />{message.status}</span>}
                  {message.content && message.status && <div className="studio-result-status">{message.status}{message.historyId && <Link to={`/reports/${message.historyId}`}>Open report <ArrowUpRight size={13} /></Link>}</div>}
                </div>
              </article>
            ))}
          </section>
        )}

        <form className="studio-composer" onSubmit={submit}>
          <label htmlFor="research-question" className="studio-input-label">Your next discovery starts here</label>
          <textarea id="research-question" ref={inputRef} value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="What would you like to understand?" rows={3} readOnly={running} aria-describedby="studio-keyboard-hint" onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) {
              event.preventDefault();
              event.currentTarget.form.requestSubmit();
            }
          }} />
          <div className="studio-composer-bottom">
            <span className="studio-source-pill"><Globe2 size={14} /> Web research</span>
            <span className="studio-keyboard-hint" id="studio-keyboard-hint">Ctrl / ⌘ + Enter</span>
            <button type="submit" disabled={running || !topic.trim()}>{running ? <><LoaderCircle size={16} className="studio-spinner" /> Researching</> : <>Start research <ArrowUp size={16} /></>}</button>
          </div>
        </form>

        {empty && preferences.starters && (
          <section className="studio-starters" aria-labelledby="starters-heading">
            <div className="studio-starters-heading"><h2 id="starters-heading">A spark to get you started</h2><button type="button" className="studio-refresh-ideas" onClick={refreshIdeas} aria-controls="research-starter-ideas"><RefreshCw size={13} />Refresh ideas</button></div>
            <span className="studio-ideas-status" role="status">{ideasRefreshed ? `Three new research ideas shown. ${starters.map((idea) => idea.title).join('; ')}` : ''}</span>
            <div id="research-starter-ideas" className="studio-starter-grid">{starters.map(({ icon, category, title, prompt, tone }) => (
              <button type="button" className={`studio-starter ${tone}`} key={category} onClick={() => { setTopic(prompt); inputRef.current?.focus(); }}>
                <span className="studio-starter-top"><span className="studio-starter-icon">{createElement(icon, { size: 19 })}</span><ArrowUpRight size={17} /></span>
                <span className="studio-starter-category">{category}</span><strong>{title}</strong>
              </button>
            ))}</div>
          </section>
        )}
        <p className="studio-footnote"><BookOpen size={13} /> Explore widely. Check the sources. Make it your own.</p>
      </div>
    </main>
  );
}
