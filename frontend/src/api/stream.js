import { apiFetch } from './client.js';
import { createEventParser } from './sseParser.js';

export async function streamResearch({ topic, depth, forceFresh, visualPlanner, onStatus, onResult, onError, onDone, signal,
  idleTimeoutMs = 120000, totalTimeoutMs = 600000 }) {
  const controller = new AbortController();
  let reader;
  let receivedResult = false;
  let receivedDone = false;
  let timeoutMessage;
  let idleTimer;
  const abort = () => controller.abort();
  const timeOut = (message) => {
    timeoutMessage = message;
    controller.abort();
  };
  const resetIdleTimer = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => timeOut('Research stopped responding for two minutes. Please retry.'), idleTimeoutMs);
  };
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  resetIdleTimer();
  const totalTimer = setTimeout(() => timeOut('Research exceeded the time limit. Please retry with a lower research depth.'), totalTimeoutMs);
  try {
    const response = await apiFetch('/api/research/stream', {
      method: 'POST',
      body: JSON.stringify({ topic, depth, force_fresh: forceFresh, visual_planner: visualPlanner }),
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = typeof payload.detail === 'string' ? payload.detail : '';
      throw new Error(detail || `Research request failed (${response.status}). Please try again.`);
    }
    if (!response.body) throw new Error('The research response was empty. Please try again.');
    reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    const parser = createEventParser((event, raw) => {
      if (!['status', 'result', 'done', 'error'].includes(event)) return;
      let data;
      try { data = JSON.parse(raw); } catch { throw new Error('The research stream returned an invalid message. Please try again.'); }
      // Keepalive comments do not count as research progress.
      resetIdleTimer();
      if (event === 'status') onStatus?.(data);
      if (event === 'result') {
        if (typeof data.report !== 'string' || !data.report.trim()) throw new Error('Research completed without a report. Please try again.');
        receivedResult = true;
        onResult?.(data);
      }
      if (event === 'done') receivedDone = true;
      if (event === 'error') throw new Error(data.error || 'Research failed. Please try again.');
    });
    while (!receivedResult && !receivedDone) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    if (!receivedResult) {
      parser.push(decoder.decode());
      parser.finish();
    }
    if (!receivedResult) throw new Error('The connection ended before the report arrived. Please retry your research.');
    onDone?.({ message: 'Research complete' });
  } catch (error) {
    if (!signal?.aborted) {
      const message = timeoutMessage || error.message;
      if (onError) onError(message);
      else throw new Error(message);
    }
  } finally {
    clearTimeout(idleTimer);
    clearTimeout(totalTimer);
    signal?.removeEventListener('abort', abort);
    if (reader) {
      void reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    controller.abort();
  }
}
