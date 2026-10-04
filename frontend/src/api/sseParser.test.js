import test from 'node:test';
import assert from 'node:assert/strict';
import { createEventParser } from './sseParser.js';

const input = ': keepalive\r\nevent: status\r\ndata: {"detail":"Working"}\r\n\r\nevent: result\r\ndata: {"report":"Finished research"}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n';

test('events survive every possible two-chunk boundary', () => {
  for (let split = 0; split <= input.length; split++) {
    const events = [];
    const parser = createEventParser((type, data) => events.push([type, JSON.parse(data)]));
    parser.push(input.slice(0, split));
    parser.push(input.slice(split));
    parser.finish();
    assert.deepEqual(events, [['status', { detail: 'Working' }], ['result', { report: 'Finished research' }], ['done', {}]]);
  }
});
test('one-character chunks and an unterminated final event', () => {
  const events = [];
  const parser = createEventParser((type, data) => events.push([type, data]));
  for (const char of 'event: result\ndata: {"report":"ok"}') parser.push(char);
  parser.finish();
  assert.deepEqual(events, [['result', '{"report":"ok"}']]);
});
test('multiline data and comments', () => {
  const events = [];
  const parser = createEventParser((type, data) => events.push([type, data]));
  parser.push('event: result\ndata: {"report":\n: heartbeat\ndata: "ok"}\n\n');
  parser.finish();
  assert.deepEqual(events, [['result', '{"report":\n"ok"}']]);
});
