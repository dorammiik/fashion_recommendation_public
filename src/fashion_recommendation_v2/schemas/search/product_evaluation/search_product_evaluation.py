"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- search_product_evaluation_v36 ----

"""v36 source-separated observations and admission; historical contracts stay intact."""
from typing import Literal as Literal_v36
from pydantic import Field as Field_v36
from pydantic import PrivateAttr
from pydantic import create_model as create_model_v36
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v36
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.schemas.stylist import NonBlankText_base as NonBlankText_v36
from fashion_recommendation_v2.schemas.stylist import Alternatives as Alternatives_v36
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy as ThumbnailObservationV1
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v36
AttributeName = Literal_v36['category', 'product_type', 'color', 'pattern', 'fit', 'gender', 'size', 'strength', 'sleeve_length', 'sleeve', 'material', 'theme', 'occasion', 'brand', 'garment_care', 'season', 'detail']
METADATA_ONLY = frozenset({'gender', 'size', 'strength', 'brand', 'garment_care', 'season'})
ConsistencyStatus = Literal_v36['consistent', 'partially_consistent', 'inconsistent', 'visually_indeterminate', 'metadata_missing', 'not_applicable', 'observation_unavailable']
ObservedConsistencyStatus = Literal_v36['consistent', 'partially_consistent', 'inconsistent', 'visually_indeterminate', 'metadata_missing', 'not_applicable']
AttributeValue = NonBlankText_v36 | Alternatives_v36 | StylistDetailValue | None

