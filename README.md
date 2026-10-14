# Fashion Recommendation — service snapshot

현재 서비스의 구현을 읽고 로컬에서 실행하기 위한 공개용 복사본입니다. 원본 저장소의 Git 이력, 사용자 데이터, 평가 결과는 포함하지 않습니다.

## 구현 문서

현재 서비스의 구조·입출력·실행 흐름·정책·실패 처리·공개 테스트를 설명합니다. 처음에는 [전체 구조](docs/architecture.md)를 읽고 각 단계로 이동하세요.

| 문서 | 내용 |
| --- | --- |
| [Orchestrator](docs/orchestrator.md) | 요청·세션·상태와 단계 연결 |
| [Planner](docs/planner.md) | 실행 계획·의존성 검증 |
| [Stylist](docs/stylist.md) | 조건 해석·취향·기준 상품 문맥 |
| [Search](docs/search.md) | 조회·평가·후보 수집·종료 조건 |
| [Relation](docs/relation.md) | 유사성·조합 평가와 근거별 점수 |
| [Ranking](docs/ranking.md) | 추천 자격·점수·개인화 우선 선정 |
| [Summary](docs/summary.md) | 추천 설명·근거·응답 검증 |
| [Preference](docs/preference.md) | 행동·관찰에서 프로필 생성·저장 |

## 서비스 버전

| 구성 | 연결된 버전 |
| --- | --- |
| Orchestrator | v10 |
| Planner | v4 |
| Stylist | v6 |
| Search | v56 |
| Relation | v8 |
| Ranking | v15 |
| Summary | v11 |
| Preference | v4 |

실제 연결은 `src/fashion_recommendation_v2/server/recommendation_factory.py`와 `scripts/run_preference_server.py`에 있습니다. `agents/`, `llm/`, `prompts/`, `schemas/` 및 이들이 가져오는 공통 모듈을 포함합니다. 현재 서비스가 사용하는 공통 로직은 역할 파일 안에 보존했습니다. 내부 계약·심볼에는 버전 이름이 남을 수 있지만, 모든 과거 버전의 실행을 제공하는 배포본은 아닙니다. 버전 선택 옵션은 위 서비스 조합을 사용하세요.

## API 키 없이 UI 실행

Node.js 22 이상과 npm을 사용합니다.

```sh
cd frontend
npm ci
npm run dev
```

http://127.0.0.1:5173 에서 기본 모의 모드로 실행됩니다. 로컬 SVG 상품과 고정 응답으로 화면을 확인하며 실제 추천 API를 호출하지 않습니다.

## 실제 추천 실행

Python 3.12 환경에서 프로젝트 루트를 기준으로 실행합니다.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-preference.txt
cp .env.example .env
```

`.env`에 본인의 OpenAI API 키와 eBay Browse API 자격 증명을 입력하세요. API 키는 프런트엔드 환경변수에 넣지 않습니다. 모델별 기본값은 코드에 유지했으므로 사용하는 API 계정에서 해당 모델을 사용할 수 있어야 합니다. 실제 추천·취향 갱신에는 외부 API 호출과 비용이 발생할 수 있습니다.

```sh
PYTHONPATH=src python scripts/init_preference_db.py
PYTHONPATH=src python scripts/run_preference_server.py --recommendations \
  --origin http://127.0.0.1:5173
