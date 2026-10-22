"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_brain ----

from fashion_recommendation_v2.prompts.preference import PREFERENCE_PROMPT
from fashion_recommendation_v2.schemas.preference_agent import PreferenceBatchOutput

@_preserve_class('PreferenceBrain', 'fashion_recommendation_v2.agents.preference_brain')
class PreferenceBrain:

    def __init__(self, llm):
        self.llm = llm

    def analyze(self, request):
        # Deliberately no image attachment; reuse Ranking observations as text.
        return self.llm.generate(system_prompt=PREFERENCE_PROMPT, user_input=request, output_schema=PreferenceBatchOutput)
