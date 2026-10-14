"""Runtime processor with existing cost ledger and expiring attempt reports."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fashion_recommendation_v2.llm.cost_tracking import record_run_costs
from fashion_recommendation_v2.storage import UserUnavailable
from fashion_recommendation_v2.agents.preference_brain import PreferenceBrain
from fashion_recommendation_v2.agents.preference_runner import PreferenceRunner


class PreferenceAgent:
    def __init__(self, llm, service, config=None, *, version='v0'):
        from fashion_recommendation_v2.preference.contracts import get_contract
        get_contract(version)
        self.llm, self.service, self.config = llm, service, config
        self.version = version

    def __call__(self, source):
        if self.version in {'v1', 'v2', 'v3', 'v4'}:
            from fashion_recommendation_v2.agents.preference_interpretation_runner import PreferenceAgent as InterpretationPreferenceAgent
            runner=InterpretationPreferenceAgent(self.llm,self.config,clock=self.service.clock,version=self.version)
        else:
            if source.previous_profile and source.previous_profile.schema_version != '1.0':
                raise ValueError('Cannot overwrite v1 using the v0 processor')
            runner=PreferenceRunner(PreferenceBrain(self.llm),self.config)
        run_id=uuid4().hex
        with TemporaryDirectory(prefix='preference-') as temporary:
            folder=Path(temporary)
            try:
                with record_run_costs(folder,run_id):
                    return runner(source)
            finally:
                files={'attempts.json':json.dumps(runner.attempts,ensure_ascii=False,indent=2).encode()}
                if self.version in {'v1', 'v2', 'v3', 'v4'}:
                    files['prepared_input.json']=json.dumps(runner.prepared,ensure_ascii=False,indent=2).encode()
                    files['manifest.json']=json.dumps(runner.manifest,ensure_ascii=False,indent=2).encode()
                cost=folder/'openAI_cost.json'
                if cost.exists():
                    files[cost.name]=cost.read_bytes()
                try:
                    with self.service.store() as store:
                        store.save_agent_artifacts(source.job.user_id,run_id,files,now=self.service.clock())
                except UserUnavailable:
                    pass  # Expiry must not recreate user's logs. Runtime also fences the profile commit.
