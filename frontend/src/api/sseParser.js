// Preserve SSE event state across arbitrary network chunk boundaries.
export function createEventParser(onEvent) {
  let buffer = '';
  let event = 'message';
  let data = [];

  const dispatch = () => {
    if (data.length) onEvent(event, data.join('\n'));
    event = 'message';
    data = [];
  };
  const line = (value) => {
    if (value.endsWith('\r')) value = value.slice(0, -1);
    if (!value) { dispatch(); return; }
    if (value.startsWith(':')) return;
    const colon = value.indexOf(':');
    const field = colon < 0 ? value : value.slice(0, colon);
    let content = colon < 0 ? '' : value.slice(colon + 1);
    if (content.startsWith(' ')) content = content.slice(1);
    if (field === 'event') event = content;
    if (field === 'data') data.push(content);
  };
  return {
    push(chunk) {
      buffer += chunk;
      let index;
      while ((index = buffer.indexOf('\n')) !== -1) {
        const next = buffer.slice(0, index);
        buffer = buffer.slice(index + 1);
        line(next);
      }
    },
    finish() {
      if (buffer) line(buffer);
      buffer = '';
      dispatch();
    },
  };
}
