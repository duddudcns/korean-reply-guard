"""Tests for korean_reply_guard.py. Run: python -I -m pytest ~/.claude/hooks/korean-reply-guard -q"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import korean_reply_guard as g  # noqa: E402

HOOK = str(Path(__file__).with_name('korean_reply_guard.py'))


def line(role, content, **extra):
    return json.dumps({'type': role, 'message': {'role': role, 'content': content}, **extra}, ensure_ascii=False)


def transcript(tmp_path, *lines):
    p = tmp_path / 't.jsonl'
    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return p


def run(payload):
    r = subprocess.run([sys.executable, '-I', HOOK], input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8')
    return r.returncode, r.stdout


ENGLISH = 'The server session merged three rows and the gate is still running, so nothing is committed yet. I will check again later.'
KOREAN = '서버 세션이 세 행을 반영했고 게이트는 아직 도는 중이라 커밋은 아직 안 했어요. 나중에 다시 확인할게요.'


def test_ratio_counts_prose_not_code():
    text = '설정을 고쳤어요.\n```python\nimport json, sys, subprocess, pathlib, collections\n```\n`work/tools/pm.py` 와 https://example.com/a/b 참고.'
    assert g.hangul_ratio(g.strip_code(text)) > 0.5


def test_english_reply_blocks(tmp_path):
    t = transcript(tmp_path, line('user', '상태 알려줘'), line('assistant', [{'type': 'text', 'text': ENGLISH}]))
    code, out = run({'transcript_path': str(t), 'stop_hook_active': False})
    assert code == 0 and json.loads(out)['decision'] == 'block'


def test_korean_reply_passes(tmp_path):
    t = transcript(tmp_path, line('user', '상태 알려줘'), line('assistant', [{'type': 'text', 'text': KOREAN}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False}) == (0, '')


def test_text_split_over_entries_and_tool_results_is_one_turn(tmp_path):
    # Korean text before a tool call, then a short English line after it: the turn as a whole is Korean.
    t = transcript(tmp_path,
                   line('user', '진행해'),
                   line('assistant', [{'type': 'text', 'text': KOREAN}, {'type': 'tool_use', 'id': 'x', 'name': 'Bash', 'input': {}}]),
                   line('user', [{'type': 'tool_result', 'tool_use_id': 'x', 'content': 'long english tool output ' * 20}]),
                   line('assistant', [{'type': 'text', 'text': KOREAN + ' Done.'}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False}) == (0, '')


def test_previous_turn_english_not_counted(tmp_path):
    t = transcript(tmp_path,
                   line('user', '첫 질문'), line('assistant', [{'type': 'text', 'text': ENGLISH}]),
                   line('user', '다음'), line('assistant', [{'type': 'text', 'text': KOREAN}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False}) == (0, '')


def test_short_reply_and_rerun_pass(tmp_path):
    t = transcript(tmp_path, line('user', 'ok?'), line('assistant', [{'type': 'text', 'text': 'Done.'}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False}) == (0, '')
    t = transcript(tmp_path, line('user', '상태'), line('assistant', [{'type': 'text', 'text': ENGLISH}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': True}) == (0, '')


def test_sidechain_and_bad_input_pass(tmp_path):
    t = transcript(tmp_path, line('user', '상태'), line('assistant', [{'type': 'text', 'text': ENGLISH}], isSidechain=True))
    assert run({'transcript_path': str(t), 'stop_hook_active': False}) == (0, '')
    assert run({'transcript_path': str(tmp_path / 'missing.jsonl')}) == (0, '')
    r = subprocess.run([sys.executable, '-I', HOOK], input='not json', capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ''


def test_last_assistant_message_is_judged_not_interim_notes(tmp_path):
    # 2026-10-29: English interim notes, final Korean reply not yet in the transcript -> was blocked.
    t = transcript(tmp_path, line('user', '진행해'), line('assistant', [{'type': 'text', 'text': ENGLISH}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False, 'hook_event_name': 'Stop',
                'last_assistant_message': KOREAN}) == (0, '')


def test_english_last_assistant_message_blocks_with_ratio(tmp_path):
    t = transcript(tmp_path, line('user', '상태'), line('assistant', [{'type': 'text', 'text': KOREAN}]))
    code, out = run({'transcript_path': str(t), 'stop_hook_active': False, 'hook_event_name': 'Stop',
                     'last_assistant_message': ENGLISH})
    reason = json.loads(out)['reason']
    assert json.loads(out)['decision'] == 'block' and '0.00' in reason


def test_empty_field_falls_back_to_last_text_entry_only(tmp_path):
    t = transcript(tmp_path,
                   line('user', '진행해'),
                   line('assistant', [{'type': 'text', 'text': ENGLISH}, {'type': 'tool_use', 'id': 'x', 'name': 'Bash', 'input': {}}]),
                   line('user', [{'type': 'tool_result', 'tool_use_id': 'x', 'content': 'ok'}]),
                   line('assistant', [{'type': 'text', 'text': KOREAN}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False, 'last_assistant_message': ''}) == (0, '')


def test_fallback_without_final_text_passes(tmp_path):
    t = transcript(tmp_path,
                   line('user', '진행해'),
                   line('assistant', [{'type': 'text', 'text': ENGLISH}, {'type': 'tool_use', 'id': 'x', 'name': 'Bash', 'input': {}}]),
                   line('user', [{'type': 'tool_result', 'tool_use_id': 'x', 'content': 'ok'}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False}) == (0, '')


def test_subagent_stop_is_not_judged(tmp_path):
    t = transcript(tmp_path, line('user', '상태'), line('assistant', [{'type': 'text', 'text': ENGLISH}]))
    assert run({'transcript_path': str(t), 'stop_hook_active': False, 'hook_event_name': 'SubagentStop',
                'last_assistant_message': ENGLISH}) == (0, '')
