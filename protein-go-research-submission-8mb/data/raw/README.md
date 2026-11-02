# 대용량 원자료의 공개 저장 위치

공개 저장소: https://github.com/arnixs115/protein-go-research

고정 버전 원자료: https://github.com/arnixs115/protein-go-research/tree/7d7cc33078aa8b684534f03ef339b46789f01a14/protein-go-research/data/raw

업로드 용량 제한 때문에 전체 수집의 큰 응답 83개(정상 페이지 82개와 초기 미채택 원본 1개), 177,808,088바이트를 ZIP에서 제외했습니다. 나머지 수집 메타데이터·체크섬·소량 검증 표본은 ZIP에 있습니다. 파일별 고정 커밋 경로·SHA256·크기는 `external_raw_files.json`에 있습니다.

제출 폴더에서 `python scripts/07_restore_raw_data.py`를 실행하면 인증 없이 이 원본 바이트를 내려받고 검증합니다. `--verify-only`는 이미 복원한 파일을 오프라인으로 검증합니다. UniProt API는 다시 호출하지 않습니다.
