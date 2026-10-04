import test from 'node:test';
import assert from 'node:assert/strict';
import { streamResearch } from './stream.js';

globalThis.localStorage = { getItem: () => null };

const encode = (event, data) => new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);

function mockStream(t, chunks, { close = true } = {}) {
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      if (close) controller.close();
      else signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true });
    },
  })));
}

const options = { topic: 'A claim', depth: 3, forceFresh: true };

test('a complete report finishes even if the server leaves the stream open', async (t) => {
  mockStream(t, [encode('status', { detail: 'Searching' }), encode('result', { report: 'A sourced report' })], { close: false });
  const results = [];
  let completed = 0;
  await streamResearch({ ...options, onResult: (data) => results.push(data.report), onDone: () => completed++ });
  assert.deepEqual(results, ['A sourced report']);
  assert.equal(completed, 1);
});

test('premature end and done without a report are errors', async (t) => {
  mockStream(t, [encode('done', {})]);
  await assert.rejects(streamResearch(options), /before the report arrived/);
});

test('server errors reach the caller', async (t) => {
  mockStream(t, [encode('error', { error: 'Provider unavailable' })]);
  await assert.rejects(streamResearch(options), /Provider unavailable/);
});

test('a stalled stream times out and reports an actionable error', async (t) => {
  mockStream(t, [new TextEncoder().encode(': keepalive\n\n')], { close: false });
  const errors = [];
  await streamResearch({ ...options, idleTimeoutMs: 15, onError: (error) => errors.push(error) });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /stopped responding/);
});

test('the overall deadline bounds a request independently of the idle deadline', async (t) => {
  mockStream(t, [], { close: false });
  await assert.rejects(streamResearch({ ...options, idleTimeoutMs: 1000, totalTimeoutMs: 15 }), /time limit/);
});

test('navigation cancellation is silent and a subsequent request can succeed', async (t) => {
  mockStream(t, [], { close: false });
  const controller = new AbortController();
  const errors = [];
  const request = streamResearch({ ...options, signal: controller.signal, onError: (error) => errors.push(error) });
  await new Promise((resolve) => setTimeout(resolve, 5));
  controller.abort();
  await request;
  assert.deepEqual(errors, []);
  t.mock.restoreAll();
  mockStream(t, [encode('result', { report: 'New research' })]);
  let report;
  await streamResearch({ ...options, onResult: (data) => { report = data.report; } });
  assert.equal(report, 'New research');
});

test('HTTP errors preserve the server explanation', async (t) => {
  mockStream(t, []);
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: 'Research limit reached' }), { status: 429 }));
  await assert.rejects(streamResearch(options), /Research limit reached/);
});
