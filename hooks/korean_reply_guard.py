"""Stop hook: block a final reply that is not written in Korean (user rule: every reply in Korean, 2026-10-26).

Judges only the final reply: payload["last_assistant_message"] when present, else the text of the assistant entries after
the last tool result or real user message in the transcript (the transcript may not hold the final reply yet at Stop:
2026-10-29 English interim notes were judged instead of a Korean reply). Drops code blocks, inline code, URLs and paths,
then compares Hangul syllables with Latin letters. Under MIN_RATIO Hangul with at least MIN_LETTERS letters ->
{"decision": "block", "reason": ...}. Passes for SubagentStop, when stop_hook_active (the rewrite after one block), when
no final text is found, for very short replies, and on any read error.
"""
import json
import re
import sys

MIN_RATIO = 0.3
MIN_LETTERS = 40
REASON = ('마지막 답의 한글 비율이 {ratio:.2f} 로 기준 {min:.2f} 보다 낮습니다. 사용자 규칙: 모든 답은 한국어로 씁니다'
          '(코드·경로·식별자는 원래대로). 마지막 답을 그대로 한국어로 다시 쓰세요.')

CODE_BLOCK = re.compile(r'```.*?```', re.S)
INLINE = re.compile(r'`[^`\n]*`')
URL = re.compile(r'https?://\S+|\[[^\]]*\]\([^)]*\)')
PATH = re.compile(r'\S*[\\/]\S*')
HANGUL = re.compile(r'[가-힣]')
LATIN = re.compile(r'[A-Za-z]')


def strip_code(text):
    for rx in (CODE_BLOCK, URL, INLINE, PATH):
        text = rx.sub(' ', text)
    return text


def hangul_ratio(text):
    h, l = len(HANGUL.findall(text)), len(LATIN.findall(text))
    return h / (h + l) if h + l else 1.0


def is_real_user(entry):
    msg = entry.get('message') or {}
    if entry.get('type') != 'user' or msg.get('role') != 'user':
        return False
    c = msg.get('content')
    if isinstance(c, str):
        return True
    return any(isinstance(b, dict) and b.get('type') == 'text' for b in c or [])


def is_tool_result(entry):
    c = (entry.get('message') or {}).get('content')
    return entry.get('type') == 'user' and isinstance(c, list) and any(
        isinstance(b, dict) and b.get('type') == 'tool_result' for b in c)


def final_text(path):
    """Text of the assistant entries after the last tool result or real user message ('' when the turn ends in a tool call)."""
    entries = []
    with open(path, encoding='utf-8') as fh:
        for raw in fh:
            try:
                entries.append(json.loads(raw))
            except ValueError:
                continue
    parts = []
    for e in reversed(entries):
        if is_real_user(e) or is_tool_result(e):
            break
        msg = e.get('message') or {}
        if e.get('type') != 'assistant' or e.get('isSidechain') or msg.get('role') != 'assistant':
            continue
        c = msg.get('content')
        if isinstance(c, str):
            parts.append(c)
        else:
            parts.extend(b.get('text', '') for b in c or [] if isinstance(b, dict) and b.get('type') == 'text')
    return '\n'.join(reversed(parts))


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace'))
        if payload.get('stop_hook_active') or payload.get('hook_event_name') == 'SubagentStop':
            return 0
        text = payload.get('last_assistant_message')
        if not isinstance(text, str) or not text.strip():
            text = final_text(payload['transcript_path'])
        text = strip_code(text)
    except (ValueError, KeyError, OSError, TypeError, AttributeError):
        return 0
    if len(HANGUL.findall(text)) + len(LATIN.findall(text)) < MIN_LETTERS or hangul_ratio(text) >= MIN_RATIO:
        return 0
    # Windows stdout defaults to cp949; Claude Code reads hook output as UTF-8.
    sys.stdout.buffer.write(json.dumps({'decision': 'block', 'reason': REASON.format(ratio=hangul_ratio(text), min=MIN_RATIO)}, ensure_ascii=False).encode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
