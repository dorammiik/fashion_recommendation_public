"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- stylist ----

"""Stylist interpretation contracts; no product selection or marketplace planning.

All interpretations are soft and alternatives are OR. English fashion vocabulary,
semantic preservation and interpretation quality are prompt/review obligations.
Call StylistResult.validate_against(input_data) before consuming a result.
"""
from typing import Annotated
from typing import Any
from typing import Literal as Literal_base
from typing import Self
from typing import get_args
from pydantic import Field as Field_base
from pydantic import PrivateAttr
from pydantic import model_validator as model_validator_base
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.planner import PlannerUnresolvedState
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
NonBlankText_base = Annotated[str, Field_base(min_length=1, pattern=r"\S")]
Alternatives = Annotated[list[NonBlankText_base], Field_base(min_length=1)]
StylistAttribute = Literal_base["color", "size", "fit", "material", "pattern", "brand", "strength", "garment_care", "theme", "season", "occasion", "detail", "category"]

@_preserve_class('StylistAgentInput', 'fashion_recommendation_v2.schemas.stylist')
class StylistAgentInput_base(StrictBaseModel_base):
    user_request: NonBlankText_base
    unresolved_states: list[PlannerUnresolvedState] = Field_base(min_length=1)
    original_user_request: NonBlankText_base | None = None
    relation_intent: RelationIntent | None = None
    anchor_evidence: dict[str, Any] | None = Field_base(default=None, description="Code-validated Search observation projection; no raw snapshot fallback.")
    profile_lookup_status: Literal_base["not_found", "empty", "available", "failed"] = "not_found"
    preference_profile: PreferenceProfile | None = Field_base(default=None, description="Read-only Preference VIEW; current request takes precedence.")

    @model_validator_base(mode="after")
    def validate_states(self) -> Self:
        if self.relation_intent is not None:
            if self.anchor_evidence is None:
                raise ValueError("Resolved relation requires an anchor evidence projection.")
            if self.anchor_evidence.get('item_id') != self.relation_intent.anchor_item_id:
                raise ValueError("Stylist anchor identity must match the confirmed intent.")
            if self.anchor_evidence.get("category") != self.relation_intent.anchor_category:
                raise ValueError("Stylist anchor category must match the confirmed intent.")
        elif self.anchor_evidence is not None:
            raise ValueError("Anchor evidence requires a confirmed relation intent.")
        ids = [state.state_id for state in self.unresolved_states]
        if len(ids) != len(set(ids)):
            raise ValueError("Input state IDs must be unique.")
        for state in self.unresolved_states:
            if not state.state_id.strip() or not state.description.strip():
                raise ValueError("State ID and description must be nonblank.")
            if state.resolution_agent != "stylist_agent":
                raise ValueError("Pass only states assigned to stylist_agent.")
        return self

@_preserve_class('StylistDetailValue', 'fashion_recommendation_v2.schemas.stylist')
class StylistDetailValue_base(StrictBaseModel_base):
    key: NonBlankText_base = Field_base(description="Design/detail key, e.g. closure or pockets.")
    values: Alternatives = Field_base(description="English fashion terms; alternatives are OR.")

@_preserve_class('StylistInterpretation', 'fashion_recommendation_v2.schemas.stylist')
class StylistInterpretation_base(StrictBaseModel_base):
    attribute: StylistAttribute = Field_base(description="NormalizedItem semantic attribute or generic clothing category; never a marketplace ID/path.")
    value: NonBlankText_base | Alternatives | StylistDetailValue_base = Field_base(description="English fashion vocabulary. Lists are OR; detail requires a key/values object.")
    source_text: NonBlankText_base = Field_base(description="Exact supporting excerpt from the user request.")
    reason: NonBlankText_base = Field_base(description="Why this unresolved wording supports the interpretation.")
    state_id: NonBlankText_base = Field_base(description="Input unresolved state addressed by this interpretation.")
    preference_evidence_refs: list[NonBlankText_base] = Field_base(default_factory=list)
    search_text: NonBlankText_base | None = Field_base(default=None, description="Target search sentence rendering this attribute/value and its OR alternatives; not a user quote.")

    @model_validator_base(mode="after")
    def validate_value(self) -> Self:
        if (self.attribute == "detail") != isinstance(self.value, StylistDetailValue_base):
            raise ValueError("Only detail requires a StylistDetailValue object.")
        return self

