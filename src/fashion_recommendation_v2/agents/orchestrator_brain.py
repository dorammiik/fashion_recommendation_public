"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- orchestrator_brain ----

"""One initial LLM assessment, with at most one correction/API retry."""
from fashion_recommendation_v2.compatibility import ORCHESTRATOR_VERSION
from fashion_recommendation_v2.compatibility import validate_compatibility_assessment
from fashion_recommendation_v2.compatibility import response_record
from fashion_recommendation_v2.schemas.orchestrator import PendingRequestState
from fashion_recommendation_v2.schemas.orchestrator import RequestAssessment
from fashion_recommendation_v2.schemas.orchestrator import StructuredRequestAssessment_base as StructuredRequestAssessment
from fashion_recommendation_v2.schemas.orchestrator import AssessmentInput_base as AssessmentInput
from fashion_recommendation_v2.prompts.orchestrator import ORCHESTRATOR_PROMPT
from fashion_recommendation_v2.orchestrator_policy import assessment_contract
from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_MAX_ATTEMPTS
from fashion_recommendation_v2.agents.orchestrator_contracts import validate_segmentation
from fashion_recommendation_v2.agents.orchestrator_contracts import validate_similarity_assessment
from fashion_recommendation_v2.agents.orchestrator_contracts import ORCHESTRATOR_V2_ASSESSMENT_MODEL

@_preserve_class('OrchestratorExecutionError', 'fashion_recommendation_v2.agents.orchestrator_brain')
class OrchestratorExecutionError(RuntimeError):

    def __init__(self, *, code, message, attempts):
        self.code = code
        self.attempts = attempts
        super().__init__(message)

