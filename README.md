# gpt

NAIA 2.0용 `Prompt Library` 모듈 예시 구현이 포함되어 있습니다.

- 파일: `modules/prompt_library_module.py`
- 핵심 기능:
  - 프롬프트 라이브러리 목록/검색/편집
  - 단일 생성/대기열 publish 이벤트
  - `prompt.txt` 줄 단위 분할 (`1.txt`, `2.txt`, ...)
  - 자연 정렬
  - 이미지 결과 자동 점검+재생성 요청 payload 생성
  - 수정 로그를 `save/prompt_library/fix_logs/N.txt`로 저장