@_preserve_class('MetadataObservation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class MetadataObservation(StrictBaseModel_v36):
    value: AttributeValue
    evidence_fields: list[str]
    evidence: list[str]

@_preserve_class('ImageObservation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class ImageObservation(StrictBaseModel_v36):
    value: AttributeValue
    evidence: list[str]

@_preserve_class('ObservedConsistency', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class ObservedConsistency(StrictBaseModel_v36):
    status: ObservedConsistencyStatus
    reason: str = Field_v36(min_length=1)

@_preserve_class('Consistency', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class Consistency(StrictBaseModel_v36):
    status: ConsistencyStatus
    reason: str = Field_v36(min_length=1)

@_preserve_class('AttributeDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class AttributeDraft(StrictBaseModel_v36):
    attribute: AttributeName
    metadata: MetadataObservation
    image_observation: ImageObservation | None
    metadata_image_consistency: ObservedConsistency

    @model_validator(mode='after')
    def canonical_gender(self):
        if self.attribute == 'gender' and self.metadata.value not in (None, 'men', 'women', 'unisex', 'unknown'):
            raise ValueError('gender requires the canonical audience enum.')
        return self

@_preserve_class('CodeValidation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class CodeValidation(StrictBaseModel_v36):
    status: Literal_v36['passed', 'failed']
    errors: list[str] = Field_v36(default_factory=list)

@_preserve_class('AttributeValidation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class AttributeValidation(CodeValidation):
    validated_sources: list[Literal_v36['metadata', 'image_observation']] = Field_v36(default_factory=list)

@_preserve_class('AttributeObservation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class AttributeObservation(AttributeDraft):
    metadata_image_consistency: Consistency
    code_validation: AttributeValidation

@_preserve_class('JudgmentDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class JudgmentDraft_v36(StrictBaseModel_v36):
    requirement_id: str
    status: Literal_v36['met', 'mostly_met', 'partial', 'unmet', 'unknown']
    attribute_keys: list[str]
    reason: str = Field_v36(min_length=1)
    uncertainty_reason: Literal_v36['none', 'insufficient_evidence', 'unresolved_conflict']

@_preserve_class('AlternativeDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class AlternativeDraft_v36(JudgmentDraft_v36):
    value: str
    status: Literal_v36['met', 'unmet', 'unknown']

@_preserve_class('Judgment', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class Judgment(RequirementJudgment):
    attribute_keys: list[str]
    uncertainty_reason: Literal_v36['none', 'insufficient_evidence', 'unresolved_conflict']

@_preserve_class('Alternative', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class Alternative_v36(Judgment):
    value: str
    status: Literal_v36['met', 'unmet', 'unknown']

@_preserve_class('HardFinding', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class HardFinding_v36(StrictBaseModel_v36):
    requirement_id: str
    finding: Literal_v36['matched', 'clear_mismatch', 'insufficient_evidence']
    evidence: str = Field_v36(min_length=1)

@_preserve_class('AdmissionJudgment', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class AdmissionJudgment(StrictBaseModel_v36):
    photo_pass: bool
    exposure_pass: bool
    overall_pass: bool
    reason: str = Field_v36(min_length=1)

@_preserve_class('ThumbnailObservationV36', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class ThumbnailObservationV36(ThumbnailObservationV1):

    @model_validator(mode='after')
    def person_support(self):
        if self.photo_type == 'person' and self.support != 'unknown':
            raise ValueError('Person photographs have no display support.')
        return self

@_preserve_class('ProductDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class ProductDraft_v36(StrictBaseModel_v36):
    attributes: list[AttributeDraft]
    judgments: list[JudgmentDraft_v36]
    alternative_judgments: list[AlternativeDraft_v36]
    hard_condition_findings: list[HardFinding_v36]
    thumbnail_observation_v8: ThumbnailObservationV36
    exposure_suitability: ExposureSuitability
    admission_judgment: AdmissionJudgment

@_preserve_class('AdmissionChecks', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class AdmissionChecks(StrictBaseModel_v36):
    evaluation_valid: bool
    image_available: bool
    hard_conditions_pass: bool
    photo_pass: bool
    exposure_pass: bool
    childrenswear_pass: bool
    overall_pass: bool

@_preserve_class('SearchItemAnalysisV36', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class SearchItemAnalysisV36_v36(StrictBaseModel_v36):
    evaluation_policy: Literal_v36['v36'] = 'v36'
    item_id: str
    image_url: str
    attributes: list[AttributeObservation]
    judgments: list[Judgment]
    alternative_judgments: list[Alternative_v36]
    hard_condition_findings: list[HardFinding_v36]
    thumbnail_observation_v8: ThumbnailObservationV36
    exposure_suitability: ExposureSuitability
    admission_judgment: AdmissionJudgment
    admission_checks: AdmissionChecks
    code_validation: CodeValidation
    semantic_review: dict | None = None

    def passes(self, hard_ids):
        by_id = {j.requirement_id: j.status for j in self.judgments}
        return self.admission_checks.overall_pass and self.code_validation.status == 'passed' and all((by_id.get(k) == 'met' for k in hard_ids))

    @property
    def gender(self):
        return next((a.metadata.value for a in self.attributes if a.attribute == 'gender' and a.code_validation.status == 'passed'), None) or 'unknown'

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class ProductBatch_v36(StrictBaseModel_v36):
    items: list[SearchItemAnalysisV36_v36]
    _slot_errors: dict = PrivateAttr(default_factory=dict)

@_preserve_class('VisualSlotsV36', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
class VisualSlotsV36_v36(StrictBaseModel_v36):
    _slot_errors: dict = PrivateAttr(default_factory=dict)

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
def output_schema_v36(count, context):
    return preserve_response_schema_v36(create_model_v36(f'SearchVisualSlotsV36_{count}', __base__=VisualSlotsV36_v36, **{f'item_{i:02d}': (ProductDraft_v36 if i <= count else type(None), ...) for i in range(1, 11)}))


# ---- search_product_evaluation_v40 ----

"""v40 graded hard admission, preserving source-separated v36 field layout."""
from typing import Literal as Literal_v40
from pydantic import create_model as create_model_v40
PreviousDraft = ProductDraft_v36
JudgmentDraft = JudgmentDraft_v36
SearchItemAnalysisV36 = SearchItemAnalysisV36_v36
PreviousFinding = HardFinding_v36
PreviousBatch_v40 = ProductBatch_v36
VisualSlotsV36 = VisualSlotsV36_v36
PreviousAlternative = Alternative_v36
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v40
HARD_PASS_STATUSES_v40 = frozenset({'met', 'mostly_met'})
HARD_FINDING_STATUSES_v40 = {'matched': frozenset({'met'}), 'mostly_matched': frozenset({'mostly_met'}), 'partial_match': frozenset({'partial'}), 'clear_mismatch': frozenset({'unmet'}), 'insufficient_evidence': frozenset({'unknown'})}

@_preserve_class('HardFinding', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
class HardFinding_v40(PreviousFinding):
    finding: Literal_v40['matched', 'mostly_matched', 'partial_match', 'clear_mismatch', 'insufficient_evidence']

@_preserve_class('AlternativeDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
class AlternativeDraft_v40(JudgmentDraft):
    value: str

@_preserve_class('Alternative', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
class Alternative_v40(PreviousAlternative):
    status: Literal_v40['met', 'mostly_met', 'partial', 'unmet', 'unknown']

@_preserve_class('ProductDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
class ProductDraft_v40(PreviousDraft):
    alternative_judgments: list[AlternativeDraft_v40]
    hard_condition_findings: list[HardFinding_v40]

@_preserve_class('SearchItemAnalysisV40', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
class SearchItemAnalysisV40_v40(SearchItemAnalysisV36):
    evaluation_policy: Literal_v40['v40'] = 'v40'
    alternative_judgments: list[Alternative_v40]
    hard_condition_findings: list[HardFinding_v40]

    def passes(self, hard_ids):
        by_id = {j.requirement_id: j.status for j in self.judgments}
        return self.admission_checks.overall_pass and self.code_validation.status == 'passed' and all((by_id.get(k) in HARD_PASS_STATUSES_v40 for k in hard_ids))

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
class ProductBatch_v40(PreviousBatch_v40):
    items: list[SearchItemAnalysisV40_v40]

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
def output_schema_v40(count, context):
    # Keep operation names: execution limits/model routing remain unchanged.
    return preserve_response_schema_v40(create_model_v40(f'SearchVisualSlotsV36_{count}', __base__=VisualSlotsV36, **{f'item_{i:02d}': (ProductDraft_v40 if i <= count else type(None), ...) for i in range(1, 11)}))


# ---- search_product_evaluation_v41 ----

"""v41 semantic revision; preserve v40 wire fields and graded admission."""
from typing import Literal as Literal_v41
ProductDraft_v41 = ProductDraft_v40
AlternativeDraft_v41 = AlternativeDraft_v40
Alternative = Alternative_v40
HardFinding = HardFinding_v40
HARD_PASS_STATUSES_v41 = HARD_PASS_STATUSES_v40
HARD_FINDING_STATUSES_v41 = HARD_FINDING_STATUSES_v40
SearchItemAnalysisV40 = SearchItemAnalysisV40_v40
PreviousBatch_v41 = ProductBatch_v40
output_schema_v41 = output_schema_v40

@_preserve_class('SearchItemAnalysisV41', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v41')
class SearchItemAnalysisV41_v41(SearchItemAnalysisV40):
    evaluation_policy: Literal_v41['v41'] = 'v41'

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v41')
class ProductBatch_v41(PreviousBatch_v41):
    items: list[SearchItemAnalysisV41_v41]


# ---- search_product_evaluation_v42 ----

"""Fixed observation slots for v42; response keys are derived from validated requirements."""
from typing import Literal as Literal_v42
from typing import get_args
from pydantic import create_model as create_model_v42
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.stylist import NonBlankText_base as NonBlankText
from fashion_recommendation_v2.schemas.stylist import Alternatives
base_v42 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
ProductDraft = ProductDraft_v40
AlternativeDraft_v42 = AlternativeDraft_v40
HARD_PASS_STATUSES_v42 = HARD_PASS_STATUSES_v40
HARD_FINDING_STATUSES_v42 = HARD_FINDING_STATUSES_v40
SearchItemAnalysisV41 = SearchItemAnalysisV41_v41
PreviousBatch = ProductBatch_v41
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v42

@_preserve_class('Metadata', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class Metadata(StrictBaseModel):
    value: NonBlankText | Alternatives | None
    evidence_fields: list[str]
    evidence: list[str]

@_preserve_class('Image', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class Image(StrictBaseModel):
    value: NonBlankText | Alternatives | None
    evidence: list[str]

@_preserve_class('Observation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class Observation(StrictBaseModel):
    metadata: Metadata
    image_observation: Image | None
    metadata_image_consistency: base_v42.ObservedConsistency

@_preserve_class('ExtraDetail', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class ExtraDetail(Observation):
    key: NonBlankText = Field(description='One detail key shared by both sources; never repeat a fixed detail key.')

@_preserve_class('DerivedDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class DerivedDraft(base_v42.AttributeDraft):
    fixed_attribute_key: str

@_preserve_class('DerivedObservation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class DerivedObservation(base_v42.AttributeObservation):
    fixed_attribute_key: str

@_preserve_class('SearchItemAnalysisV42', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class SearchItemAnalysisV42(SearchItemAnalysisV41):
    evaluation_policy: Literal_v42['v42'] = 'v42'
    attributes: list[DerivedObservation]

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
class ProductBatch_v42(PreviousBatch):
    items: list[SearchItemAnalysisV42]

@_preserve_function('fixed_keys', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
def fixed_keys_v42(requirements):
    """Use source keys verbatim; no alias rewriting or requested values as observations."""
    reqs = requirements.requirements if hasattr(requirements, 'requirements') else requirements.get('requirements', [])
    keys = list((k for k in get_args(base_v42.AttributeName) if k not in {'detail', 'sleeve'}))
    for r in reqs:
        attr = r.attribute if hasattr(r, 'attribute') else r['attribute']
        value = r.value if hasattr(r, 'value') else r['value']
        if attr == 'price':
            continue
        if attr == 'avoid_product_type':
            attr = 'product_type'
        if attr == 'detail':
            # Older scalar/list detail conditions have no semantic key; preserve them
            # under a stable condition ID rather than guessing or rewriting the request.
            key = value.key if hasattr(value, 'key') else value['key'] if isinstance(value, dict) else r.requirement_id if hasattr(r, 'requirement_id') else r['requirement_id']
            attr = 'detail.' + key
        if attr not in keys:
            keys.append(attr)
    return tuple(keys)

@_preserve_function('product_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
def product_schema_v42(requirements):
    fields = {}
    for key in fixed_keys_v42(requirements):
        row = Observation
        if key in base_v42.METADATA_ONLY:
            row = create_model_v42('MetadataOnlyObservation', __base__=Observation, image_observation=(type(None), ...))
        fields[key] = (row, ...)
    slots = create_model_v42('FixedProductAttributesV42', __base__=StrictBaseModel, **fields)
    return create_model_v42('ProductDraftV42', __base__=ProductDraft, attributes=(slots, ...), additional_details=(list[ExtraDetail], ...))

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
def output_schema_v42(count, context):
    product = product_schema_v42(context['resolved_requirements'])
    return preserve_response_schema_v42(create_model_v42(f'SearchVisualSlotsV36_{count}', __base__=base_v42.VisualSlotsV36, **{f'item_{i:02d}': (product if i <= count else type(None), ...) for i in range(1, 11)}))


# ---- search_product_evaluation_v43 ----

"""v43: condition references use the same code-owned inventory as observations."""
from typing import Literal as Literal_v43
from pydantic import create_model
base = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
previous_v43 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
AlternativeDraft = AlternativeDraft_v40
HARD_PASS_STATUSES_v43 = HARD_PASS_STATUSES_v40
HARD_FINDING_STATUSES_v43 = HARD_FINDING_STATUSES_v40
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema
fixed_keys_v43 = previous_v43.fixed_keys

@_preserve_class('SearchItemAnalysisV43', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v43')
class SearchItemAnalysisV43(previous_v43.SearchItemAnalysisV42):
    evaluation_policy: Literal_v43['v43'] = 'v43'

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v43')
class ProductBatch_v43(previous_v43.ProductBatch):
    items: list[SearchItemAnalysisV43]

@_preserve_function('product_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v43')
def product_schema_v43(requirements):
    reference = Literal_v43[fixed_keys_v43(requirements)]
    judgment = create_model('JudgmentDraftV43', __base__=base.JudgmentDraft, attribute_keys=(list[reference], ...))
    alternative = create_model('AlternativeDraftV43', __base__=AlternativeDraft, attribute_keys=(list[reference], ...))
    return create_model('ProductDraftV43', __base__=previous_v43.product_schema(requirements), judgments=(list[judgment], ...), alternative_judgments=(list[alternative], ...))

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v43')
def output_schema_v43(count, context):
    product = product_schema_v43(context['resolved_requirements'])
    return preserve_response_schema(create_model(f'SearchVisualSlotsV36_{count}', __base__=base.VisualSlotsV36, **{f'item_{i:02d}': (product if i <= count else type(None), ...) for i in range(1, 11)}))


# ---- search_product_evaluation_v44 ----

"""v44 retains v43 bounded references; each image call contains one product."""
from typing import Literal as Literal_v44
previous_v44 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v43')
HARD_PASS_STATUSES_v44 = HARD_PASS_STATUSES_v40
HARD_FINDING_STATUSES_v44 = HARD_FINDING_STATUSES_v40
fixed_keys_v44 = previous_v44.fixed_keys
product_schema_v44 = previous_v44.product_schema

@_preserve_class('SearchItemAnalysisV44', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v44')
class SearchItemAnalysisV44(previous_v44.SearchItemAnalysisV43):
    evaluation_policy: Literal_v44['v44'] = 'v44'

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v44')
class ProductBatch_v44(previous_v44.ProductBatch):
    items: list[SearchItemAnalysisV44]

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v44')
def output_schema_v44(count, context):
    if count != 1:
        raise ValueError('Search v44 image evaluation requires exactly one product per call.')
    return previous_v44.output_schema(count, context)


# ---- search_product_evaluation_v45 ----

"""v45 changes semantics only; preserve the bounded single-product response contract."""
from typing import Literal
previous = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v44')
HARD_PASS_STATUSES = HARD_PASS_STATUSES_v40
HARD_FINDING_STATUSES = HARD_FINDING_STATUSES_v40
fixed_keys = previous.fixed_keys
product_schema = previous.product_schema
output_schema = previous.output_schema

@_preserve_class('SearchItemAnalysisV45', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v45')
class SearchItemAnalysisV45(previous.SearchItemAnalysisV44):
    evaluation_policy: Literal['v45'] = 'v45'

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v45')
class ProductBatch(previous.ProductBatch):
    items: list[SearchItemAnalysisV45]


# ---- search_product_evaluation_v57 ----

"""v57 semantics with the existing bounded, source-separated response shape."""
from typing import Literal as Literal_search_product_evaluation_v57
previous_search_product_evaluation_v57 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v45')

@_preserve_function('fixed_keys', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v57')
def fixed_keys_search_product_evaluation_v57(requirements):
    keys = ['sleeve' if k == 'sleeve_length' else k for k in previous_search_product_evaluation_v57.fixed_keys(requirements)]
    return tuple(dict.fromkeys([*keys, 'detail.length', 'detail.neckline']))
from pydantic import create_model as create_model_search_product_evaluation_v57
base_search_product_evaluation_v57 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
Observation_search_product_evaluation_v57 = Observation
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_search_product_evaluation_v57
METADATA_ONLY_search_product_evaluation_v57 = base_search_product_evaluation_v57.METADATA_ONLY - {'season'}

@_preserve_function('product_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v57')
def product_schema_search_product_evaluation_v57(requirements):
    from fashion_recommendation_v2.schemas.base import StrictBaseModel
    AlternativeDraft = AlternativeDraft_v40
    product = previous_search_product_evaluation_v57.product_schema(requirements)
    fields = {}
    for key in fixed_keys_search_product_evaluation_v57(requirements):
        row = Observation_search_product_evaluation_v57
        if key in METADATA_ONLY_search_product_evaluation_v57:
            row = create_model_search_product_evaluation_v57('MetadataOnlyObservationV57', __base__=Observation_search_product_evaluation_v57, image_observation=(type(None), ...))
        fields[key] = (row, ...)
    attributes = create_model_search_product_evaluation_v57('FixedProductAttributesV57', __base__=StrictBaseModel, **fields)
    reference = Literal_search_product_evaluation_v57[fixed_keys_search_product_evaluation_v57(requirements)]
    judgment = create_model_search_product_evaluation_v57('JudgmentDraftV57', __base__=base_search_product_evaluation_v57.JudgmentDraft, attribute_keys=(list[reference], ...))
    alternative = create_model_search_product_evaluation_v57('AlternativeDraftV57', __base__=AlternativeDraft, attribute_keys=(list[reference], ...))
    return create_model_search_product_evaluation_v57('ProductDraftV57', __base__=product, attributes=(attributes, ...), judgments=(list[judgment], ...), alternative_judgments=(list[alternative], ...))

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v57')
def output_schema_search_product_evaluation_v57(count, context):
    if count != 1:
        raise ValueError('Search v57 image evaluation requires exactly one product per call.')
    product = product_schema_search_product_evaluation_v57(context['resolved_requirements'])
    return preserve_response_schema_search_product_evaluation_v57(create_model_search_product_evaluation_v57(f'SearchVisualSlotsV57_{count}', __base__=base_search_product_evaluation_v57.VisualSlotsV36, **{f'item_{i:02d}': (product if i <= count else type(None), ...) for i in range(1, 11)}))

@_preserve_class('SearchItemAnalysisV57', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v57')
class SearchItemAnalysisV57_search_product_evaluation_v57(previous_search_product_evaluation_v57.SearchItemAnalysisV45):
    evaluation_policy: Literal_search_product_evaluation_v57['v57'] = 'v57'

@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v57')
class ProductBatch_search_product_evaluation_v57(previous_search_product_evaluation_v57.ProductBatch):
    items: list[SearchItemAnalysisV57_search_product_evaluation_v57]


# ---- search_product_evaluation_v59 ----

"""Reuse v57 native response shape; persist the distinct v59 admission policy."""
from typing import Literal as Literal_search_product_evaluation_v59
Literal_search_product_evaluation_v59 = Literal_search_product_evaluation_v57
METADATA_ONLY_search_product_evaluation_v59 = METADATA_ONLY_search_product_evaluation_v57
Observation_search_product_evaluation_v59 = Observation_search_product_evaluation_v57
ProductBatch_search_product_evaluation_v59 = ProductBatch_search_product_evaluation_v57
SearchItemAnalysisV57_search_product_evaluation_v59 = SearchItemAnalysisV57_search_product_evaluation_v57
base_search_product_evaluation_v59 = base_search_product_evaluation_v57
create_model_search_product_evaluation_v59 = create_model_search_product_evaluation_v57
fixed_keys_search_product_evaluation_v59 = fixed_keys_search_product_evaluation_v57
output_schema_search_product_evaluation_v59 = output_schema_search_product_evaluation_v57
preserve_response_schema_search_product_evaluation_v59 = preserve_response_schema_search_product_evaluation_v57
previous_search_product_evaluation_v59 = previous_search_product_evaluation_v57
product_schema_search_product_evaluation_v59 = product_schema_search_product_evaluation_v57
previous_search_product_evaluation_v59 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v57')

@_preserve_class('SearchItemAnalysisV59', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v59')
class SearchItemAnalysisV59_search_product_evaluation_v59(previous_search_product_evaluation_v59.SearchItemAnalysisV57):
    evaluation_policy: Literal_search_product_evaluation_v59['v59'] = 'v59'

# noqa: F401,F403
@_preserve_class('ProductBatch', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v59')
class ProductBatch_search_product_evaluation_v59(previous_search_product_evaluation_v59.ProductBatch):
    items: list[SearchItemAnalysisV59_search_product_evaluation_v59]


# ---- search_product_evaluation_legacy ----

"""schemas.search.product_evaluation.search_product_evaluation_legacy: definitions relocated without semantic changes."""
from fashion_recommendation_v2.schemas.product_evidence import DiversityFeature
from fashion_recommendation_v2.schemas.product_evidence import EvidenceConflict
from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability as ExposureSuitability_legacy
from pydantic import Field as Field_legacy
from pydantic import model_validator as model_validator_legacy
from fashion_recommendation_v2.schemas.product_evidence import ImageEvidence
from typing import Literal as Literal_legacy
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord as ProductRecord_legacy
from fashion_recommendation_v2.schemas.product_evidence import ProductFactV26 as ProductFactV26_legacy
from fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation import RelationVisualObservation
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment as RequirementJudgment_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_legacy
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservation
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationDraft
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV8_legacy
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationV5 as VisualConfirmationV5_legacy
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConsistencyAuditV5
from pydantic import model_serializer
from pydantic import model_validator as model_validator_legacy

@_preserve_class('ObservedValuesV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class ObservedValuesV8(StrictBaseModel_legacy):
    category: str | list[str]
    color: str | list[str]
    pattern: str | list[str]
    fit: str | list[str]
    gender: Literal_legacy['men', 'women', 'unisex', 'unknown']
    material: str | list[str]
    theme: str | list[str]
    occasion: str | list[str]

@_preserve_class('AlternativeJudgmentV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class AlternativeJudgmentV8_legacy(StrictBaseModel_legacy):
    requirement_id: str
    value: str
    status: Literal_legacy['met', 'unmet', 'unknown']
    evidence_fields: list[str]
    evidence: list[str]
    image_evidence: list[ImageEvidence]

@_preserve_class('SearchItemAnalysis', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemAnalysis(StrictBaseModel_legacy):
    validation_v29: dict | None = None
    product_facts_v26: list[ProductFactV26_legacy] | None = None
    relation_observation_v0: RelationVisualObservation | None = None
    ranking_thumbnail_observation_v5: ThumbnailObservationV1_legacy | None = None
    visual_confirmation_v5: VisualConfirmationV5_legacy | None = None
    visual_consistency_v5: VisualConsistencyAuditV5 | None = None
    ranking_visual_error_v5: str | None = None
    exposure_suitability: ExposureSuitability_legacy | None = None
    evaluation_policy: Literal_legacy['v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35'] | None = None
    thumbnail_observation_v8: ThumbnailObservationV1_legacy | ThumbnailObservationV8_legacy | None = None
    observed_values: ObservedValuesV8 | None = None
    alternative_judgments: list[AlternativeJudgmentV8_legacy] = Field_legacy(default_factory=list)
    thumbnail_observation: ThumbnailObservation | None = None
    item_id: str
    image_url: str | None = None
    attributes: list[DiversityFeature]
    judgments: list[RequirementJudgment_legacy]
    conflicts: list[EvidenceConflict]
    relavance_quality: Literal_legacy['high', 'medium', 'low']
    thum_quality: Literal_legacy['high', 'medium', 'low']
    thumbnail_kind: Literal_legacy['person', 'product_only', 'unknown']
    relevance_evidence: str = Field_legacy(min_length=1)
    thumbnail_evidence: str = Field_legacy(min_length=1)

    @model_serializer(mode='wrap')
    def serialize_version(self, handler):
        data = handler(self)
        if self.validation_v29 is None:
            data.pop('validation_v29', None)
        if self.product_facts_v26 is None:
            data.pop('product_facts_v26', None)
        if self.relation_observation_v0 is None:
            data.pop('relation_observation_v0', None)
        for key in ('ranking_thumbnail_observation_v5', 'visual_confirmation_v5', 'visual_consistency_v5', 'ranking_visual_error_v5'):
            if getattr(self, key) is None:
                data.pop(key, None)
        if self.exposure_suitability is None:
            data.pop("exposure_suitability", None)
        if self.evaluation_policy not in {'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35'}:
            for key in ('evaluation_policy', 'thumbnail_observation_v8', 'observed_values', 'alternative_judgments'):
                data.pop(key, None)
        if self.evaluation_policy in {'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35'}:
            data.pop('observed_values', None)
        return data

    @property
    def known_attributes(self):
        return [a for a in self.attributes if a.value != 'unknown'] if self.evaluation_policy in {'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35'} else self.attributes

    @model_validator_legacy(mode='after')
    def validate_attributes(self):
        allowed = {'category', 'color', 'pattern', 'fit', 'gender', 'material', 'theme', 'occasion'}
        if any((a.attribute not in allowed for a in self.attributes)):
            raise ValueError('Search v2 supports exactly eight attribute types.')
        genders = [a for a in self.known_attributes if a.attribute == 'gender']
        if len(genders) > 1 or (genders and genders[0].value not in ('men', 'women', 'unisex')):
            raise ValueError('Gender must be a single canonical men/women/unisex value, or omitted.')
        return self

    @property
    def gender(self):
        if any((c.attribute == 'gender' for c in self.conflicts)):
            return 'unknown'
        return next((a.value for a in self.attributes if a.attribute == 'gender'), 'unknown')

    def passes(self, hard_ids):
        if self.evaluation_policy in {'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35'}:
            by_id = {j.requirement_id: j.status for j in self.judgments}
            return bool(self.image_url) and self.thumbnail_observation_v8 is not None and self.thumbnail_observation_v8.passes() and (self.relavance_quality in {'high', 'medium'}) and all((by_id.get(key) == 'met' for key in hard_ids))
        observation_matches = self.thumbnail_observation is None or (self.thumbnail_kind, self.thum_quality) == self.thumbnail_observation.quality()
        return observation_matches and bool(self.image_url) and (self.relavance_quality in {'high', 'medium'}) and (self.thumbnail_kind == 'person' and self.thum_quality in {'high', 'medium'} or (self.thumbnail_kind == 'product_only' and self.thum_quality == 'high')) and (not any((j.requirement_id in hard_ids and j.status == 'unmet' for j in self.judgments)))

@_preserve_class('VisualImageDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
# Transport types deliberately defer semantic validation to each individual item.
# Using SearchItemAnalysis here would let one invalid item reject the SDK batch.
class VisualImageDraft(StrictBaseModel_legacy):
    image_url: str
    observation: str

@_preserve_class('VisualJudgmentDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class VisualJudgmentDraft(StrictBaseModel_legacy):
    requirement_id: str
    status: str
    evidence_fields: list[str] = Field_legacy(default_factory=list)
    evidence: list[str] = Field_legacy(default_factory=list)
    image_evidence: list[VisualImageDraft] = Field_legacy(default_factory=list)

@_preserve_class('VisualAttributeDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class VisualAttributeDraft(StrictBaseModel_legacy):
    attribute: str
    value: str | list[str]
    group: str
    fixed_by_requirement_ids: list[str] = Field_legacy(default_factory=list)
    evidence_fields: list[str] = Field_legacy(default_factory=list)
    evidence: list[str] = Field_legacy(default_factory=list)
    image_evidence: list[VisualImageDraft] = Field_legacy(default_factory=list)

@_preserve_class('VisualConflictDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class VisualConflictDraft_legacy(StrictBaseModel_legacy):
    attribute: str
    requirement_id: str | None = None
    evidence_fields: list[str]
    metadata_evidence: list[str]
    image_evidence: list[VisualImageDraft]
    explanation: str

@_preserve_class('SearchItemAnalysisDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemAnalysisDraft(StrictBaseModel_legacy):
    item_id: str
    image_url: str | None = None
    attributes: list[VisualAttributeDraft]
    judgments: list[VisualJudgmentDraft]
    conflicts: list[VisualConflictDraft_legacy]
    relavance_quality: str
    thum_quality: str
    thumbnail_kind: str
    relevance_evidence: str
    thumbnail_evidence: str

@_preserve_class('SearchVisualBatchOutput', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchVisualBatchOutput(StrictBaseModel_legacy):
    items: list[SearchItemAnalysisDraft]

@_preserve_class('SearchItemAnalysisDraftV3', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemAnalysisDraftV3(SearchItemAnalysisDraft):
    thumbnail_observation: ThumbnailObservationDraft

@_preserve_class('SearchVisualBatchOutputV3', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchVisualBatchOutputV3(StrictBaseModel_legacy):
    items: list[SearchItemAnalysisDraftV3]

@_preserve_class('HardConditionFindingDraft', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class HardConditionFindingDraft(StrictBaseModel_legacy):
    requirement_id: str
    # matched / clear_mismatch / insufficient_evidence; checked per item
    finding: str
    evidence: str

@_preserve_class('SearchItemAnalysisDraftV7', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemAnalysisDraftV7(SearchItemAnalysisDraftV3):
    hard_condition_findings: list[HardConditionFindingDraft]

@_preserve_class('SearchVisualBatchOutputV7', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchVisualBatchOutputV7(StrictBaseModel_legacy):
    items: list[SearchItemAnalysisDraftV7]

@_preserve_class('VisualJudgmentDraftV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class VisualJudgmentDraftV8_legacy(VisualJudgmentDraft):
    status: Literal_legacy['met', 'mostly_met', 'partial', 'unmet', 'unknown']

@_preserve_class('VisualAttributeDraftV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class VisualAttributeDraftV8_legacy(VisualAttributeDraft):
    attribute: Literal_legacy['category', 'color', 'pattern', 'fit', 'gender', 'material', 'theme', 'occasion']
    group: Literal_legacy['product', 'visual', 'shape', 'gender', 'material', 'style']

@_preserve_class('HardConditionFindingV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class HardConditionFindingV8_legacy(HardConditionFindingDraft):
    finding: Literal_legacy['matched', 'clear_mismatch', 'insufficient_evidence']

@_preserve_class('SearchItemAnalysisDraftV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemAnalysisDraftV8(SearchItemAnalysisDraft):
    attributes: list[VisualAttributeDraftV8_legacy]
    judgments: list[VisualJudgmentDraftV8_legacy]
    relavance_quality: Literal_legacy['high', 'medium', 'low']
    thum_quality: Literal_legacy['high', 'medium', 'low']
    thumbnail_kind: Literal_legacy['person', 'product_only', 'unknown']
    thumbnail_observation_v8: ThumbnailObservationV1_legacy | ThumbnailObservationV8_legacy
    observed_values: ObservedValuesV8
    hard_condition_findings: list[HardConditionFindingV8_legacy]
    alternative_judgments: list[AlternativeJudgmentV8_legacy]

@_preserve_class('SearchVisualBatchOutputV8', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchVisualBatchOutputV8(StrictBaseModel_legacy):
    items: list[SearchItemAnalysisDraftV8]

@_preserve_class('SearchItemAnalysisDraftV9', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemAnalysisDraftV9_legacy(SearchItemAnalysisDraft):
    exposure_suitability: ExposureSuitability_legacy | None = None
    attributes: list[VisualAttributeDraftV8_legacy]
    judgments: list[VisualJudgmentDraftV8_legacy]
    relavance_quality: Literal_legacy['high', 'medium', 'low']
    thum_quality: Literal_legacy['high', 'medium', 'low']
    thumbnail_kind: Literal_legacy['person', 'product_only', 'unknown']
    thumbnail_observation_v8: ThumbnailObservationV1_legacy | ThumbnailObservationV8_legacy
    hard_condition_findings: list[HardConditionFindingV8_legacy]
    alternative_judgments: list[AlternativeJudgmentV8_legacy]

    @model_serializer(mode='wrap')
    def serialize_exposure(self, handler):
        data = handler(self)
        if self.exposure_suitability is None:
            data.pop("exposure_suitability", None)
        return data

@_preserve_class('SearchVisualBatchOutputV9', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchVisualBatchOutputV9_legacy(StrictBaseModel_legacy):
    items: list[SearchItemAnalysisDraftV9_legacy]
SearchItemAnalysisV36_legacy = SearchItemAnalysisV36_v36
SearchItemAnalysisV40_legacy = SearchItemAnalysisV40_v40
SearchItemAnalysisV41_legacy = SearchItemAnalysisV41_v41
SearchItemAnalysisV42_legacy = SearchItemAnalysisV42
SearchItemAnalysisV43_legacy = SearchItemAnalysisV43
SearchItemAnalysisV44_legacy = SearchItemAnalysisV44
SearchItemAnalysisV45_legacy = SearchItemAnalysisV45
SearchItemAnalysisV57_search_product_evaluation_legacy = SearchItemAnalysisV57_search_product_evaluation_v57
SearchItemAnalysisV59_search_product_evaluation_legacy = SearchItemAnalysisV59_search_product_evaluation_v59

@_preserve_class('SearchItemEvaluation', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_legacy')
class SearchItemEvaluation(StrictBaseModel_legacy):
    hard_condition_findings: list[dict[str, str]] | None = None
    evaluation_attempt_count: int = 1
    evaluation_recovery: dict | None = None
    evaluation_mode: Literal_legacy['fresh', 'reused', 'duplicate_unresolved', 'skipped'] = 'fresh'
    evaluation_source_attempt_id: str | None = None
    evaluation_source_item_id: str | None = None
    evaluation_source_item: ProductRecord_legacy | None = None
    duplicate_match_fields: list[Literal_legacy['item_id', 'title', 'image_url', 'evidence_snapshot']] = Field_legacy(default_factory=list)
    item_id: str
    batch_id: str
    status: Literal_legacy['accepted', 'rejected', 'evaluation_error', 'image_fetch_error', 'duplicate_skipped']
    analysis: SearchItemAnalysis | SearchItemAnalysisV36_legacy | SearchItemAnalysisV40_legacy | SearchItemAnalysisV41_legacy | SearchItemAnalysisV42_legacy | SearchItemAnalysisV43_legacy | SearchItemAnalysisV44_legacy | SearchItemAnalysisV59_search_product_evaluation_legacy | SearchItemAnalysisV57_search_product_evaluation_legacy | SearchItemAnalysisV45_legacy | None = None
    reasons: list[str] = Field_legacy(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    error_fields: list[str] = Field_legacy(default_factory=list)
    requirement_id: str | None = None
    thumbnail_quality_correction: str | None = None
    evidence_path_corrections: list[str] = Field_legacy(default_factory=list)
    retained_in_pool: bool = False

    @model_validator_legacy(mode='after')
    def validate_skipped_duplicate(self):
        if self.status == 'duplicate_skipped' and (self.analysis is not None or self.evaluation_mode != 'skipped'):
            raise ValueError('Skipped duplicate must have no analysis and use skipped mode.')
        return self


# ---- search_product_evaluation_v10 ----

"""schemas.search.product_evaluation.search_product_evaluation_v10: definitions relocated without semantic changes."""
AlternativeJudgmentV8 = AlternativeJudgmentV8_legacy
from pydantic import Field as Field_v10
HardConditionFindingV8_v10 = HardConditionFindingV8_legacy
from typing import Literal as Literal_v10
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v10
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV8_legacy as ThumbnailObservationV8
VisualAttributeDraftV8 = VisualAttributeDraftV8_legacy
VisualConflictDraft = VisualConflictDraft_legacy
VisualJudgmentDraftV8 = VisualJudgmentDraftV8_legacy
from pydantic import create_model as create_model_v10
from functools import lru_cache as lru_cache_v10

@_preserve_class('ImageObservationV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class ImageObservationV10_v10(StrictBaseModel_v10):
    observation: str

@_preserve_class('AttributeV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class AttributeV10_v10(VisualAttributeDraftV8):
    image_evidence: list[ImageObservationV10_v10] = Field_v10(default_factory=list)

@_preserve_class('JudgmentV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class JudgmentV10_v10(VisualJudgmentDraftV8):
    image_evidence: list[ImageObservationV10_v10] = Field_v10(default_factory=list)

@_preserve_class('ConflictV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class ConflictV10(VisualConflictDraft):
    image_evidence: list[ImageObservationV10_v10]

@_preserve_class('AlternativeV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class AlternativeV10_v10(AlternativeJudgmentV8):
    image_evidence: list[ImageObservationV10_v10]

@_preserve_class('ItemEvaluationV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class ItemEvaluationV10_v10(StrictBaseModel_v10):
    attributes: list[AttributeV10_v10]
    judgments: list[JudgmentV10_v10]
    conflicts: list[ConflictV10]
    relavance_quality: Literal_v10['high', 'medium', 'low']
    thum_quality: Literal_v10['high', 'medium', 'low']
    thumbnail_kind: Literal_v10['person', 'product_only', 'unknown']
    relevance_evidence: str
    thumbnail_evidence: str
    thumbnail_observation_v8: ThumbnailObservationV8
    hard_condition_findings: list[HardConditionFindingV8_v10]
    alternative_judgments: list[AlternativeV10_v10]

@_preserve_class('VisualSlotsV10', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
class VisualSlotsV10_v10(StrictBaseModel_v10):
    """Marker for strict raw-JSON validation in the adapter."""

@_preserve_function('visual_slots_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
@lru_cache_v10(maxsize=10)
def visual_slots_schema_v10(active_count: int) -> type[VisualSlotsV10_v10]:
    if not 1 <= active_count <= 10:
        raise ValueError('Expected 1..10 active visual slots.')
    # Every key is mandatory. Inactive slots accept ONLY null, never fabricated items.
    fields = {f'item_{i:02d}': (ItemEvaluationV10_v10 if i <= active_count else type(None), ...) for i in range(1, 11)}
    return create_model_v10(f'SearchVisualSlotsV10_{active_count}', __base__=VisualSlotsV10_v10, **fields)

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v10')
def output_schema_v10(count, context):
    return visual_slots_schema_v10(count)


# ---- search_product_evaluation_v11 ----

"""schemas.search.product_evaluation.search_product_evaluation_v11: definitions relocated without semantic changes."""
ItemEvaluationV10_v11 = ItemEvaluationV10_v10
from pydantic import PrivateAttr as PrivateAttr_v11
SearchVisualBatchOutputV9 = SearchVisualBatchOutputV9_legacy
VisualSlotsV10 = VisualSlotsV10_v10
from pydantic import create_model as create_model_v11
from functools import lru_cache as lru_cache_v11

@_preserve_class('VisualSlotsV11', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v11')
class VisualSlotsV11_v11(VisualSlotsV10):
    _slot_errors: dict = PrivateAttr_v11(default_factory=dict)

@_preserve_function('visual_slots_schema_v11', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v11')
@lru_cache_v11(maxsize=10)
def visual_slots_schema_v11(active_count):
    if not 1 <= active_count <= 10:
        raise ValueError('Expected 1..10 active visual slots.')
    return create_model_v11(f'SearchVisualSlotsV11_{active_count}', __base__=VisualSlotsV11_v11, **{f'item_{i:02d}': (ItemEvaluationV10_v11 if i <= active_count else type(None), ...) for i in range(1, 11)})

@_preserve_function('parse_visual_slots_v11', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v11')
def parse_visual_slots_v11(payload, schema):
    """Root corruption fails the batch; identifiable item failures stay isolated."""
    if not isinstance(payload, dict) or set(payload) - set(schema.model_fields):
        raise ValueError('Unexpected visual slot response root or keys.')
    values, errors = ({}, {})
    for key, field in schema.model_fields.items():
        if field.annotation is type(None):
            if key not in payload or payload[key] is not None:
                raise ValueError(f'Inactive slot {key} must be present and null.')
            values[key] = None
            continue
        try:
            values[key] = field.annotation.model_validate(payload.get(key))
        except ValueError as exc:
            values[key] = None
            errors[key] = str(exc)
    result = schema.model_construct(**values)
    result._slot_errors = errors
    if '_model_response' in schema.__private_attributes__:
        from copy import deepcopy
        result._model_response = deepcopy(payload)
    return result

@_preserve_class('VisualBatchOutputV11', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v11')
class VisualBatchOutputV11_v11(SearchVisualBatchOutputV9):
    _slot_errors: dict = PrivateAttr_v11(default_factory=dict)

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v11')
def output_schema_v11(count, context):
    return visual_slots_schema_v11(count)


# ---- search_product_evaluation_v14 ----

"""schemas.search.product_evaluation.search_product_evaluation_v14: definitions relocated without semantic changes."""
AlternativeV10 = AlternativeV10_v10
HardConditionFindingV8 = HardConditionFindingV8_legacy
ItemEvaluationV10 = ItemEvaluationV10_v10
JudgmentV10 = JudgmentV10_v10
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v14
VisualSlotsV11_v14 = VisualSlotsV11_v11
from fashion_recommendation_v2.schemas.search._model_utils import copy_fields
from pydantic import create_model as create_model_v14

@_preserve_function('alternative_slots', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v14')
def alternative_slots(context):
    result = {}
    for alt in context['required_alternatives']:
        group = result.setdefault(alt['requirement_id'], {})
        group[f'alt_{len(group) + 1:02d}'] = alt['value']
    return result

@_preserve_function('visual_slots_schema_v14', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v14')
def visual_slots_schema_v14_v14(count, context):
    if not 1 <= count <= 10:
        raise ValueError('Expected 1..10 active visual slots.')
    judgment = create_model_v14('ConditionJudgmentV14', __base__=StrictBaseModel_v14, **copy_fields(JudgmentV10, exclude={'requirement_id'}))
    finding = create_model_v14('ConditionFindingV14', __base__=StrictBaseModel_v14, **copy_fields(HardConditionFindingV8, exclude={'requirement_id'}))
    alternative = create_model_v14('AlternativeJudgmentV14', __base__=StrictBaseModel_v14, **copy_fields(AlternativeV10, exclude={'requirement_id', 'value'}))
    judgments = create_model_v14('ConditionJudgmentsV14', __base__=StrictBaseModel_v14, **{rid: (judgment, ...) for rid in context['required_judgment_ids']})
    findings = create_model_v14('HardFindingsV14', __base__=StrictBaseModel_v14, **{rid: (finding, ...) for rid in context['required_hard_finding_ids']})
    alternatives = create_model_v14('AlternativeGroupsV14', __base__=StrictBaseModel_v14, **{rid: (create_model_v14(f'AlternativeSlotsV14_{i}', __base__=StrictBaseModel_v14, **{slot: (alternative, ...) for slot in slots}), ...) for i, (rid, slots) in enumerate(alternative_slots(context).items())})
    item = create_model_v14('ItemEvaluationV14', __base__=ItemEvaluationV10, judgments=(judgments, ...), hard_condition_findings=(findings, ...), alternative_judgments=(alternatives, ...))
    return create_model_v14(f'SearchVisualSlotsV14_{count}', __base__=VisualSlotsV11_v14, **{f'item_{i:02d}': (item if i <= count else type(None), ...) for i in range(1, 11)})

@_preserve_function('bind_condition_ids', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v14')
def bind_condition_ids(data, context):
    for field in ('judgments', 'hard_condition_findings'):
        data[field] = [dict(requirement_id=rid, **value) for rid, value in data[field].items()]
    slots = alternative_slots(context)
    data['alternative_judgments'] = [dict(requirement_id=rid, value=slots[rid][slot], **value) for rid, group in data['alternative_judgments'].items() for slot, value in group.items()]

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v14')
def output_schema_v14(count, context):
    return visual_slots_schema_v14_v14(count, context)


# ---- search_product_evaluation_v18 ----

"""schemas.search.product_evaluation.search_product_evaluation_v18: definitions relocated without semantic changes."""
from typing import Annotated as Annotated_v18
AttributeV10_v18 = AttributeV10_v10
from pydantic import Field as Field_v18
from typing import Literal as Literal_v18
from typing_extensions import TypeAliasType
from typing import Union as Union_v18
from pydantic import create_model as create_model_v18
from copy import deepcopy as deepcopy_v18
from typing import get_args as get_args_v18
from typing import get_origin
from functools import lru_cache
from hashlib import sha256
visual_slots_schema_v14 = visual_slots_schema_v14_v14
# Positive alternatives exclude exactly "unknown" without API-unsupported
# lookaround. Accept shorter prefixes, a differing character, or a suffix.
_UNKNOWN = 'unknown'
KNOWN_TEXT_PATTERN = '^(?:' + '|'.join([_UNKNOWN[:i] for i in range(1, len(_UNKNOWN))] + [_UNKNOWN[:i] + '[^' + char + r'][\s\S]*' for i, char in enumerate(_UNKNOWN)] + [_UNKNOWN + r'[\s\S]+']) + ')$'

@_preserve_function('shared_literal', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v18')
@lru_cache(maxsize=32)
def shared_literal(values):
    name = 'SharedEnumV18_' + sha256(repr(values).encode()).hexdigest()[:12]
    return TypeAliasType(name, Literal_v18[values])

@_preserve_function('shared_fields', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v18')
def shared_fields(model):
    # Reuse identical enums across ten item schemas, rather than repeat their
    # values in every definition and exceed the structured-output enum budget.
    return {key: (shared_literal(get_args_v18(field.annotation)), deepcopy_v18(field)) for key, field in model.model_fields.items() if get_origin(field.annotation) is Literal_v18}

@_preserve_function('visual_slots_schema_v18', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v18')
def visual_slots_schema_v18_v18(count, context):
    base = visual_slots_schema_v14(count, context)
    fields = {}
    for index, item_data in enumerate(context['items'], 1):
        slot = f'item_{index:02d}'
        suffix = f'V18Slot{index}'
        paths = tuple(context['available_evidence_fields'][item_data['item_id']])
        paths_type = TypeAliasType(f'EvidencePaths{suffix}', Literal_v18[paths]) if paths else str
        path_field = (list[paths_type], Field_v18(..., **{} if paths else {'max_length': 0}))

        def bind_paths(model, name):
            return create_model_v18(name + suffix, __base__=model, **shared_fields(model), evidence_fields=path_field)
        known_text = Annotated_v18[str, Field_v18(pattern=KNOWN_TEXT_PATTERN)]
        known = create_model_v18('KnownAttribute' + suffix, __base__=bind_paths(AttributeV10_v18, 'Attribute'), value=(Union_v18[known_text, list[str]], ...))
        unknown = create_model_v18('UnknownAttribute' + suffix, __base__=AttributeV10_v18, **shared_fields(AttributeV10_v18), value=(Literal_v18['unknown'], ...), fixed_by_requirement_ids=(list[str], Field_v18(..., max_length=0)), evidence_fields=(list[str], Field_v18(..., max_length=0)), image_evidence=(AttributeV10_v18.model_fields['image_evidence'].annotation, Field_v18(..., max_length=0)))
        item = base.model_fields[slot].annotation
        updates = {**shared_fields(item), 'attributes': (list[Union_v18[known, unknown]], ...)}
        for field in ('judgments', 'alternative_judgments'):
            container = item.model_fields[field].annotation
            entries = {}
            for key, spec in container.model_fields.items():
                if field == 'judgments':
                    bound = bind_paths(spec.annotation, 'Judgment')
                else:
                    bound = create_model_v18('AlternativeSlots' + key + suffix, __base__=spec.annotation, **{k: (bind_paths(v.annotation, 'Alternative'), ...) for k, v in spec.annotation.model_fields.items()})
                entries[key] = (bound, ...)
            updates[field] = (create_model_v18(field + suffix, __base__=container, **entries), ...)
        conflict = item.model_fields['conflicts'].annotation.__args__[0]
        updates['conflicts'] = (list[bind_paths(conflict, 'Conflict')], ...)
        fields[slot] = (create_model_v18('ItemEvaluation' + suffix, __base__=item, **updates), ...)
    return create_model_v18(f'SearchVisualSlotsV18_{count}', __base__=base, **fields)

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v18')
def output_schema_v18(count, context):
    return visual_slots_schema_v18_v18(count, context)


# ---- search_product_evaluation_v24 ----

"""schemas.search.product_evaluation.search_product_evaluation_v24: definitions relocated without semantic changes."""
from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability as ExposureSuitability_v24
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy as ThumbnailObservationV1_v24
from pydantic import create_model as create_model_v24
visual_slots_schema_v18 = visual_slots_schema_v18_v18

@_preserve_function('visual_slots_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v24')
def visual_slots_schema(count, context):
    """The same v24 presentation/exposure extensions used before the layout move."""
    if context.get('thumbnail_rubric_version', 'v4') == 'v4':
        return visual_slots_schema_safety_v4(count, context)
    return visual_slots_schema_thumbnail_v1(count, context)

@_preserve_function('visual_slots_schema_thumbnail_v1', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v24')
def visual_slots_schema_thumbnail_v1(count, context):
    base = visual_slots_schema_v18(count, context)
    return create_model_v24(f'SearchVisualSlotsV24ThumbnailV1_{count}', __base__=base, **{f'item_{index:02d}': (create_model_v24(f'ItemEvaluationThumbnailV1Slot{index}', __base__=base.model_fields[f'item_{index:02d}'].annotation, thumbnail_observation_v8=(ThumbnailObservationV1_v24, ...)), ...) for index in range(1, count + 1)})

@_preserve_function('visual_slots_schema_safety_v4', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v24')
def visual_slots_schema_safety_v4(count, context):
    base = visual_slots_schema_thumbnail_v1(count, context)
    return create_model_v24(f'SearchVisualSlotsV24SafetyV4_{count}', __base__=base, **{f'item_{index:02d}': (create_model_v24(f'ItemEvaluationSafetyV4Slot{index}', __base__=base.model_fields[f'item_{index:02d}'].annotation, exposure_suitability=(ExposureSuitability_v24, ...)), ...) for index in range(1, count + 1)})

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v24')
def output_schema_v24(count, context):
    return visual_slots_schema(count, context)


# ---- search_product_evaluation_v26 ----

"""One image response: admission evidence, product facts and Ranking visibility.

Only the code-derived draft permits absent visibility, so an auxiliary failure
can be recorded without losing otherwise valid Search admission evidence.
"""
from copy import deepcopy as deepcopy_v26
from typing import Any
from pydantic import PrivateAttr as PrivateAttr_v26
from pydantic import create_model as create_model_v26
from fashion_recommendation_v2.schemas.product_evidence import ProductFactV26 as ProductFactV26_v26
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationV5
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v26
admission_schema = output_schema_v24
SearchItemAnalysisDraftV9 = SearchItemAnalysisDraftV9_legacy
VisualBatchOutputV11 = VisualBatchOutputV11_v11
ImageObservationV10 = ImageObservationV10_v10

@_preserve_class('ProductFactDraftV26', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v26')
class ProductFactDraftV26(ProductFactV26_v26):
    image_evidence: list[ImageObservationV10]

@_preserve_class('ProductDraftV26', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v26')
class ProductDraftV26_v26(SearchItemAnalysisDraftV9):
    product_facts_v26: list[ProductFactV26_v26]
    visual_confirmation_v5: VisualConfirmationV5 | None = None

@_preserve_class('ProductBatchV26', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v26')
class ProductBatchV26_v26(VisualBatchOutputV11):
    items: list[ProductDraftV26_v26]
    _ranking_errors: dict = PrivateAttr_v26(default_factory=dict)
    _review_targets: dict = PrivateAttr_v26(default_factory=dict)
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v26
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements

@_preserve_class('ProductReviewInputV26', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v26')
class ProductReviewInputV26(StrictBaseModel_v26):
    """Review the exact generated batch, preserving fields and keyed conditions."""
    item: ProductRecord
    resolved_requirements: ResolvedRequirements
    target_slot: str
    model_response: dict[str, Any]
    response_schema: dict[str, Any]
    code_validation: dict[str, Any]

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v26')
def output_schema_v26(count, context):
    base = admission_schema(count, context)
    fields = {}
    for index in range(1, count + 1):
        slot = f'item_{index:02d}'
        fields[slot] = (create_model_v26(f'ProductEvaluationV26Slot{index}', __base__=base.model_fields[slot].annotation, product_facts_v26=(list[ProductFactDraftV26], ...), visual_confirmation_v5=(VisualConfirmationV5, ...)), ...)
    return preserve_response_schema_v26(create_model_v26(f'SearchVisualSlotsV26_{count}', __base__=base, **fields))

@_preserve_function('admission_projection', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v26')
def admission_projection(raw, core_schema):
    """Explicit derived projection, NOT a repaired/rewritten model_response.

    Unknown fields or invalid product facts cannot be concealed as a V failure.
    The caller retains the complete original response and the schema error.
    """
    required = {*core_schema.model_fields, 'product_facts_v26'}
    if not isinstance(raw, dict) or not required <= set(raw) <= required | {'visual_confirmation_v5'}:
        raise ValueError('Cannot derive admission from a missing/unknown response field.')
    from pydantic import TypeAdapter
    facts = TypeAdapter(list[ProductFactDraftV26]).validate_python(raw['product_facts_v26'])
    core = core_schema.model_validate({k: deepcopy_v26(raw[k]) for k in core_schema.model_fields})
    return {**core.model_dump(mode='json'), 'product_facts_v26': [f.model_dump(mode='json') for f in facts], 'visual_confirmation_v5': None}


# ---- search_product_evaluation_v29 ----

"""Same image transport as v26; explicit, audited field-local code projection."""
from pydantic import create_model as create_model_v29
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v29
ProductDraftV26 = ProductDraftV26_v26
ProductBatchV26 = ProductBatchV26_v26
integrated_schema_v29 = output_schema_v26

@_preserve_class('ProductDraftV29', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v29')
class ProductDraftV29(ProductDraftV26):
    # Code-owned diagnostic, never an LLM output field.
    validation_v29: dict

@_preserve_class('ProductBatchV29', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v29')
class ProductBatchV29(ProductBatchV26):
    items: list[ProductDraftV29]

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v29')
def output_schema_v29(count, context):
    return preserve_response_schema_v29(create_model_v29(f'SearchVisualSlotsV29_{count}', __base__=integrated_schema_v29(count, context)))


# ---- search_product_evaluation_v32 ----

"""Compact per-product evidence references; expanded storage uses the existing contract."""
from copy import deepcopy as deepcopy_v32
from typing import Literal as Literal_v32
from typing import get_args as get_args_v32
from typing import Annotated
from pydantic import Field as Field_v32
from pydantic import create_model as create_model_v32
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v32
from fashion_recommendation_v2.schemas.stylist import StylistAttribute
from fashion_recommendation_v2.schemas.product_evidence import ProductFactV26
from fashion_recommendation_v2.schemas.product_evidence import DIVERSITY_ATTRIBUTE_GROUPS
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v32
VisualSlotsV11_v32 = VisualSlotsV11_v11
integrated_schema_v32 = output_schema_v26
AttributeV10 = AttributeV10_v10
ATTRIBUTE_GROUPS_v32 = {k: v for k, v in DIVERSITY_ATTRIBUTE_GROUPS.items() if k != 'detail'}
EvidenceID = Annotated[int, Field_v32(strict=True, ge=1)]

@_preserve_class('EvidenceV32', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v32')
class EvidenceV32(StrictBaseModel_v32):
    """IDs are code-owned 1-based positions in this product's evidence list."""
    evidence_fields: list[str]
    evidence: list[str]
    image_evidence: list[Annotated[str, Field_v32(min_length=1)]]

@_preserve_class('AttributeV32', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v32')
class AttributeV32_v32(StrictBaseModel_v32):
    attribute: Literal_v32[tuple(ATTRIBUTE_GROUPS_v32)]
    value: AttributeV10.model_fields['value'].annotation
    evidence_ids: list[EvidenceID]

@_preserve_class('FactV32', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v32')
class FactV32_v32(StrictBaseModel_v32):
    attribute: Literal_v32[tuple((v for v in get_args_v32(StylistAttribute) if v not in ATTRIBUTE_GROUPS_v32)) + ('product_type', 'sleeve_length')]
    value: ProductFactV26.model_fields['value'].annotation
    evidence_ids: list[EvidenceID]

@_preserve_function('referenced', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v32')
def referenced(schema, name):
    fields = {k: (f.annotation, deepcopy_v32(f)) for k, f in schema.model_fields.items() if k not in {'evidence_fields', 'evidence', 'metadata_evidence', 'image_evidence'}}
    return create_model_v32(name, __base__=StrictBaseModel_v32, **fields, evidence_ids=(list[EvidenceID], ...))

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v32')
def output_schema_v32(count, context):
    base = integrated_schema_v32(count, context)
    fields = {}
    for slot, spec in base.model_fields.items():
        if spec.annotation is type(None):
            fields[slot] = (type(None), ...)
            continue
        old = spec.annotation
        compact = {k: (f.annotation, deepcopy_v32(f)) for k, f in old.model_fields.items() if k not in {'attributes', 'product_facts_v26', 'conflicts', 'judgments', 'alternative_judgments', 'thumbnail_kind', 'thumbnail_evidence'}}
        compact['evidence'] = (list[EvidenceV32], ...)
        compact['attributes'] = (list[AttributeV32_v32], ...)
        compact['product_facts_v26'] = (list[FactV32_v32], ...)
        compact['conflicts'] = (list[referenced(old.model_fields['conflicts'].annotation.__args__[0], f'ConflictV32_{slot}')], ...)
        judgments = old.model_fields['judgments'].annotation
        compact['judgments'] = (create_model_v32(f'JudgmentsV32_{slot}', __base__=StrictBaseModel_v32, **{rid: (referenced(f.annotation, f'JudgmentV32_{slot}_{rid}'), ...) for rid, f in judgments.model_fields.items()}), ...)
        alternatives = old.model_fields['alternative_judgments'].annotation
        compact['alternative_judgments'] = (create_model_v32(f'AlternativesV32_{slot}', __base__=StrictBaseModel_v32, **{rid: (create_model_v32(f'AlternativesV32_{slot}_{rid}', __base__=StrictBaseModel_v32, **{aid: (referenced(a.annotation, f'AlternativeV32_{slot}_{rid}_{aid}'), ...) for aid, a in f.annotation.model_fields.items()}), ...) for rid, f in alternatives.model_fields.items()}), ...)
        fields[slot] = (create_model_v32(f'ProductEvaluationV32_{slot}', __base__=StrictBaseModel_v32, **compact), ...)
    return preserve_response_schema_v32(create_model_v32(f'SearchVisualSlotsV32_{count}', __base__=VisualSlotsV11_v32, **fields))


# ---- search_product_evaluation_v33 ----

"""Observations own their facts; links select only input-owned condition/OR IDs."""
from copy import deepcopy
from typing import Literal as Literal_v33
from typing import Union
from pydantic import Field as Field_v33
from pydantic import create_model as create_model_v33
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v33
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v33
VisualSlotsV11 = VisualSlotsV11_v11
integrated_schema = output_schema_v26
AttributeV32 = AttributeV32_v32
FactV32 = FactV32_v32
ATTRIBUTE_GROUPS = ATTRIBUTE_GROUPS_v32

@_preserve_function('without_evidence', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v33')
def without_evidence(model, name):
    return create_model_v33(name, __base__=StrictBaseModel_v33, **{k: (f.annotation, deepcopy(f)) for k, f in model.model_fields.items() if k not in {'evidence_fields', 'evidence', 'image_evidence', 'evidence_ids'}})
AttributeV33 = without_evidence(AttributeV32, 'AttributeV33')
FactV33 = without_evidence(FactV32, 'FactV33')
UnknownAttributeV33 = create_model_v33('UnknownAttributeV33', __base__=AttributeV33, value=(Literal_v33['unknown'], ...))

@_preserve_function('link_fields', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v33')
def link_fields(judgments, alternatives, suffix):
    ids = tuple(judgments.model_fields)
    requirement_links = (list[Literal_v33[ids]], ...) if ids else (list[str], Field_v33(max_length=0))
    pairs = []
    for rid, spec in alternatives.model_fields.items():
        aids = tuple(spec.annotation.model_fields)
        if aids:
            pairs.append(create_model_v33('AlternativeLinkV33_' + suffix + '_' + rid, __base__=StrictBaseModel_v33, requirement_id=(Literal_v33[rid], ...), alternative_id=(Literal_v33[aids], ...)))
    alternative_links = (list[Union[tuple(pairs)]], ...) if pairs else (list[str], Field_v33(max_length=0))
    return dict(requirement_ids=requirement_links, alternative_targets=alternative_links)

@_preserve_function('output_schema', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v33')
def output_schema_v33(count, context):
    base = integrated_schema(count, context)
    fields = {}
    for slot, spec in base.model_fields.items():
        if spec.annotation is type(None):
            fields[slot] = (type(None), ...)
            continue
        old = spec.annotation
        judgments = old.model_fields['judgments'].annotation
        alternatives = old.model_fields['alternative_judgments'].annotation
        shared = dict(observation=(str, Field_v33(min_length=1)), attributes=(list[AttributeV33], ...), product_facts_v26=(list[FactV33], ...), **link_fields(judgments, alternatives, slot))
        metadata = create_model_v33('MetadataObservationV33_' + slot, __base__=StrictBaseModel_v33, source=(Literal_v33['metadata'], ...), evidence_fields=(list[str], Field_v33(min_length=1)), **shared)
        image = create_model_v33('ImageObservationV33_' + slot, __base__=StrictBaseModel_v33, source=(Literal_v33['image'], ...), **shared)
        unavailable = create_model_v33('UnavailableObservationV33_' + slot, __base__=StrictBaseModel_v33, source=(Literal_v33['unavailable'], ...), **{**shared, 'attributes': (list[UnknownAttributeV33], ...), 'product_facts_v26': (list[str], Field_v33(max_length=0))})
        compact = {k: (f.annotation, deepcopy(f)) for k, f in old.model_fields.items() if k not in {'attributes', 'product_facts_v26', 'judgments', 'alternative_judgments', 'thumbnail_kind', 'thumbnail_evidence'}}
        # Conflicts keep their paired metadata/image proof inline. They never
        # refer to a model-created ID and remain checked by the existing contract.
        compact['observations'] = (list[Union[metadata, image, unavailable]], ...)
        compact['judgments'] = (create_model_v33('JudgmentsV33_' + slot, __base__=StrictBaseModel_v33, **{rid: (without_evidence(f.annotation, 'JudgmentV33_' + slot + '_' + rid), ...) for rid, f in judgments.model_fields.items()}), ...)
        compact['alternative_judgments'] = (create_model_v33('AlternativesV33_' + slot, __base__=StrictBaseModel_v33, **{rid: (create_model_v33('AlternativesV33_' + slot + '_' + rid, __base__=StrictBaseModel_v33, **{aid: (without_evidence(a.annotation, 'AlternativeV33_' + slot + '_' + rid + '_' + aid), ...) for aid, a in f.annotation.model_fields.items()}), ...) for rid, f in alternatives.model_fields.items()}), ...)
        fields[slot] = (create_model_v33('ProductEvaluationV33_' + slot, __base__=StrictBaseModel_v33, **compact), ...)
    return preserve_response_schema_v33(create_model_v33(f'SearchVisualSlotsV33_{count}', __base__=VisualSlotsV11, **fields))
