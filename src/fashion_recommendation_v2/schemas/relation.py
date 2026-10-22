"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- relation ----

"""Anchor-to-candidate relationship contracts; scores are not probabilities."""
from fashion_recommendation_v2.validation_reuse import validated_once
from typing import Literal as Literal_base
from pydantic import Field as Field_base
from pydantic import model_validator as model_validator_base
from pydantic import model_serializer
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysis
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV36_v36 as SearchItemAnalysisV36
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV40_v40 as SearchItemAnalysisV40
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV41_v41 as SearchItemAnalysisV41
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV42
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV43
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV44
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV45
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV57_search_product_evaluation_v57 as SearchItemAnalysisV57_relation
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV59_search_product_evaluation_v59 as SearchItemAnalysisV59_relation
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
from fashion_recommendation_v2.schemas.relation_scoring import RelationScoreBreakdown
RelationEvaluationVersion = Literal_base['legacy', 'v0', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9']
EVIDENCE_FIELDS = ('title', 'category_path', 'category_id_path', 'price', 'condition', 'condition_description', 'color', 'size', 'fit', 'material', 'pattern', 'brand', 'strength', 'garment_care', 'theme', 'season', 'occasion', 'detail')

@_preserve_class('RelationEvidenceError', 'fashion_recommendation_v2.schemas.relation')
class RelationEvidenceError(ValueError):
    """Serializable field-level diagnostics, also used for the single correction retry."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__('Invalid candidate evidence_fields: ' + '; '.join((f"item_id={i['item_id']!r}, field={i['field']!r}, reason={i['reason']}; available_fields={i['available_fields']}" for i in issues)))

@_preserve_class('ReferenceItem', 'fashion_recommendation_v2.schemas.relation')
class ReferenceItem(StrictBaseModel_base):
    request_id: str
    rank: int = Field_base(ge=1)
    item: ProductRecord
    search_analysis: SearchItemAnalysis | SearchItemAnalysisV36 | SearchItemAnalysisV40 | SearchItemAnalysisV41 | SearchItemAnalysisV42 | SearchItemAnalysisV43 | SearchItemAnalysisV44 | SearchItemAnalysisV59_relation | SearchItemAnalysisV57_relation | SearchItemAnalysisV45 | None = None

    @model_validator_base(mode='after')
    def evidence_identity(self):
        from fashion_recommendation_v2.search.evidence_projection import validate_analysis_identity
        validate_analysis_identity(self.item, self.search_analysis)
        return self

    @model_serializer(mode='wrap')
    def serialize_analysis(self, handler):
        data = handler(self)
        if self.search_analysis is None:
            data.pop('search_analysis', None)
        return data

@_preserve_class('RelationAgentInput', 'fashion_recommendation_v2.schemas.relation')
class RelationAgentInput(StrictBaseModel_base):
    evaluation_version: RelationEvaluationVersion = 'legacy'
    candidate_set: CandidateSet
    intent: RelationIntent
    anchor_item: ProductRecord | None = None
    anchor_search_analysis: SearchItemAnalysis | SearchItemAnalysisV36 | SearchItemAnalysisV40 | SearchItemAnalysisV41 | SearchItemAnalysisV42 | SearchItemAnalysisV43 | SearchItemAnalysisV44 | SearchItemAnalysisV59_relation | SearchItemAnalysisV57_relation | SearchItemAnalysisV45 | None = None

    @model_serializer(mode='wrap')
    def serialize_version(self, handler):
        data = handler(self)
        if self.evaluation_version == 'legacy':
            data.pop('evaluation_version', None)
            data.pop('anchor_search_analysis', None)
        return data

    @model_validator_base(mode='after')
    def references(self):
        if (self.anchor_item.item_id if self.anchor_item else None) != self.intent.anchor_item_id:
            raise ValueError('Anchor item must match the resolved reference.')
        ids = [c.item.item_id for c in self.candidate_set.candidates]
        if len(ids) != len(set(ids)) or len(ids) != self.candidate_set.candidate_count:
            raise ValueError('Candidate IDs must be unique and counts must match.')
        from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
        contract = get_relation_contract(self.evaluation_version)
        if contract.evidence_module:
            if self.anchor_item is None and self.anchor_search_analysis is not None:
                raise ValueError('Category anchors have no image observations.')
            contract.evidence().packets(self)
        elif self.anchor_search_analysis is not None:
            raise ValueError('Legacy Relation does not accept Search observation inputs.')
        return self

@_preserve_class('RelationEvaluation', 'fashion_recommendation_v2.schemas.relation')
class RelationEvaluation(StrictBaseModel_base):
    item_id: str
    score: float | None = Field_base(ge=0, le=1)
    reasons: list[str] = Field_base(min_length=1)
    differences: list[str]
    uncertainties: list[str]
    evidence_fields: list[str]

@_preserve_class('RelationBatchOutput', 'fashion_recommendation_v2.schemas.relation')
class RelationBatchOutput_base(StrictBaseModel_base):
    evaluations: list[RelationEvaluation]

@_preserve_class('RelationBatchInput', 'fashion_recommendation_v2.schemas.relation')
class RelationBatchInput(StrictBaseModel_base):
    intent: RelationIntent
    anchor_item: ProductRecord | None
    items: list[ProductRecord]
    validation_feedback: list[str] = Field_base(default_factory=list)
from fashion_recommendation_v2.schemas.relation_execution import RelationItemExecutionV7

@_preserve_class('RelationRatio', 'fashion_recommendation_v2.schemas.relation')
class RelationRatio(StrictBaseModel_base):
    item_statuses_v7: dict[str, RelationItemExecutionV7] | None = None
    evaluation_version: RelationEvaluationVersion = 'legacy'
    evidence_input_sha256: str | None = None
    anchor_search_analysis: SearchItemAnalysis | SearchItemAnalysisV36 | SearchItemAnalysisV40 | SearchItemAnalysisV41 | SearchItemAnalysisV42 | SearchItemAnalysisV43 | SearchItemAnalysisV44 | SearchItemAnalysisV59_relation | SearchItemAnalysisV57_relation | SearchItemAnalysisV45 | None = None
    omitted: bool = False
    anchor_item: ProductRecord | None = None
    candidate_set_id: str
    intent: RelationIntent
    evaluations: list[RelationEvaluation]
    unevaluated_item_ids: list[str]
    warnings: list[str] = Field_base(default_factory=list)
    score_breakdowns_v3: dict[str, RelationScoreBreakdown] | None = None
    score_breakdowns_v4: dict[str, RelationScoreBreakdown] | None = None
    score_breakdowns_v5: dict[str, RelationScoreBreakdown] | None = None

    @model_serializer(mode='wrap')
    def serialize_version(self, handler):
        data = handler(self)
        if self.evaluation_version == 'legacy':
            for key in ('evaluation_version', 'evidence_input_sha256', 'anchor_search_analysis'):
                data.pop(key, None)
        if self.item_statuses_v7 is None:
            data.pop('item_statuses_v7', None)
        if self.score_breakdowns_v3 is None:
            data.pop('score_breakdowns_v3', None)
        if self.score_breakdowns_v4 is None:
            data.pop('score_breakdowns_v4', None)
        if self.score_breakdowns_v5 is None:
            data.pop('score_breakdowns_v5', None)
        return data

    @validated_once
    def validate_against(self, source: RelationAgentInput, *, require_execution=True):
        if self.evaluation_version != source.evaluation_version:
            raise ValueError('Relation evaluation versions must match.')
        if self.omitted and self.evaluations:
            raise ValueError('Omitted relationship conditions cannot have evaluations.')
        if self.candidate_set_id != source.candidate_set.candidate_set_id or self.intent != source.intent:
            raise ValueError('Relation source identifiers must match.')
        if self.anchor_item != source.anchor_item:
            raise ValueError('Anchor snapshot must be preserved.')
        candidates = {c.item.item_id: c.item for c in source.candidate_set.candidates}
        ids = [e.item_id for e in self.evaluations] + self.unevaluated_item_ids
        if len(ids) != len(set(ids)) or set(ids) != set(candidates):
            raise ValueError('Every candidate needs exactly one evaluation or unevaluated record.')
        if self.evaluation_version not in {'v7', 'v8', 'v9'} and self.item_statuses_v7 is not None:
            raise ValueError('Candidate execution outcomes require Relation v7.')
        if self.evaluation_version in {'v7', 'v8', 'v9'} and require_execution:
            records = self.item_statuses_v7
            if records is None or set(records) != set(candidates):
                raise ValueError('Relation v7 requires exactly one execution outcome per candidate.')
            done = {e.item_id for e in self.evaluations}
            if {i for i, r in records.items() if r.status == 'success'} != done:
                raise ValueError('Execution outcomes disagree with evaluations.')
        from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
        contract = get_relation_contract(self.evaluation_version)
        for field in ('score_breakdowns_v3', 'score_breakdowns_v4', 'score_breakdowns_v5'):
            if getattr(self, field) is not None and (not contract.scoring_module or field != contract.breakdown_field):
                raise ValueError('Relation score breakdown must match its evaluation version.')
        if contract.evidence_module:
            evidence = contract.evidence()
            if self.anchor_search_analysis != source.anchor_search_analysis or self.evidence_input_sha256 != evidence.evidence_input_hash(source):
                raise ValueError('Relation evidence snapshot/hash mismatch.')
            for entry in self.evaluations:
                if entry.item_id == source.intent.anchor_item_id:
                    raise ValueError('The anchor must not be evaluated as an alternative.')
                if entry.score is None and (not entry.uncertainties):
                    raise ValueError('Unknown score requires an uncertainty explanation.')
            getattr(evidence, contract.validation_name)(source, self.evaluations)
            if contract.ratio_validation_name:
                getattr(evidence, contract.ratio_validation_name)(source, self)
            return self
        issues = []
        for entry in self.evaluations:
            if entry.item_id == source.intent.anchor_item_id:
                raise ValueError('The anchor must not be evaluated as an alternative.')
            if entry.score is None and (not entry.uncertainties):
                raise ValueError('Unknown score requires an uncertainty explanation.')
            if entry.score is not None and (not entry.evidence_fields):
                raise ValueError('Scored relationships require metadata evidence.')
            metadata = candidates[entry.item_id].model_dump()
            for field in entry.evidence_fields:
                reason = 'unsupported_field' if field not in EVIDENCE_FIELDS else 'empty_field' if not metadata.get(field) else None
                if reason:
                    issues.append(dict(item_id=entry.item_id, field=field, reason=reason, available_fields=[name for name in EVIDENCE_FIELDS if metadata.get(name)]))
        if issues:
            raise RelationEvidenceError(issues)
        return self


# ---- relation_v2 ----

"""Relation v2 derived input and unchanged evaluation fields with raw capture."""
from typing import Any as Any_v2
from typing import Literal as Literal_v2
from pydantic import Field as Field_v2
from pydantic import PrivateAttr as PrivateAttr_v2
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v2
RelationBatchOutput = RelationBatchOutput_base
Dimension = Literal_v2['color', 'pattern', 'silhouette', 'length', 'details', 'style']

@_preserve_class('RelationFactV2', 'fashion_recommendation_v2.schemas.relation_v2')
class RelationFactV2_v2(StrictBaseModel_v2):
    ref: str
    value: Any_v2
    status: Literal_v2['known', 'unknown', 'conflicted', 'unavailable']
    kind: Literal_v2['metadata', 'search_observation', 'search_image_observation']

@_preserve_class('RelationObservationV2', 'fashion_recommendation_v2.schemas.relation_v2')
class RelationObservationV2(StrictBaseModel_v2):
    dimension: Dimension
    status: Literal_v2['observed', 'unknown', 'observation_unavailable', 'conflicted']
    evidence_refs: list[str]
    metadata_refs: list[str]
    unknown_refs: list[str]
    reasons: list[str]

@_preserve_class('RelationPacketV2', 'fashion_recommendation_v2.schemas.relation_v2')
class RelationPacketV2_v2(StrictBaseModel_v2):
    item_id: str | None = None
    category: str | None = None
    facts: list[RelationFactV2_v2]
    observations: list[RelationObservationV2]
    limitations: list[dict]

@_preserve_class('RelationEvidenceBatchV2', 'fashion_recommendation_v2.schemas.relation_v2')
class RelationEvidenceBatchV2(StrictBaseModel_v2):
    intent: dict
    anchor: RelationPacketV2_v2
    items: list[RelationPacketV2_v2]
    validation_feedback: list[str] = Field_v2(default_factory=list)

@_preserve_class('RelationBatchOutputV2', 'fashion_recommendation_v2.schemas.relation_v2')
class RelationBatchOutputV2(RelationBatchOutput):
    # Existing adapter captures received JSON/text before SDK validation. These
    # private attributes add no fields to the model's generation contract.
    _model_response: Any_v2 = PrivateAttr_v2(default=None)
    _model_response_text: str | None = PrivateAttr_v2(default=None)


# ---- relation_v3 ----

"""Relation v3 generates facet judgments; code owns coverage and final scores."""
from typing import Any
from pydantic import Field as Field_v3
from pydantic import PrivateAttr
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v3
from fashion_recommendation_v2.schemas.relation_scoring import Facet
from fashion_recommendation_v2.schemas.relation_scoring import RelationCriterionJudgment as RelationCriterionJudgment_v3
RelationPacketV2_v3 = RelationPacketV2_v2

@_preserve_class('RelationFacetSourcesV3', 'fashion_recommendation_v2.schemas.relation_v3')
class RelationFacetSourcesV3(StrictBaseModel_v3):
    facet: Facet
    evidence_refs: list[str]
    not_applicable_evidence_refs: list[str]

@_preserve_class('RelationPacketV3', 'fashion_recommendation_v2.schemas.relation_v3')
class RelationPacketV3(RelationPacketV2_v3):
    facet_evidence: list[RelationFacetSourcesV3]

@_preserve_class('RelationEvidenceBatchV3', 'fashion_recommendation_v2.schemas.relation_v3')
class RelationEvidenceBatchV3_v3(StrictBaseModel_v3):
    intent: dict
    anchor: RelationPacketV3
    items: list[RelationPacketV3]
    validation_feedback: list[str] = Field_v3(default_factory=list)

@_preserve_class('RelationItemJudgmentsV3', 'fashion_recommendation_v2.schemas.relation_v3')
class RelationItemJudgmentsV3_v3(StrictBaseModel_v3):
    item_id: str
    criteria: list[RelationCriterionJudgment_v3]
    reasons: list[str] = Field_v3(min_length=1)
    differences: list[str]
    uncertainties: list[str]

@_preserve_class('RelationBatchOutputV3', 'fashion_recommendation_v2.schemas.relation_v3')
class RelationBatchOutputV3_v3(StrictBaseModel_v3):
    evaluations: list[RelationItemJudgmentsV3_v3]
    _model_response: Any = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)


# ---- relation_v5 ----

"""v5 generation adds only auditable facet-specific metadata fallback reasons."""
RelationEvidenceBatchV3 = RelationEvidenceBatchV3_v3
RelationBatchOutputV3 = RelationBatchOutputV3_v3
RelationItemJudgmentsV3 = RelationItemJudgmentsV3_v3
from fashion_recommendation_v2.schemas.relation_scoring import MetadataFallbackV5
from fashion_recommendation_v2.schemas.relation_scoring import fallback_error
from fashion_recommendation_v2.schemas.relation_scoring import RelationFacetJudgment
from fashion_recommendation_v2.schemas.relation_scoring import RelationCriterionJudgment
from typing import Literal
from typing import Union
from pydantic import Field as Field_v5
from pydantic import create_model
from pydantic import model_validator

@_preserve_class('RelationEvidenceBatchV5', 'fashion_recommendation_v2.schemas.relation_v5')
class RelationEvidenceBatchV5(RelationEvidenceBatchV3):
    pass

@_preserve_class('RelationItemJudgmentsV5', 'fashion_recommendation_v2.schemas.relation_v5')
class RelationItemJudgmentsV5(RelationItemJudgmentsV3):
    metadata_fallbacks: list[MetadataFallbackV5]

@_preserve_class('RelationBatchOutputV5', 'fashion_recommendation_v2.schemas.relation_v5')
class RelationBatchOutputV5_v5(RelationBatchOutputV3):
    evaluations: list[RelationItemJudgmentsV5]

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.relation_v5')
def output_schema_v5(payload, criteria):
    """Bind exact criterion/facet names and per-side refs before generation/repair."""
    return bound_output_schema_v5(payload, criteria)

@_preserve_function('bound_output_schema', 'fashion_recommendation_v2.schemas.relation_v5')
def bound_output_schema_v5(payload, criteria, *, refs_for=None, version="V5", output_base=RelationBatchOutputV5_v5, fallback_facets=None):
    """Shared exact inventory and citation syntax; each input contract supplies refs."""
    if refs_for is None:

        def refs_for(packet, facet):
            row = next((r for r in packet.facet_evidence if r.facet == facet))
            return [*row.evidence_refs, *row.not_applicable_evidence_refs]

    def ref_field(refs):
        refs = tuple(dict.fromkeys(refs))
        return (list[Literal[refs]], Field_v5(...)) if refs else (list[str], Field_v5(..., max_length=0))

    def fallback_validator(item_id):

        @model_validator(mode='before')
        def check(cls, data):
            if not isinstance(data, dict):
                return data
            seen = set()
            for row in data.get('metadata_fallbacks', []):
                if not isinstance(row, dict):
                    continue
                facet, side = (row.get('facet'), row.get('side'))
                if facet not in fallback_facets:
                    raise fallback_error(item_id, facet, side, 'facet is metadata-only or not evaluated for this relation.', 'Remove this fallback entry; record evidence in facet reason and information gaps in uncertainties.')
                if (facet, side) in seen:
                    raise fallback_error(item_id, facet, side, 'Duplicate metadata fallback explanation.', 'Keep one entry per facet/side.')
                seen.add((facet, side))
            return data
        return check
    items = []
    for index, packet in enumerate(payload.items):
        criterion_models = []
        for name, facets in criteria.items():
            models = []
            for facet in facets:
                ar = refs_for(payload.anchor, facet)
                cr = refs_for(packet, facet)
                models.append(create_model(f'Facet{version}_{index}_{facet}', __base__=RelationFacetJudgment, facet=(Literal[facet], ...), anchor_evidence=ref_field(ar), candidate_evidence=ref_field(cr)))
            criterion_models.append(create_model(f'Criterion{version}_{index}_{name}', __base__=RelationCriterionJudgment, criterion=(Literal[name], ...), facets=(list[Union[tuple(models)]], Field_v5(..., min_length=len(models), max_length=len(models)))))
        fallback_fields = {}
        if fallback_facets is not None:
            allowed = tuple(sorted(fallback_facets))
            fallback_model = create_model(f'MetadataFallback{version}_{index}', __base__=MetadataFallbackV5, facet=(Literal[allowed], ...)) if allowed else MetadataFallbackV5
            fallback_fields['metadata_fallbacks'] = (list[fallback_model], Field_v5(...) if allowed else Field_v5(..., max_length=0))
        items.append(create_model(f'ItemJudgments{version}_{index}', __base__=RelationItemJudgmentsV5, **fallback_fields, __validators__={'fallback_inventory': fallback_validator(packet.item_id)} if fallback_facets is not None else {}, item_id=(Literal[packet.item_id], ...), criteria=(list[Union[tuple(criterion_models)]], Field_v5(..., min_length=len(criterion_models), max_length=len(criterion_models)))))
    return create_model(f'RelationBatchOutput{version}', __base__=output_base, evaluations=(list[Union[tuple(items)]], Field_v5(..., min_length=len(items), max_length=len(items))))


# ---- relation_v6 ----

"""v6 passes Search keys and observations without assigning them to facets."""
from pydantic import Field
from fashion_recommendation_v2.schemas.relation_scoring import METADATA_ONLY_RELATION_FACETS
from fashion_recommendation_v2.schemas.base import StrictBaseModel
RelationFactV2 = RelationFactV2_v2
RelationPacketV2 = RelationPacketV2_v2
RelationBatchOutputV5 = RelationBatchOutputV5_v5
bound_output_schema = bound_output_schema_v5

@_preserve_class('RelationFactV6', 'fashion_recommendation_v2.schemas.relation_v6')
class RelationFactV6(RelationFactV2):
    attribute: str
    attribute_key: str

@_preserve_class('RelationPacketV6', 'fashion_recommendation_v2.schemas.relation_v6')
class RelationPacketV6(RelationPacketV2):
    image_url: str | None = None
    facts: list[RelationFactV6]

@_preserve_class('RelationEvidenceBatchV6', 'fashion_recommendation_v2.schemas.relation_v6')
class RelationEvidenceBatchV6(StrictBaseModel):
    intent: dict
    anchor: RelationPacketV6
    items: list[RelationPacketV6]
    validation_feedback: list[str] = Field(default_factory=list)

@_preserve_class('RelationBatchOutputV6', 'fashion_recommendation_v2.schemas.relation_v6')
# The judgment/score/fallback contract is unchanged; do not copy it per version.
class RelationBatchOutputV6(RelationBatchOutputV5):
    pass

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.relation_v6')
def output_schema(payload, criteria):
    return bound_output_schema(payload, criteria, refs_for=lambda packet, facet: [f.ref for f in packet.facts], version='V6', output_base=RelationBatchOutputV6, fallback_facets={f for facets in criteria.values() for f in facets} - METADATA_ONLY_RELATION_FACETS)


# ---- relation_v9 ----

"""v9 binds the compatibility inventory while retaining the observation contract."""
RelationEvidenceBatchV6_relation_v9 = RelationEvidenceBatchV6
RelationBatchOutputV6_relation_v9 = RelationBatchOutputV6
bound_output_schema_relation_v9 = bound_output_schema_v5
# v9 permits saved material/season observations.
METADATA_ONLY_RELATION_FACETS_relation_v9 = frozenset()

@_preserve_class('RelationBatchOutputV9', 'fashion_recommendation_v2.schemas.relation_v9')
class RelationBatchOutputV9_relation_v9(RelationBatchOutputV6_relation_v9):
    pass

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.relation_v9')
def output_schema_relation_v9(payload, criteria):
    return bound_output_schema_relation_v9(payload, criteria, refs_for=lambda packet, facet: [f.ref for f in packet.facts], version='V9', output_base=RelationBatchOutputV9_relation_v9, fallback_facets={f for facets in criteria.values() for f in facets} - METADATA_ONLY_RELATION_FACETS_relation_v9)
