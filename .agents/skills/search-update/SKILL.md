---
name: search-update
description: Apply the maintenance rules before every Search Agent modification in fashion_recommendation_v2, including changes to its contracts, prompts, schemas, validation, source projections, version wiring, and regression tests. Preserve unrelated behavior and historical reproducibility. Does not apply to unrelated search implementations or read-only explanations.
---

# Search Update

Apply all seven rules below before and throughout every Search Agent modification. Preserve existing behavior, contracts, source paths, validation logic, versioning, and regression coverage unless the user's request explicitly requires a change. These rules govern the requested work; they do not authorize a general cleanup or migration.

Before editing, identify the affected role and version, trace its wiring and input sources, inspect the relevant generation/audit/correction paths and downstream consumers, and select the dependency and regression checks that cover the change. Distinguish the requested behavior change from invariants that must remain unchanged.

Paths below are relative to `src/fashion_recommendation_v2/` unless stated otherwise. Resolve the checked-out repository rather than relying on a particular absolute workspace path.

## 1. Scope and preservation

Only modify content related to the request. Preserve unmentioned features, rules, validation, exception handling, and recovery behavior. If responsibility must move, move it to the nearest appropriate owner. Do not arbitrarily add or delete Relation/Search Agent files or create unnecessary empty files.

If an additional deletion beyond the user's requested scope is necessary, identify exactly what would be deleted and why, prepare the reviewable proposal, and ask for confirmation before that deletion. Continue independent authorized work where possible.

## 2. Role organization

Group work by role when it shares the same inputs, outputs, and semantic rules. Keep prompt and schema folder/file names aligned:

```text
prompts/search/<role>/search_<role>*vN.py
schemas/search/<role>/search_<role>_vN.py
```

Roles are `requirements`, `planning`, `product_evaluation`, `item_normalization`, `ranking_observation`, and `relation_observation`. This is a role catalog, not a requirement to enable every role for every release. Preserve inactive/optional roles and resolve the actual wiring from `search/contracts.py`; do not create files or calls merely to fill the catalog.

Keep `retrieval` and `candidate_pool` as code-oriented schemas. Put shared helpers in neutral code locations. Apply the layout to necessary changes without reorganizing unrelated historical files.

## 3. Canonical rule ownership

Maintain one canonical location for each rule:

| Rule | Canonical owner |
| --- | --- |
| Field names, types, required/optional status, allowed values | Schema |
| Citation/source definitions for fields | Code source definitions |
| Gender defaults and priority | Code policy |
| Semantic interpretation: hard/soft constraints, OR, ranges | Shared role semantic rules |
| Step-specific work | Step-specific instructions layered on shared rules |

Source guidance and code validation must use the same definitions. Pass gender policy to the LLM, but apply the final policy in code. Generation, audit, and correction must use the same target contract. Keep audit judgment schemas separate from the schema of the response being audited.

## 4. Original model response

Do not reconstruct the original model response for validation. Preserve `model_response` field names, values, types, and nesting. Attach `code_validation` and code-derived results separately. Do not delete or move fields to hide validation errors.

## 5. Input paths and provenance

Preserve these fixed input paths and sources:

| Input | Required source |
| --- | --- |
| `original_user_query` | Actual user text |
| `user_query` | Search-expanded/projected query |
| `original_stylist_resolution` | Full original Stylist output |
| `stylist_resolution` | Source-preserving projection of resolved interpretation |
| `audience_context_v1` | Its existing source |
| `similarity_reference` | Its existing source |

Preserve Stylist `attribute`, `value`, and `source_text`, including OR values and their types. Fields retained only for source preservation must not revive excluded conditions into search.

## 6. Version wiring and dependency direction

Declare role/version wiring explicitly in `search/contracts.py`. Distinguish release versions, role prompt/schema versions, and code implementation versions. For example, the v53 contract reuses requirements v50, planning v52, planning code v50, product_evaluation v45, and ranking_observation v5, with `item_normalization=None`. Read the actual target contract before editing; do not infer module names from the release number or copy unchanged contracts into new version files. Preserve old-version reproducibility and existing results. Inspect how shared changes affect historical versions; isolate requested new behavior when needed to preserve those contracts.

Do not create new rules by chaining string replacements over old prompts. Do not introduce schemas-to-prompts/agents references, prompts-to-agents reverse references, or circular dependencies. Change model choice, call count, or budget only when the request requires it.

## 7. Verification and reporting

For every changed rule, verify alignment across schema, prompt, code validation, correction, and downstream consumers. Run dependency checks and relevant regression tests. Verify success, failure, correction, and repeated-failure paths, including existing retry limits and terminal behavior. Add or adjust focused coverage where the changed behavior lacks it.

Never overwrite expected values merely to make tests pass. Change an expectation only when the requested contract change justifies it, while retaining coverage for behavior that must remain unchanged. Preserve historical fixtures and recorded results.

Use the repository's existing test setup. Starting points, relative to the repository root, include:

- `tests/test_search_contract_layout.py`: role paths, version wiring, historical contracts, and dependency direction.
- `tests/test_search_consolidation.py`: frozen prompt/schema contracts and consolidated module use.
- Relevant `tests/test_search_*.py`, Stylist/Search integration tests, and fixtures for the affected role/version and recovery paths.
- `evals/search/eval_version.md`: existing evaluation/version conventions when the request affects them.

Inspect selected tests and runners to distinguish local mocked/replay checks from real API execution. Do not assume an evaluation runner is offline. Use real API runs only within the user's authorized scope and budget.

Report changed locations and their purpose, validation commands and outcomes, preserved contracts, and remaining limitations or unverified paths. Clearly label real API runs separately from mocked or replay tests. If checks cannot run, report the blocker without claiming they passed.
