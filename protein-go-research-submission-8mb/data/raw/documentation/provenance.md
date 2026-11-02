2026-10-30 사전 구조 확인 자료.

- `result-fields.json`: https://rest.uniprot.org/configure/uniprotkb/result-fields — PowerShell Invoke-WebRequest, HTTP 200.
- `uniprotkb-openapi.json`: https://rest.uniprot.org/uniprotkb/api/docs — PowerShell Invoke-WebRequest, HTTP 200.
- `../structure-probe.json`: https://rest.uniprot.org/uniprotkb/search?query=organism_id%3A9606%20AND%20reviewed%3Atrue&format=json&size=10 — PowerShell Invoke-WebRequest, HTTP 200. Content를 UTF-8 JSON으로 보존했으며 requests의 바이트 보존 원본과 구분한다. 응답 Date: Fri, 30 Oct 2026 07:19:53 GMT. X-Total-Results: 20431. X-UniProt-Release: 2026_03. X-UniProt-Release-Date: 02-September-2026.

이전 `size=1&sort=accession%20asc` 구조 확인 요청은 HTTP 500 Internal server error로 실패하여 단백질 데이터를 받지 못했다. 최종 스크립트는 정렬을 지정하지 않는다.
정식 검증의 완전한 URL·응답 헤더·시각·SHA256은 `../20261030T072135Z_8fce6346/metadata.json`에 있다.