@_preserve_class('StylistUnresolvedState', 'fashion_recommendation_v2.schemas.stylist')
class StylistUnresolvedState_base(StrictBaseModel_base):
    reason_code: Literal_base["context_missing", "profile_missing", "profile_lookup_failed", "body_information_missing"] = "context_missing"
    state_id: NonBlankText_base
    reason: NonBlankText_base = Field_base(description="Why the input state cannot yet be fully resolved.")
CompatibilityCriterion_base = Literal_base['category_pairing', 'color_pattern', 'style', "season", 'use_context']

@_preserve_class('CompatibilityGuidance', 'fashion_recommendation_v2.schemas.stylist')
class CompatibilityGuidance(StrictBaseModel_base):
    criterion: CompatibilityCriterion_base
    anchor_evidence_refs: list[NonBlankText_base]
    interpretation_indices: list[Annotated[int, Field_base(ge=0)]]
    reason: NonBlankText_base
    limitations: list[NonBlankText_base]

@_preserve_class('StylistResult', 'fashion_recommendation_v2.schemas.stylist')
class StylistResult_base(StrictBaseModel_base):
    preference_category: NonBlankText_base | None = None
    interpretations: list[StylistInterpretation_base]
    resolved_state_ids: list[NonBlankText_base]
    unresolved_states: list[StylistUnresolvedState_base]
    compatibility_guidance: list[CompatibilityGuidance] = Field_base(default_factory=list)
    _model_response: Any = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)

    @model_validator_base(mode="after")
    def validate_structure(self) -> Self:
        resolved = set(self.resolved_state_ids)
        unresolved_ids = [state.state_id for state in self.unresolved_states]
        unresolved = set(unresolved_ids)
        if len(resolved) != len(self.resolved_state_ids) or len(unresolved) != len(unresolved_ids):
            raise ValueError("Result state IDs must be unique within each status list.")
        if resolved & unresolved:
            raise ValueError("A state cannot be both resolved and unresolved.")
        interpreted = {entry.state_id for entry in self.interpretations}
        if not interpreted <= resolved | unresolved:
            raise ValueError("Every interpretation must reference a reported state.")
        if not resolved <= interpreted:
            raise ValueError("Each resolved state requires at least one interpretation.")
        keys = [(entry.state_id, entry.attribute, entry.value.key if isinstance(entry.value, StylistDetailValue_base) else None) for entry in self.interpretations]
        if len(keys) != len(set(keys)):
            raise ValueError("Combine alternatives for the same state and attribute/detail key into one value.")
        return self

    def validate_against(self, input_data: StylistAgentInput_base) -> Self:
        # Revalidate mutable nested instances as well as external references.
        source = StylistAgentInput_base.model_validate(input_data.model_dump())
        result = StylistResult_base.model_validate(self.model_dump())
        expected = {state.state_id for state in source.unresolved_states}
        reported = set(result.resolved_state_ids) | {state.state_id for state in result.unresolved_states}
        if reported != expected:
            raise ValueError("Every input state must be reported exactly once, with no new states.")
        profile = source.preference_profile
        if result.preference_category is not None and (profile is None or result.preference_category not in profile.by_category):
            raise ValueError('Preference category must reference the supplied profile')
        for unresolved in result.unresolved_states:
            if unresolved.reason_code == "profile_lookup_failed" and source.profile_lookup_status != "failed":
                raise ValueError('Cannot claim a profile lookup failure without one')
            if unresolved.reason_code == "profile_missing" and source.profile_lookup_status == "failed":
                raise ValueError('Lookup failure is not missing profile information')
        for entry in result.interpretations:
            refs = set(entry.preference_evidence_refs)
            if len(refs) != len(entry.preference_evidence_refs):
                raise ValueError('Duplicate preference evidence references')
            if refs:
                if profile is None or source.profile_lookup_status == "failed":
                    raise ValueError('Preference evidence requires an available profile')
                if entry.attribute == "size":
                    raise ValueError('Do not infer actual size from preference history')
                attr = 'category_path' if entry.attribute == "category" else entry.attribute
                local = profile.by_category.get(result.preference_category)
                features = [f for f in local.features if f.attribute == attr and f.evidence_refs] if local else []
                features = features or [f for f in profile.global_preferences.features if f.attribute == attr and f.evidence_refs]
                if isinstance(entry.value, StylistDetailValue_base):
                    features = [f for f in features if f.value.key == entry.value.key]
                allowed = {ref for f in features for ref in f.evidence_refs}
                if not refs <= allowed:
                    raise ValueError('Preference evidence must follow category-first attribute fallback')
            if entry.source_text not in source.user_request:
                raise ValueError("source_text must be an exact excerpt from user_request.")
            if source.original_user_request and entry.source_text not in source.original_user_request:
                raise ValueError("Stylist source_text must quote the actual user, not expanded anchor prose.")
        from fashion_recommendation_v2.compatibility import validate_stylist_compatibility
        validate_stylist_compatibility(source, result, get_args(CompatibilityCriterion_base))
        return self


