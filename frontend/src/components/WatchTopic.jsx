import { useState } from 'react';
import { Link } from 'react-router-dom';
import { BellPlus } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './Watchlists.css';

export default function WatchTopic({ reportId }) {
  const [frequency, setFrequency] = useState('weekly');
  const { user } = useAuth();
  const client = useQueryClient();
  const queryKey = ['watchlists', user.id];
  const watches = useQuery({ queryKey, queryFn: api.watchlists });
  const watchId = watches.data?.find((watch) => watch.report_id === reportId)?.id;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const create = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await api.createWatchlist({ report_id: reportId, frequency });
      await client.cancelQueries({ queryKey });
      client.setQueryData(queryKey, (items = []) => [result, ...items.filter((item) => item.id !== result.id)]);
      await client.invalidateQueries({ queryKey });
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  return <details className="watch-topic"><summary><BellPlus size={16} />Watch this topic</summary><div className="watch-topic-panel">
    {watches.isPending ? <p role="status">Checking watchlist status...</p> : watchId ? <><strong>This topic is in your watchlists</strong><Link to={`/watchlists/${watchId}`}>Open watchlist →</Link></> :
      <form onSubmit={create}><strong>Keep up with this topic</strong><p>Your current report becomes the baseline. Each check saves a separate version.</p><label>Check frequency<select value={frequency} onChange={(event) => setFrequency(event.target.value)} disabled={busy}><option value="weekly">Weekly</option><option value="monthly">Every 30 days</option></select></label><p>Checks run while the research service is online and may use your configured AI and search API credits.</p>{error && <p role="alert">{error}</p>}<button type="submit" className="workspace-action" disabled={busy}>{busy ? 'Adding…' : 'Start watching'}</button></form>}
  </div></details>;
}
