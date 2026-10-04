import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScanSearch, ArrowUpRight, LoaderCircle, ExternalLink, Search, ChevronDown } from 'lucide-react';
import { apiFetch } from '../api/client';
import './EvidenceExplorer.css';

const labels = { supported: 'Supported', mixed: 'Mixed / conflicting', insufficient: 'Insufficient evidence' };

export default function EvidenceExplorer({ historyId, topic, depth }) {
  const navigate = useNavigate();
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);

  const analyze = async () => {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 115000);
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`/api/history/${historyId}/evidence`, { method: 'POST', signal: controller.signal });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (response.status === 429) throw new Error('Review limit reached. Please wait before trying again.');
        if (response.status === 404 && data.detail === 'Not Found') throw new Error('The evidence endpoint is unavailable. Restart the backend to load the latest update.');
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not review the evidence. Please try again.');
      }
      const data = await response.json();
      if (!controller.signal.aborted) { setReview(data); setFilter('all'); }
    } catch (err) {
      if (timedOut) setError('Evidence review timed out. Please try again.');
      else if (!controller.signal.aborted) setError(err.message);
    } finally {
      clearTimeout(timeout);
      if (!controller.signal.aborted || timedOut) { setLoading(false); request.current = null; }
    }
  };
  const researchClaim = (claim) => navigate('/research', { state: {
    topic: `Investigate this claim from research on "${topic}": ${claim}. Find primary sources that support or challenge it. Explain differences in dates, populations, and assumptions, and identify remaining evidence gaps.`,
    depth: Math.max(3, depth || 3), forceFresh: true,
  } });
  const claims = review?.claims || [];
  const visible = claims.filter((claim) => filter === 'all' || claim.status === filter);

  return (
    <section id="evidence-explorer" className="evidence-explorer" aria-labelledby="evidence-heading">
      <header className="evidence-heading">
        <span className="evidence-symbol"><ScanSearch size={21} /></span>
        <div><span className="evidence-eyebrow">BEFORE YOU TRUST THE CONCLUSION</span><h2 id="evidence-heading">Evidence Explorer <span>AI review</span></h2><p>See what supports each claim, where sources disagree, and what is still missing.</p></div>
        <button type="button" className="report-action-btn evidence-analyze" disabled={loading} onClick={analyze}>{loading ? <LoaderCircle size={14} className="evidence-spinner" /> : <ScanSearch size={14} />}{loading ? 'Reviewing…' : review ? 'Review again' : 'Analyze claims'}</button>
      </header>
      <p className="evidence-scope">Reviews saved source snippets, not full articles or the live web. Excerpts are checked against saved text; their relationship to a claim is an AI interpretation.</p>
      {error && <p className="evidence-error" role="alert">{error}</p>}
      {loading && <p className="evidence-loading" role="status">Extracting key claims and comparing saved excerpts. This may take a minute.</p>}
      {!review && !loading && <div className="evidence-intro"><span>01 <strong>Extract claims</strong></span><span>02 <strong>Compare excerpts</strong></span><span>03 <strong>Find evidence gaps</strong></span></div>}
      {review && <>
        <p className="evidence-coverage">{claims.length} claims · {review.reviewed_sources} source snippets reviewed{review.truncated ? ' · Review shortened to fit the model input budget.' : ''}</p>
        {claims.length === 0 ? <p className="evidence-empty">This report has no usable saved source snippets. Run fresh research to collect evidence for review.</p> : <>
          <div className="evidence-filters" role="group" aria-label="Filter claim assessments">
            {['all', ...Object.keys(labels)].map((value) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value === 'all' ? 'All claims' : labels[value]} <span>{value === 'all' ? claims.length : claims.filter((claim) => claim.status === value).length}</span></button>)}
          </div>
          <div className="evidence-claims">{visible.map((claim) => (
            <details key={claim.id} className="evidence-claim">
              <summary><span className={`evidence-label ${claim.status}`}>{labels[claim.status]}</span><span className="evidence-claim-text">{claim.claim}</span><ChevronDown size={16} /></summary>
              <div className="evidence-claim-body">
                {claim.explanation && <p className="evidence-reason"><strong>AI assessment</strong>{claim.explanation}</p>}
                {['supports', 'contradicts'].map((relation) => {
                  const entries = claim.evidence.filter((entry) => entry.relation === relation);
                  return entries.length > 0 && <section className="evidence-excerpts" key={relation}><h3>{relation === 'supports' ? 'Supporting excerpts' : 'Conflicting excerpts'}</h3>{entries.map((entry, index) => <figure key={index}><blockquote>{entry.quote}</blockquote><figcaption><span>Source {entry.source_id} · {entry.title}</span>{entry.url && <a href={entry.url} target="_blank" rel="noopener noreferrer">Open source <ExternalLink size={12} /></a>}</figcaption></figure>)}</section>;
                })}
                {claim.gaps.length > 0 && <div className="evidence-gaps"><h3>What is still missing</h3><ul>{claim.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></div>}
                <button type="button" className="report-action-btn" onClick={() => researchClaim(claim.claim)}><Search size={14} />Research this claim<ArrowUpRight size={14} /></button>
              </div>
            </details>
          ))}</div>
          {visible.length === 0 && <p className="evidence-empty">No claims in this category.</p>}
        </>}
      </>}
    </section>
  );
}
