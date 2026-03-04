# gpt

NAIA 2.0용 Prompt Library 모듈 샘플 구현.

## 파일
- `modules/prompt_library_module.py`

## 포함 기능
- 프롬프트 라이브러리 목록/검색/편집
- 단일 생성/대기열 적재 publish 이벤트 + 대기열 패널(다음 1개/전체/중지/제거/비우기)
- `prompt.txt` 줄 단위 분할 (`1.txt`, `2.txt`, ...)
- 자연 정렬
- Auto Refine 요청 (의도와 다르거나 부자연스러우면 FAIL) + Judge 모드(API/OpenAI/Gemini, Local YOLO, Local MediaPipe, Local Aesthetic) + 임계값(심미/해부학)
- API 설정 저장/불러오기 (`save/prompt_library/api_settings.json`)
- API 검수(인증 테스트) + OpenAI/Gemini 모델 선택(직접 입력 가능)
- 실행/오류 로그 저장 (`save/prompt_library/fix_logs/N.txt`)
- 로그 목록/미리보기 UI

- 로컬 해부학 판별 권장 실패 규칙: `detected_errors > anatomy_error_limit`
