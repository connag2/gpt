# gpt

NAIA 2.0용 Prompt Library 모듈 샘플 구현.

## 파일
- `modules/prompt_library_module.py`

## 포함 기능
- 프롬프트 라이브러리 목록/검색/편집
- 단일 생성/대기열 publish 이벤트
- `prompt.txt` 줄 단위 분할 (`1.txt`, `2.txt`, ...)
- 자연 정렬
- Auto Refine 요청 (provider/model/api key/base url/재시도 정책)
- API 설정 저장/불러오기 (`save/prompt_library/api_settings.json`)
- 실행/오류 로그 저장 (`save/prompt_library/fix_logs/N.txt`)
- 로그 목록/미리보기 UI