```

프런트엔드를 실행한 뒤 http://127.0.0.1:5173/?mode=live 에서 직접 요청을 입력하세요. 서버는 빈 로컬 DB부터 시작합니다. 기존 사용자 취향은 포함하지 않으며, 프로필이 없는 Warm 사용자는 개인화 없이 처리합니다. Similarity 요청은 원래 사용자 상태를 유지하면서 Stylist와 Ranking의 취향 반영을 끕니다.

**고정 예제 제한:** 실제 API 모드의 유사 상품 예제와 A/B 취향 예제는 원본의 앵커·프로필 데이터가 필요하므로 이 복사본에서는 `quick_start_data_unavailable`로 실패합니다. 직접 입력하는 일반 요청 또는 모의 모드를 사용하세요. 원본 평가 데이터를 공개 샘플로 위장해 넣지 않았습니다.

## 테스트

```sh
python -m pip install -r requirements-dev.txt
PYTHONPATH=src python -m pytest -q tests
cd frontend
npm test
npm run build
```

Python 테스트는 저장소·세션·HTTP 계약, 환율 처리, 요약 스키마, LLM 스트림 정리 및 서비스 의존성 연결을 검증합니다. 실제 API 품질 평가는 포함하지 않습니다. 프런트엔드 브라우저 테스트는 로컬 Chrome이 설치된 경우 `npm run test:e2e`로 실행할 수 있습니다.

## 파일과 유지보수

`PUBLIC_FILES.json`에 파일별 SHA-256과 포함 이유를 기록했습니다. `PUBLIC_REVIEW.md`는 이 복사본의 검증 결과입니다.

`.agents/skills/`에는 common/preference/ranking/relation/search 유지보수 Skill 5개와 UI 메타데이터를 포함했습니다. Skill의 개인 로컬 절대 경로는 상대 경로로 정리했습니다. 비공개 버전 기록·과거 테스트를 언급하는 부분은 남아 있습니다. 공개본에서는 현재 체크아웃의 상대 경로를 사용하고, 없는 평가 자료를 요구하는 절차는 적용할 수 없습니다. 실행 안내는 이 README와 포함된 테스트를 기준으로 합니다. 과거 평가를 재실행하는 E2E Skill은 포함하지 않았습니다.

비밀정보, 실제 DB, 실행 결과, 평가·버전 기록, 내부 설계 문서, Excel, 캐시, 가상환경, 기존 `.git`은 제외했습니다. 이 폴더만 별도 Git 저장소의 루트로 사용하세요.

## 프롬프트 읽는 순서

공개본의 프롬프트는 역할마다 한 파일로 통합했습니다. 서비스용 최종 문자열은 해당 파일 앞쪽에 있으며, 이전 버전 파일을 차례로 열지 않아도 읽을 수 있습니다.

| 역할 | 파일 | 현재 서비스 진입점 |
| --- | --- | --- |
| Orchestrator | `prompts/orchestrator.py` | `ORCHESTRATOR_PROMPT_V9`, `ORCHESTRATOR_CORRECTION_PROMPT_V9` (서비스 v10) |
| Planner | `prompts/planner.py` | `PLANNER_SYSTEM_PROMPT` |
| Stylist | `prompts/stylist.py` | `STYLIST_PROMPT_V6`, `STYLIST_COMPATIBILITY_PROMPT_V6` |
| Ranking | `prompts/ranking.py` | `PREFERENCE_PROMPT` (서비스 v15가 사용하는 취향 평가) |
| Relation | `prompts/relation.py` | `RELATION_PROMPT_V6` (서비스 v8) |
| Summary | `prompts/summary.py` | `SUMMARY_PROMPT` (서비스 v11) |
| Preference | `prompts/preference.py` | `PREFERENCE_INTERPRETATION_PROMPT` |
| Search 요구사항 | `prompts/search/requirements.py` | `requirements_prompt` |
| Search 검색 계획 | `prompts/search/planning.py` | `initial_plan_prompt`, `strategy_prompt` |
| Search 상품 평가 | `prompts/search/product_evaluation.py` | `build_visual_batch_prompt`, `build_review_prompt` |
| Search 랭킹 관찰 | `prompts/search/ranking_observation.py` | `IMAGE_OBSERVATION_V5_CONTRACT`, `VISUAL_CONSISTENCY_V5_CONTRACT` |

기존 역할인 `conversation.py`, Search의 `item_normalization.py`, `relation_observation.py`도 유지했습니다. `_shared.py`는 공용 서식 함수, `_compat.py`는 기존 계약 이름과 통합 파일의 심볼을 연결하는 표입니다. 이전 호출부에서 필요한 상수·함수는 같은 역할 파일 안에 호환 이름으로 남아 있습니다. 새로운 서비스 버전이나 프롬프트 의미 변경은 없습니다.

통합 전 고정 문자열 251개와 합성 입력으로 만든 동적 출력 29개를 직접 비교해 모두 일치했습니다. 공백·줄바꿈을 포함한 UTF-8 기준이며, 기준 해시는 `tests/fixtures/prompt_fingerprints.json`, 재검증은 `tests/test_prompt_equivalence.py`에 있습니다. 동적 검증은 초기·단일·교정 계획, 재검색, 일반/similarity/compatibility 요구사항, 상품 생성/리뷰, 카테고리·필터·검색결과 처리 경로를 포함합니다. 가능한 모든 입력이나 실제 모델 응답의 동일성을 주장하는 검사는 아닙니다.

## 역할별 서비스 코드

아래 경로는 `src/fashion_recommendation_v2/` 기준입니다. 같은 역할의 버전별 구현은 한 파일에 모으고, 역할 사이의 구분은 유지했습니다.

| 폴더 | 읽을 파일과 역할 |
| --- | --- |
| `preference/` | 기존 역할 파일 유지: `contracts.py`, `profile_lookup.py`, `observations.py`, `interpretation_*.py` |
| `ranking/` | `personalization.py` 취향 평가, `ranking_scoring.py` 점수, `ranking_policy.py` 정책, `partial_evaluation.py` 부분 실패 처리 |
| `relation/` | `relation_evidence.py` 근거, `relation_scoring.py` 점수, `execution.py` 실행, `streaming.py` 병렬 결과 처리 |
| `schemas/` | `ranking.py`, `relation.py`, `stylist.py`, `summary.py`, `orchestrator.py` 등 역할별 계약. `search/` 하위의 요구사항·검색 계획·상품 평가 구분 유지 |
| `search/` | `requirements.py`, `planning.py`, `product_evaluation.py`, `product_validation.py`, `product_semantics.py` 등 단계별 파일 |
| `tools/` | `ranking_judgments.py`, `ranking_observations.py` 및 기존 역할별 도구 |

통합 대상 159개 모듈을 41개 역할 파일로 정리했습니다. 이 숫자는 여섯 폴더 전체 파일 수가 아니라 통합 대상으로 선택한 모듈 수입니다. `preference/`처럼 이미 역할별로 나뉜 파일과 다른 역할의 도구는 그대로 유지합니다. 원시 상품의 공용 타입은 순환 import를 피하도록 `schemas/common.py`에 두었습니다.

파일 안에서는 필요한 공통 기반 구현을 먼저 정의하고 후속 구현을 이어갑니다. 기존 이름이 충돌하는 내부 심볼에는 버전 접미사가 남습니다. `module_compat.py`는 기존 동적 계약 이름을 역할 모듈에 연결하고, 검증용 함수·클래스 식별자를 보존합니다. 서비스 버전과 평가 규칙을 변경한 작업은 아닙니다.

`tests/test_role_consolidation.py`는 변경 전 JSON 스키마 1,878개, 합성 서비스 사례 15개, 41개 모듈의 독립 import를 검증합니다. fixture는 합성 상품·취향·모델 응답이며 실제 API를 호출하지 않습니다. 시간 측정값을 제외한 출력과 호출 횟수를 비교하고 UUID는 고정합니다. 실제 모델 품질이나 모든 입력에 대한 동등성을 보장하는 검사는 아닙니다.

스키마 해시 기준은 Pydantic 2.10.3과 2.14.1에서 각각 변경 전 코드로 수집했습니다. 다른 Pydantic 버전에서는 스키마 해시 검사만 skip하며, 나머지 검사는 실행합니다. 전체 검사를 재현하려면 두 버전 중 하나를 사용하세요.
