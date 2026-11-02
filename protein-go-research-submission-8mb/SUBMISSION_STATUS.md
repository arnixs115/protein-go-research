# 과제 10 — 8MB 제한용 패키지 상태

논문 PDF·분석용 CSV·코드·결과·그림·실행 안내는 ZIP에 포함합니다. 큰 원자료 83개(177,808,088바이트)는 공개 저장소의 고정 커밋으로 분리했습니다.

공개 저장소: https://github.com/arnixs115/protein-go-research
고정 원자료: https://github.com/arnixs115/protein-go-research/tree/7d7cc33078aa8b684534f03ef339b46789f01a14/protein-go-research/data/raw

사용자가 기존 저장소의 공개 전환을 명시적으로 선택했고, 공개 전환 후 HTTP 200과 비공개 여부 false를 인증 없이 확인했습니다. 이어 파일 83개를 인증 없이 실제 다운로드하여 모두 기록된 SHA256과 일치함을 확인했습니다. 로그와 결과는 `verification_run/public_raw_verification.json` 및 `logs/public_raw_download.log`에 있습니다.

기존 원 프로젝트 161개 파일, 원본 응답 93개 체크섬, 전처리 3개·통계 CSV 5개 일치와 테스트 11개 통과 기록을 보존했습니다. 새 실행에서는 외부 파일을 복원한 뒤 이 검증을 재대조합니다. 논문 PDF는 바꾸지 않았고, 큰 원자료를 ZIP에서 제외한 것 외에 분석 조건·결과를 바꾸지 않았습니다.

`06_package_submission.py`는 외부 응답 파일·가상환경·캐시를 압축에서 제외하고 ZIP이 8,000,000바이트 미만인지 강제 검사합니다. 별도 위치 압축 해제, CRC·파일 목록·내부 체크섬·PDF 동일성을 대조한 결과는 ZIP 옆 검증 JSON에 기록합니다. 제출 시스템 업로드는 수행하지 않았습니다.

과거 전체 원자료 포함 패키지나 PDF 누락 상태의 기록은 `provenance/`의 역사적 자료입니다. 현재 사용 안내는 이 패키지의 README입니다. 제출할 파일은 작은 ZIP 1개뿐이며 약 182MB 기존 ZIP은 제출하지 않습니다.
