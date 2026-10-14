from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.prompts.preference import PREFERENCE_PROMPT
from fashion_recommendation_v2.schemas.preference_agent import PreferenceBatchOutput


class PreferenceBrain:
    def __init__(self, llm):
        self.llm = llm

    def analyze(self, request):
        # Deliberately no image attachment; reuse Ranking observations as text.
        return self.llm.generate(system_prompt=PREFERENCE_PROMPT, user_input=request,
                                 output_schema=PreferenceBatchOutput)
