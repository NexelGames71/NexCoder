const COMPLETE_THINK_BLOCK = /<think\b[^>]*>[\s\S]*?<\/think\s*>/gi;
const THINK_OPEN = /<think\b[^>]*>/i;
const THINK_CLOSE = /<\/think\s*>/i;

/** Defense-in-depth cleanup for restored chats made by reasoning models. */
export function sanitizeAssistantText(text: string): string {
  let value = String(text || '');
  let previous = '';
  while (value !== previous) {
    previous = value;
    value = value.replace(COMPLETE_THINK_BLOCK, '');
  }
  let close = THINK_CLOSE.exec(value);
  while (close) {
    value = value.slice(close.index + close[0].length);
    close = THINK_CLOSE.exec(value);
  }
  const opening = THINK_OPEN.exec(value);
  if (opening) value = value.slice(0, opening.index);
  return value
    .replace(/<\/?think\b[^>]*>/gi, '')
    .replace(/<tool_call\s+name="[^"]+">[\s\S]*?<\/tool_call>/gi, '')
    .trim();
}
