"""Single interpretation stage with bounded correction, no feature-extraction call."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from time import perf_counter
from uuid import uuid4
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationConfig
from fashion_recommendation_v2.preference.interpretation_input import prepare_input
from fashion_recommendation_v2.preference.interpretation_sources import fingerprint
from fashion_recommendation_v2.preference.interpretation_sources import validate_references
from fashion_recommendation_v2.server.preference_runtime import UpdateOutput


class PreferenceAgent:
    def __init__(self, llm, config=None, clock=None, *, version='v1'):
        from fashion_recommendation_v2.module_compat import import_module
        from fashion_recommendation_v2.preference.contracts import get_contract
        if version not in {'v1', 'v2', 'v3', 'v4'}:
            raise ValueError('Unsupported interpretation version')
        self.version = version
        self.contract = get_contract(version)
        schema_path, profile_name = self.contract['schema'].rsplit('.', 1)
        self.schema = import_module('fashion_recommendation_v2.' + schema_path)
        self.profile_schema = getattr(self.schema, profile_name)
        prompt_path, prompt_name = self.contract['prompt'].rsplit('.', 1)
        from fashion_recommendation_v2.prompts._compat import resolve_prompt_module
        self.prompt = getattr(resolve_prompt_module('fashion_recommendation_v2.' + prompt_path), prompt_name)
        self.llm = llm
        self.config = config or InterpretationConfig()
        self.clock = clock
        self.attempts = []
        self.prepared = None
        self.manifest = None

    def __call__(self, source):
        if source.previous_profile and source.previous_profile.schema_version == '3.0' and self.version == 'v1':
            raise ValueError('Cannot downgrade a v2 profile using v1')
        if source.previous_profile and getattr(source.previous_profile, 'interpretation_version', None) == 'preference-interpretation-v3' and self.version not in {'v3', 'v4'}:
            raise ValueError('Cannot downgrade a v3 profile')
        if source.previous_profile and getattr(source.previous_profile, 'interpretation_version', None) == 'preference-interpretation-v4' and self.version != 'v4':
            raise ValueError('Cannot downgrade a v4 profile')
        request, cursor = prepare_input(source, version=self.version)
        self.prepared = request.model_dump(mode='json')
        self.manifest = dict(version=self.version, input_policy=self.contract['input_policy'],
            input_sha256=fingerprint(self.prepared), cache_used=False,
            as_of=source.as_of.isoformat(), target_cursor=cursor,
            prompt_sha256=fingerprint(self.prompt),
            schema_sha256=fingerprint(self.schema.InterpretationOutput.model_json_schema()))
        self.manifest['config'] = self.config.model_dump(mode='json')
        self.manifest['model'] = getattr(self.llm,'model',None)
        from hashlib import sha256
        from pathlib import Path
        import inspect
        from fashion_recommendation_v2.preference import interpretation_sources
        from fashion_recommendation_v2.preference import interpretation_input
        paths = [Path(__file__), Path(inspect.getfile(self.schema.InterpretationOutput)),
                 Path(interpretation_sources.__file__), Path(interpretation_input.__file__)]
        if self.version in {'v2', 'v3', 'v4'}:
            from fashion_recommendation_v2.preference import interpretation_attributes
            paths.append(Path(interpretation_attributes.__file__))
        self.manifest['code_hashes'] = {str(p):sha256(p.read_bytes()).hexdigest() for p in paths}
        for attempt in range(self.config.max_retries+1):
            # Explicit full-history byte budget; same correction ceiling as v0.
            bound = (len(request.model_dump_json().encode()) + len(self.prompt.encode())
                     + 2*len(str(self.schema.InterpretationOutput.model_json_schema()).encode()) + 1024)
            if bound > self.config.max_input_bytes:
                raise ValueError(f'Preference {self.version} input exceeds byte budget ({bound}>{self.config.max_input_bytes}); no partial profile published')
            record = dict(attempt=attempt+1, input=request.model_dump(mode='json'),
                          input_bytes_with_allowance=bound, status='started')
            self.attempts.append(record)
            start = perf_counter()
            try:
                raw = self.llm.generate(system_prompt=self.prompt,
                                       user_input=request, output_schema=self.schema.InterpretationOutput)
                record['model_response'] = getattr(raw, '_model_response', None)
                record['model_response_text'] = getattr(raw, '_model_response_text', None)
                record['parsed_response'] = raw.model_dump(mode='json')
                output = self.schema.InterpretationOutput.model_validate_json(raw.model_dump_json())
                validate_references(output.interpretations, request.evidence, request.categories)
                record.update(status='success', code_validation=dict(status='passed', errors=[]))
                break
            except Exception as exc:
                record.update(getattr(exc, 'response_snapshot', None) or {})
                record.update(status='failed', code_validation=dict(status='failed', errors=[str(exc)]))
                if attempt == self.config.max_retries:
                    exc.preference_retry_exhausted = True
                    raise
                request = request.model_copy(update={'feedback': 'Correct the same output contract: '+str(exc)})
            finally:
                record['elapsed_seconds'] = perf_counter()-start
        profile = self.profile_schema(user_id=source.job.user_id,
            profile_version=(source.previous_profile.profile_version if source.previous_profile else 0)+1,
            updated_at=self.clock() if self.clock else source.as_of, as_of=source.as_of,
            processed_event_cursor=cursor,
            interpretations=[self.schema.StoredInterpretation(**i.model_dump(), interpretation_id='i_'+uuid4().hex)
                             for i in output.interpretations], summary=output.summary)
        return UpdateOutput(profile, request.evidence, [])


# Preserve imports used by existing callers and evaluation scripts.
PreferenceInterpretationRunner = PreferenceAgent