# ---- stylist_v2 ----

"""Stylist v2: versioned preference origins; legacy contracts remain unchanged."""
from typing import Literal as Literal_v2
from pydantic import Field as Field_v2
from pydantic import model_validator as model_validator_v2
StylistAgentInput = StylistAgentInput_base
StylistInterpretation = StylistInterpretation_base
StylistResult = StylistResult_base
StylistDetailValue = StylistDetailValue_base
NonBlankText = NonBlankText_base
CompatibilityCriterion = CompatibilityCriterion_base
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_class('StylistAgentInputV2', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistAgentInputV2_v2(StylistAgentInput):
    user_id: NonBlankText
    personalization_mode: Literal_v2['cold', 'warm']
    # v4 is fetched through the authenticated tool
    preference_profile: None = None

@_preserve_class('StylistInterpretationV2', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistInterpretationV2_v2(StylistInterpretation):
    source_text: NonBlankText | None
    state_id: NonBlankText | None
    origin: Literal_v2['user_request', 'preference']
    preference_interpretation_id: NonBlankText | None

    @model_validator_v2(mode='after')
    def source_shape(self):
        if self.origin == 'preference':
            if self.source_text is not None or self.state_id is not None:
                raise ValueError('Preference-only additions have null source_text and state_id.')
            if not self.preference_interpretation_id:
                raise ValueError('Preference-only additions require a profile interpretation.')
        elif self.source_text is None or self.state_id is None:
            raise ValueError('User interpretations require source_text and state_id.')
        if bool(self.preference_interpretation_id) != bool(self.preference_evidence_refs):
            raise ValueError('Preference interpretation and evidence references must be supplied together.')
        if len(set(self.preference_evidence_refs)) != len(self.preference_evidence_refs):
            raise ValueError('Duplicate preference evidence references.')
        return self

@_preserve_class('StylistCopyV2', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistCopyV2_v2(StylistResult):
    """LLM-owned response; no generated management fields or profile snapshots."""
    preference_category: None = None
    interpretations: list[StylistInterpretationV2_v2]

    @model_validator_v2(mode='after')
    def validate_structure(self):
        resolved = set(self.resolved_state_ids)
        remaining = [s.state_id for s in self.unresolved_states]
        if len(resolved) != len(self.resolved_state_ids) or len(set(remaining)) != len(remaining) or resolved & set(remaining):
            raise ValueError('State IDs must be unique and disjoint.')
        interpreted = {i.state_id for i in self.interpretations if i.state_id is not None}
        if not interpreted <= resolved | set(remaining) or not resolved <= interpreted:
            raise ValueError('User interpretations must cover reported resolved states.')
        keys = [(i.origin, i.state_id, i.preference_interpretation_id if i.origin == 'preference' else None, i.attribute, i.value.key if isinstance(i.value, StylistDetailValue) else None) for i in self.interpretations]
        if len(set(keys)) != len(keys):
            raise ValueError('Combine same-source attribute alternatives into one OR value.')
        return self

    def validate_against(self, source, bundle=None):
        from fashion_recommendation_v2.stylist_personalization import validate_copy
        validate_copy(self, source, bundle)
        return self

@_preserve_class('StylistPersonalizationContext', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistPersonalizationContext(StrictBaseModel):
    mode: Literal_v2['cold', 'warm']
    user_id: NonBlankText
    profile_status: Literal_v2['not_requested', 'not_found', 'empty', 'available', 'failed']
    bundle: dict | None = None
    lookup_attempts: list[dict] = Field_v2(default_factory=list)
    fallback: bool = False

@_preserve_class('StylistResultV2', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistResultV2_v2(StylistCopyV2_v2):
    contract_version: Literal_v2['stylist-v2'] = 'stylist-v2'
    personalization_context: StylistPersonalizationContext

    @model_validator_v2(mode='after')
    def context_integrity(self):
        from fashion_recommendation_v2.stylist_personalization import validate_context
        from fashion_recommendation_v2.stylist_personalization import validate_preference_refs
        validate_context(self.personalization_context)
        validate_preference_refs(self.interpretations, self.personalization_context.bundle)
        return self

    def validate_against(self, source, bundle=None):
        ctx = self.personalization_context
        if source.user_id != ctx.user_id or source.personalization_mode != ctx.mode:
            raise ValueError('Stylist result user/mode differs from request.')
        source = source.model_copy(update={'profile_lookup_status': 'not_found' if ctx.profile_status == 'not_requested' else ctx.profile_status})
        return super().validate_against(source, ctx.bundle)

@_preserve_class('StylistGenerationInputV2', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistGenerationInputV2_v2(StylistAgentInputV2_v2):
    frozen_preference_bundle: dict | None = None
    validation_feedback: list[str] = Field_v2(default_factory=list)

@_preserve_class('StylistConditionProvenanceV2', 'fashion_recommendation_v2.schemas.stylist_v2')
class StylistConditionProvenanceV2_v2(StrictBaseModel):
    contract_version: Literal_v2['stylist-v2'] = 'stylist-v2'
    origin: Literal_v2['user_request', 'preference']
    state_id: NonBlankText | None
    preference_interpretation_id: NonBlankText | None
    preference_evidence_refs: list[NonBlankText]
    frozen_profile: dict | None

    @model_validator_v2(mode='after')
    def coherent(self):
        if self.origin == 'preference' and (self.state_id is not None or not self.preference_interpretation_id):
            raise ValueError('Preference-only provenance requires a profile interpretation and no state.')
        if self.origin == 'user_request' and self.state_id is None:
            raise ValueError('User provenance requires a state.')
        if bool(self.preference_interpretation_id) != bool(self.preference_evidence_refs):
            raise ValueError('Preference interpretation/evidence must be paired.')
        if self.preference_interpretation_id and (not self.frozen_profile):
            raise ValueError('Preference provenance requires frozen profile reference.')
        return self


# ---- stylist_v3 ----

"""Stylist v3: request-local raw evidence, with unchanged v2 input/context."""
from typing import Literal as Literal_v3
from pydantic import model_validator
StylistAgentInputV2_v3 = StylistAgentInputV2_v2
StylistGenerationInputV2 = StylistGenerationInputV2_v2
StylistInterpretationV2 = StylistInterpretationV2_v2
StylistCopyV2 = StylistCopyV2_v2
StylistResultV2 = StylistResultV2_v2
StylistConditionProvenanceV2 = StylistConditionProvenanceV2_v2
# Input and code-owned frozen context have not changed.
StylistAgentInputV3_v3 = StylistAgentInputV2_v3
StylistGenerationInputV3_v3 = StylistGenerationInputV2
PreferenceBasis = Literal_v3['none', 'profile_interpretation', 'raw_evidence']

@_preserve_function('validate_basis', 'fashion_recommendation_v2.schemas.stylist_v3')
def validate_basis(value):
    basis = value.preference_basis
    claim = value.preference_interpretation_id
    refs = value.preference_evidence_refs
    if basis == 'none' and (claim is not None or refs):
        raise ValueError('none requires null interpretation and empty evidence references.')
    if basis == 'profile_interpretation' and (not claim or not refs):
        raise ValueError('profile_interpretation requires interpretation and evidence references.')
    if basis == 'raw_evidence' and (claim is not None or not refs):
        raise ValueError('raw_evidence requires null interpretation and nonempty evidence references.')
    if value.origin == 'preference' and basis == 'none':
        raise ValueError('Preference-only additions require personalization evidence.')
    if len(refs) != len(set(refs)):
        raise ValueError('Duplicate preference evidence references.')

@_preserve_class('StylistInterpretationV3', 'fashion_recommendation_v2.schemas.stylist_v3')
class StylistInterpretationV3_v3(StylistInterpretationV2):
    preference_basis: PreferenceBasis

    @model_validator(mode='after')
    def source_shape(self):
        if self.origin == 'preference':
            if self.source_text is not None or self.state_id is not None:
                raise ValueError('Preference-only additions have null source_text and state_id.')
        elif self.source_text is None or self.state_id is None:
            raise ValueError('User interpretations require source_text and state_id.')
        validate_basis(self)
        return self

@_preserve_class('StylistCopyV3', 'fashion_recommendation_v2.schemas.stylist_v3')
class StylistCopyV3_v3(StylistCopyV2):
    interpretations: list[StylistInterpretationV3_v3]

@_preserve_class('StylistResultV3', 'fashion_recommendation_v2.schemas.stylist_v3')
class StylistResultV3_v3(StylistResultV2):
    contract_version: Literal_v3['stylist-v3'] = 'stylist-v3'
    interpretations: list[StylistInterpretationV3_v3]

@_preserve_class('StylistConditionProvenanceV3', 'fashion_recommendation_v2.schemas.stylist_v3')
class StylistConditionProvenanceV3_v3(StylistConditionProvenanceV2):
    contract_version: Literal_v3['stylist-v3'] = 'stylist-v3'
    preference_basis: PreferenceBasis

    @model_validator(mode='after')
    def coherent(self):
        validate_basis(self)
        if self.origin == 'preference' and self.state_id is not None:
            raise ValueError('Preference-only provenance has no state.')
        if self.origin == 'user_request' and self.state_id is None:
            raise ValueError('User provenance requires a state.')
        if self.preference_basis != 'none' and (not self.frozen_profile):
            raise ValueError('Personalization provenance requires frozen bundle reference.')
        if self.preference_basis == 'none' and self.frozen_profile is not None:
            raise ValueError('Unpersonalized provenance must not claim a frozen profile.')
        return self


# ---- stylist_v4 ----

"""v4 canonical output and request-local short-reference response schema."""
from typing import ClassVar
from typing import Literal as Literal_v4
from pydantic import Field
from pydantic import create_model as create_model_v4
StylistCopyV3 = StylistCopyV3_v3
StylistResultV3 = StylistResultV3_v3
StylistInterpretationV3 = StylistInterpretationV3_v3
StylistConditionProvenanceV3 = StylistConditionProvenanceV3_v3
StylistAgentInputV3 = StylistAgentInputV3_v3
StylistGenerationInputV3 = StylistGenerationInputV3_v3
StylistAgentInputV4 = StylistAgentInputV3
StylistGenerationInputV4 = StylistGenerationInputV3

@_preserve_class('StylistCopyV4', 'fashion_recommendation_v2.schemas.stylist_v4')
class StylistCopyV4(StylistCopyV3):
    exclude_profile_guidance: ClassVar[bool] = True

@_preserve_class('StylistResultV4', 'fashion_recommendation_v2.schemas.stylist_v4')
class StylistResultV4_v4(StylistResultV3):
    contract_version: Literal_v4['stylist-v4'] = 'stylist-v4'
    exclude_profile_guidance: ClassVar[bool] = True

@_preserve_class('StylistConditionProvenanceV4', 'fashion_recommendation_v2.schemas.stylist_v4')
class StylistConditionProvenanceV4_v4(StylistConditionProvenanceV3):
    contract_version: Literal_v4['stylist-v4'] = 'stylist-v4'

@_preserve_function('response_schema', 'fashion_recommendation_v2.schemas.stylist_v4')
def response_schema_v4(reference_keys):
    keys = tuple(reference_keys)
    refs = (list[Literal_v4[keys]], ...) if keys else (list[str], Field(max_length=0))
    row = create_model_v4('StylistInterpretationRefsV4', __base__=StylistInterpretationV3, preference_evidence_refs=refs)
    return create_model_v4('StylistCopyV4', __base__=StylistCopyV4, interpretations=(list[row], ...))


# ---- stylist_v5 ----

"""v5 preserves v4 interpretation contracts with similarity personalization disabled."""
from typing import Literal as Literal_v5
StylistResultV4 = StylistResultV4_v4
StylistConditionProvenanceV4 = StylistConditionProvenanceV4_v4
StylistAgentInputV2 = StylistAgentInputV2_v2
from fashion_recommendation_v2.personalization_policy import similarity_input
StylistAgentInputV5 = StylistAgentInputV2

@_preserve_class('StylistResultV5', 'fashion_recommendation_v2.schemas.stylist_v5')
class StylistResultV5_v5(StylistResultV4):
    contract_version: Literal_v5['stylist-v5'] = 'stylist-v5'

    def validate_against(self, source):
        return super().validate_against(similarity_input(source))

@_preserve_class('StylistConditionProvenanceV5', 'fashion_recommendation_v2.schemas.stylist_v5')
class StylistConditionProvenanceV5_v5(StylistConditionProvenanceV4):
    contract_version: Literal_v5['stylist-v5'] = 'stylist-v5'


# ---- stylist_v6 ----

"""v6 request-scoped state references; unchanged profile/reference contracts."""
from typing import Literal
from pydantic import create_model
profile_response_schema = response_schema_v4
StylistResultV5 = StylistResultV5_v5
StylistConditionProvenanceV5 = StylistConditionProvenanceV5_v5
StylistUnresolvedState = StylistUnresolvedState_base

@_preserve_class('StylistResultV6', 'fashion_recommendation_v2.schemas.stylist_v6')
class StylistResultV6(StylistResultV5):
    contract_version: Literal['stylist-v6'] = 'stylist-v6'

@_preserve_class('StylistConditionProvenanceV6', 'fashion_recommendation_v2.schemas.stylist_v6')
class StylistConditionProvenanceV6(StylistConditionProvenanceV5):
    contract_version: Literal['stylist-v6'] = 'stylist-v6'

@_preserve_function('response_schema', 'fashion_recommendation_v2.schemas.stylist_v6')
def response_schema(reference_keys, state_ids):
    """The same request-owned schema is used for generation and correction."""
    ids = tuple(state_ids)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Stylist state IDs must be nonempty and unique')
    allowed = Literal[ids]
    base = profile_response_schema(reference_keys)
    interpretation = base.model_fields['interpretations'].annotation.__args__[0]
    row = create_model('StylistInterpretationRefsV6', __base__=interpretation, state_id=(allowed | None, ...))
    unresolved = create_model('StylistUnresolvedStateV6', __base__=StylistUnresolvedState, state_id=(allowed, ...))
    return create_model('StylistCopyV6', __base__=base, interpretations=(list[row], ...), resolved_state_ids=(list[allowed], ...), unresolved_states=(list[unresolved], ...))


# ---- stylist_v8 ----

"""v8 scoped inputs and state-specific quotation validation."""
from typing import Literal as Literal_stylist_v8
from pydantic import Field as Field_stylist_v8
from pydantic import model_validator as model_validator_stylist_v8
NonBlankText_stylist_v8 = NonBlankText_base
StylistAgentInputV2_stylist_v8 = StylistAgentInputV2_v2
StylistResultV6_stylist_v8 = StylistResultV6
StylistConditionProvenanceV6_stylist_v8 = StylistConditionProvenanceV6
response_schema_stylist_v8 = response_schema

@_preserve_class('StylistAgentInputV8', 'fashion_recommendation_v2.schemas.stylist_v8')
class StylistAgentInputV8_stylist_v8(StylistAgentInputV2_stylist_v8):
    # Only assigned evidence, never the full request or choice delegation.
    state_source_texts: dict[str, list[NonBlankText_stylist_v8]]
    clear_condition_context: list[NonBlankText_stylist_v8]
    original_user_request: None = None

    @model_validator_stylist_v8(mode='after')
    def scoped_sources(self):
        ids = [s.state_id for s in self.unresolved_states]
        if set(self.state_source_texts) != set(ids):
            raise ValueError('state_source_texts must cover exactly the assigned states.')
        if any((not spans for spans in self.state_source_texts.values())):
            raise ValueError('Every assigned state requires original evidence.')
        expected = '\n'.join((text for sid in ids for text in self.state_source_texts[sid]))
        if self.user_request != expected:
            raise ValueError('v8 user_request must contain only assigned state evidence in order.')
        for state in self.unresolved_states:
            if state.description != '\n'.join(self.state_source_texts[state.state_id]):
                raise ValueError('v8 state descriptions must use assigned evidence only.')
        return self

@_preserve_class('StylistGenerationInputV8', 'fashion_recommendation_v2.schemas.stylist_v8')
class StylistGenerationInputV8_stylist_v8(StylistAgentInputV8_stylist_v8):
    frozen_preference_bundle: dict | None = None
    validation_feedback: list[str] = Field_stylist_v8(default_factory=list)

@_preserve_class('StylistResultV8', 'fashion_recommendation_v2.schemas.stylist_v8')
class StylistResultV8_stylist_v8(StylistResultV6_stylist_v8):
    contract_version: Literal_stylist_v8['stylist-v8'] = 'stylist-v8'

    def validate_against(self, source, bundle=None):
        source = StylistAgentInputV8_stylist_v8.model_validate(source.model_dump())
        super().validate_against(source)
        for entry in self.interpretations:
            if entry.origin == 'user_request' and (not any((entry.source_text in quote for quote in source.state_source_texts.get(entry.state_id, [])))):
                raise ValueError('source_text must quote the evidence of its linked state_id.')
        return self

@_preserve_class('StylistConditionProvenanceV8', 'fashion_recommendation_v2.schemas.stylist_v8')
class StylistConditionProvenanceV8_stylist_v8(StylistConditionProvenanceV6_stylist_v8):
    contract_version: Literal_stylist_v8['stylist-v8'] = 'stylist-v8'


# ---- stylist_v7 ----

"""v7 result identity; unchanged v6 request-scoped response and provenance rules."""
from typing import Literal as Literal_stylist_v7
StylistResultV6_stylist_v7 = StylistResultV6
StylistConditionProvenanceV6_stylist_v7 = StylistConditionProvenanceV6
response_schema_stylist_v7 = response_schema

@_preserve_class('StylistResultV7', 'fashion_recommendation_v2.schemas.stylist_v7')
class StylistResultV7_stylist_v7(StylistResultV6_stylist_v7):
    contract_version: Literal_stylist_v7['stylist-v7'] = 'stylist-v7'

@_preserve_class('StylistConditionProvenanceV7', 'fashion_recommendation_v2.schemas.stylist_v7')
class StylistConditionProvenanceV7_stylist_v7(StylistConditionProvenanceV6_stylist_v7):
    contract_version: Literal_stylist_v7['stylist-v7'] = 'stylist-v7'