@_preserve_class('OrchestratorBrain', 'fashion_recommendation_v2.agents.orchestrator_brain')
class OrchestratorBrain:
    evaluation_version = ORCHESTRATOR_VERSION

    def __init__(self, *, llm, version=None):
        assessment_contract(version)
        self.evaluation_version = version or ORCHESTRATOR_VERSION
        self.llm = llm
        self.generation_attempts = []
        self.response_records = []

    def run(self, input_data: PendingRequestState) -> RequestAssessment:
        self.generation_attempts = []
        self.response_records = []
        source = PendingRequestState.model_validate(input_data.model_dump())
        if assessment_contract(self.evaluation_version).collected_validation:
            return self._run_v4(source)
        from fashion_recommendation_v2.module_compat import import_module as import_module
        contract = assessment_contract(self.evaluation_version)
        prompt = getattr(import_module('fashion_recommendation_v2.prompts.' + contract.prompt_module), contract.prompt_name)
        feedback = []
        for retry in range(2):
            request = AssessmentInput(**source.model_dump(), character_offsets=[f'{i}:{char}' for i, char in enumerate(source.user_query)], validation_feedback=feedback)
            code = 'api_error'
            raw_result = None
            try:
                result = self.llm.generate(system_prompt=prompt, user_input=request, output_schema=StructuredRequestAssessment, **{'call_model_settings': {'model': ORCHESTRATOR_V2_ASSESSMENT_MODEL}} if source.personalization_mode is not None or contract.force_assessment_model else {})
                raw_result = response_record(result)
                code = 'invalid_response'
                if not isinstance(result, RequestAssessment):
                    raise ValueError('Expected structured request assessment.')
                result = validate_segmentation(result, source.user_query)
                from fashion_recommendation_v2.agents.orchestrator_preferences import select_profile
                select_profile(source.preference_profile, result)
                if result.relation_intent:
                    intent = result.relation_intent
                    if intent.source_text not in source.user_query:
                        raise ValueError('Relation source text must occur in the request.')
                    if intent.anchor_item_id and intent.anchor_item_id not in {r.item.item_id for r in source.reference_items}:
                        raise ValueError('Relation anchor must reference a supplied item.')
                    if intent.anchor_rank is not None and (not any((r.rank == intent.anchor_rank and r.item.item_id == intent.anchor_item_id for r in source.reference_items))):
                        raise ValueError('Anchor rank must match the supplied ranked item.')
                validate_similarity_assessment(source, result)
                validate_compatibility_assessment(source, result)
            except Exception as exc:
                if isinstance(exc, (ValueError, TypeError)):
                    code = 'invalid_response'
                message = str(exc) or type(exc).__name__
                self.response_records.append(dict(attempt=retry + 1, request_id=source.request_id, correction_of=retry or None, **raw_result or response_record(error=exc), code_validation=dict(status='failed', errors=[message]), applied=False))
                self.generation_attempts.append(dict(retry_count=retry, status='error', code=code, error_type=type(exc).__name__, message=message))
                if retry == 1:
                    raise OrchestratorExecutionError(code=code, message=message, attempts=list(self.generation_attempts)) from exc
                feedback = [message] if code == 'invalid_response' else []
            else:
                self.response_records.append(dict(attempt=retry + 1, request_id=source.request_id, correction_of=retry or None, **raw_result, code_validation=dict(status='passed', errors=[]), applied=True))
                self.generation_attempts.append(dict(retry_count=retry, status='success'))
                return result

    def _run_v4(self, source):
        from copy import deepcopy
        from fashion_recommendation_v2.schemas.orchestrator import AssessmentInputV4_v4 as AssessmentInputV4
        from fashion_recommendation_v2.module_compat import import_module as import_module
        contract = assessment_contract(self.evaluation_version)
        input_schema = AssessmentInputV4
        if contract.terminal_period_warning:
            from fashion_recommendation_v2.schemas.orchestrator import AssessmentInputV9
            input_schema = AssessmentInputV9
        prompts = import_module('fashion_recommendation_v2.prompts.' + contract.prompt_module)
        generation_prompt = getattr(prompts, contract.prompt_name)
        correction_prompt = getattr(prompts, contract.correction_prompt_name)
        from fashion_recommendation_v2.orchestrator_validation import character_offsets
        from fashion_recommendation_v2.orchestrator_validation import inspect_received_response
        from fashion_recommendation_v2.orchestrator_validation import AssessmentValidationError
        response_schema = StructuredRequestAssessment
        if contract.derive_quote_coordinates:
            from fashion_recommendation_v2.schemas.orchestrator import QuoteAssessmentV11_orchestrator_v11 as QuoteAssessmentV11
            response_schema = QuoteAssessmentV11
        if contract.quote_only:
            from fashion_recommendation_v2.schemas.orchestrator import QuoteAssessmentV12_orchestrator_v12 as QuoteAssessmentV12
            from fashion_recommendation_v2.schemas.orchestrator import AssessmentInputV12_orchestrator_v12 as AssessmentInputV12
            response_schema, input_schema = (QuoteAssessmentV12, AssessmentInputV12)
        feedback = dict(errors=[], deferred_checks=[])
        previous = None
        first_id = f'{source.request_id}:assessment:1'
        for retry in range(ASSESSMENT_MAX_ATTEMPTS):
            attempt_id = f'{source.request_id}:assessment:{retry + 1}'
            identity = dict(attempt_id=attempt_id, attempt=retry + 1, stage='correction' if retry else 'generation', correction_of=first_id if retry else None)
            request = input_schema(**source.model_dump(), **{} if contract.quote_only else dict(character_offsets=character_offsets(source)), previous_response=deepcopy(previous), validation_feedback=deepcopy(feedback), assessment_attempt=identity)
            received, failure = (None, None)
            try:
                response = self.llm.generate(system_prompt=correction_prompt if retry else generation_prompt, user_input=request.model_copy(deep=True), output_schema=response_schema, call_model_settings={'model': ORCHESTRATOR_V2_ASSESSMENT_MODEL})
                received = response_record(response)
            except Exception as exc:
                failure = exc
                received = response_record(error=exc)
            result, report, previous = inspect_received_response(received, source.user_query, schema=response_schema if contract.quote_only else StructuredRequestAssessment, error=failure, derive_quote_coordinates=contract.derive_quote_coordinates, quote_only=contract.quote_only)
            coordinates = report.pop('coordinate_derivation', None)
            self._collect_context_checks(source, result, report)
            from fashion_recommendation_v2.orchestrator_validation import apply_terminal_period_policy
            apply_terminal_period_policy(report, source.user_query, self.evaluation_version)
            if contract.removal_feedback:
                from fashion_recommendation_v2.orchestrator_validation import add_removal_feedback
                add_removal_feedback(report)
            valid = failure is None and result is not None and (not report['errors']) and (not report['deferred_checks'])
            self.response_records.append(dict(**identity, request_id=source.request_id, **deepcopy(received), code_validation=dict(status='passed' if valid else 'failed', **deepcopy(report)), coordinate_derivation=coordinates, applied=valid, code_derived_result=result.model_dump(mode='json') if valid else None, assessment_input=request.model_dump(mode='json')))
            if valid:
                self.generation_attempts.append(dict(retry_count=retry, status='success', attempt_id=attempt_id))
                return result
            code = 'api_error' if failure is not None and (not isinstance(failure, (ValueError, TypeError))) else 'invalid_response'
            error = failure or AssessmentValidationError(report)
            message = str(error) or type(error).__name__
            self.generation_attempts.append(dict(retry_count=retry, status='error', code=code, error_type=type(error).__name__, message=message, attempt_id=attempt_id, correction_of=identity['correction_of'], code_validation=deepcopy(report)))
            if retry == ASSESSMENT_MAX_ATTEMPTS - 1:
                raise OrchestratorExecutionError(code=code, message=message, attempts=list(self.generation_attempts)) from error
            feedback = report

    @staticmethod
    def _collect_context_checks(source, result, report):
        """Keep existing non-segmentation checks; do not infer through invalid structure."""
        if result is None:
            report['deferred_checks'].append(dict(check='assessment_context', path='$', reason='Context validation requires a complete schema-valid assessment.', prerequisite_error_ids=[e['error_id'] for e in report['errors']]))
            return
        from fashion_recommendation_v2.agents.orchestrator_preferences import select_profile
        checks = [('preference_selection', lambda: select_profile(source.preference_profile, result))]
        intent = result.relation_intent
        if intent:
            checks.extend([('relation_source', lambda: intent.source_text in source.user_query), ('relation_anchor', lambda: not intent.anchor_item_id or intent.anchor_item_id in {r.item.item_id for r in source.reference_items}), ('relation_rank', lambda: intent.anchor_rank is None or any((r.rank == intent.anchor_rank and r.item.item_id == intent.anchor_item_id for r in source.reference_items)))])
        for name, check in checks:
            try:
                if check() is False:
                    raise ValueError(f'Invalid {name}: preserve exact request and supplied reference identity.')
            except (ValueError, TypeError) as exc:
                report['errors'].append(dict(error_id=f'error_{name}', code=name, path='$', message=str(exc)))
        if intent is None:
            return
        prerequisites = [e['error_id'] for e in report['errors'] if e['code'] != 'preference_selection']
        checks = [('similarity_assessment', validate_similarity_assessment)] if intent.relation_type == 'similarity' else [('compatibility_assessment', validate_compatibility_assessment)] if result.decision == 'proceed' else []
        for name, check in checks:
            if prerequisites:
                report['deferred_checks'].append(dict(check=name, path='semantic_units', reason='Relationship routing needs valid segmentation and reference identity.', prerequisite_error_ids=prerequisites))
                continue
            try:
                check(source, result)
            except (ValueError, TypeError) as exc:
                report['errors'].append(dict(error_id=f'error_{name}', code=name, path='relation_intent', message=str(exc)))

    def classify(self, input_data):
        from fashion_recommendation_v2.schemas.conversation import ConversationInput
        from fashion_recommendation_v2.schemas.conversation import ConversationDecision
        from fashion_recommendation_v2.prompts.conversation import CONVERSATION_PROMPT
        source = ConversationInput.model_validate_json(input_data.model_dump_json())
        self.generation_attempts = []
        for retry in range(2):
            try:
                result = self.llm.generate(system_prompt=CONVERSATION_PROMPT, user_input=source.model_copy(deep=True), output_schema=ConversationDecision)
                result = ConversationDecision.model_validate_json(result.model_dump_json())
                if source.confirmed_kind and result.kind != source.confirmed_kind:
                    raise ValueError('Explicit relationship confirmation must be respected')
                if result.kind == 'new' and result.effective_query != source.user_query:
                    raise ValueError('New request must preserve original query')
                if result.kind != 'new' and source.previous_query is None:
                    raise ValueError('Followup/ambiguity requires previous context')
            except Exception as exc:
                self.generation_attempts.append(dict(retry_count=retry, status='error', code='conversation_error', error_type=type(exc).__name__, message=str(exc)))
                if retry == 1:
                    raise OrchestratorExecutionError(code='conversation_error', message=str(exc), attempts=list(self.generation_attempts)) from exc
                source.validation_feedback = ['Respect confirmed relationship and exact new query; resolve only supplied context.']
            else:
                self.generation_attempts.append(dict(retry_count=retry, status='success'))
                return result
