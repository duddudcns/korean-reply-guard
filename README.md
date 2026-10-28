# korean-reply-guard

Claude Code Stop hook: 마지막 답의 한글 비율이 0.3 미만이면(글자 40자 이상) 막고 한국어로 다시 쓰게 한다.

- 판정 대상: Stop 입력의 `last_assistant_message`. 없으면 transcript 에서 마지막 tool 결과 뒤의 답만 본다(중간 메모는 보지 않음).
- 코드 블록, 인라인 코드, URL, 경로는 세지 않는다.
- SubagentStop, 다시 쓴 답(`stop_hook_active`), 답을 못 찾은 경우, 읽기 오류는 통과.
- 필요: PATH 의 `python`(3.9+).

테스트: `python -I -m pytest hooks -q`
