"""Bounded extraction, cited-output validation and deterministic profile generation."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from collections import defaultdict
import json
import re
from time import perf_counter

from fashion_recommendation_v2.prompts.preference import PREFERENCE_PROMPT
from fashion_recommendation_v2.schemas.preference_agent import AnalysisUnit
from fashion_recommendation_v2.schemas.preference_agent import CachedAnalysis
from fashion_recommendation_v2.schemas.preference_agent import Observation
from fashion_recommendation_v2.schemas.preference_agent import PreferenceAgentConfig
from fashion_recommendation_v2.schemas.preference_agent import PreferenceBatchInput
from fashion_recommendation_v2.schemas.preference_agent import PreferenceBatchOutput
from fashion_recommendation_v2.server.preference_runtime import UpdateOutput
from fashion_recommendation_v2.storage.preference import replay_events
from fashion_recommendation_v2.agents.preference_scoring import build_evidence
from fashion_recommendation_v2.agents.preference_scoring import build_profile


class PreferenceInputTooLarge(ValueError):
    pass


class PreferenceValidationError(ValueError):
    pass


class PreferenceBudgetExhausted(RuntimeError):
    pass


from fashion_recommendation_v2.preference.observations import observations


def input_upper_bound(request):
    """Conservative UTF-8 byte bound, not a claimed exact tokenizer count.

    Includes prompt, pretty-printed input, strict schema expansion allowance and
    framing/feedback reserve. Byte-level tokenizers cannot exceed text byte count.
    """
    schema=json.dumps(PreferenceBatchOutput.model_json_schema(),ensure_ascii=False)
    return (len(PREFERENCE_PROMPT.encode())+len(request.model_dump_json(indent=2).encode())
            +2*len(schema.encode())+1024)


class PreferenceRunner:
    def __init__(self, brain, config=None):
        self.brain=brain
        self.config=config or PreferenceAgentConfig()
        self.attempts=[]

    def _request(self, units, categories):
        return PreferenceBatchInput(units=units,existing_categories=sorted(categories))

    def _pack(self, snapshots, categories):
        units=[]
        for sid,snapshot in snapshots.items():
            current=[]
            for obs in observations(snapshot):
                candidate=AnalysisUnit(unit_id=f'{sid}_{len(units)}',snapshot_id=sid,observations=current+[obs])
                if input_upper_bound(self._request([candidate],categories))>self.config.max_input_tokens:
                    if not current:
                        raise PreferenceInputTooLarge('Single observation plus required context exceeds input budget')
                    units.append(AnalysisUnit(unit_id=f'{sid}_{len(units)}',snapshot_id=sid,observations=current))
                    current=[obs]
                    if input_upper_bound(self._request([AnalysisUnit(unit_id=f'{sid}_{len(units)}',snapshot_id=sid,observations=current)],categories))>self.config.max_input_tokens:
                        raise PreferenceInputTooLarge('Atomic observation too large')
                else:
                    current.append(obs)
            units.append(AnalysisUnit(unit_id=f'{sid}_{len(units)}',snapshot_id=sid,observations=current))
        batches=[]; current=[]
        for unit in units:
            request=self._request(current+[unit],categories)
            if current and (len({u.snapshot_id for u in request.units})>self.config.max_items_per_batch or
                            input_upper_bound(request)>self.config.max_input_tokens):
                batches.append(self._request(current,categories));current=[]
            current.append(unit)
        if current:
            batches.append(self._request(current,categories))
        return batches

    @staticmethod
    def validate(request, output):
        output=PreferenceBatchOutput.model_validate_json(output.model_dump_json())
        if len(output.units)!=len(request.units) or {u.unit_id for u in output.units}!={u.unit_id for u in request.units}:
            raise PreferenceValidationError('Return exactly one result per input unit')
        originals={u.unit_id:u for u in request.units}
        for result in output.units:
            refs={o.observation_id:o for o in originals[result.unit_id].observations}
            if result.category is not None:
                if result.category == 'global' or not re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)*',result.category):
                    raise PreferenceValidationError('Invalid category identifier')
                if not result.category_observation_ids or not set(result.category_observation_ids)<=refs.keys():
                    raise PreferenceValidationError('Category requires input citations')
            elif result.category_observation_ids:
                raise PreferenceValidationError('Null category must have no category citations')
            keys=set()
            for f in result.features:
                if not set(f.observation_ids)<=refs.keys():
                    raise PreferenceValidationError('Unknown feature citation')
                if (f.attribute=='detail') != (f.detail_key is not None):
                    raise PreferenceValidationError('Only detail requires key')
                if f.detail_key and not re.fullmatch(r'[a-z][a-z0-9_]*',f.detail_key):
                    raise PreferenceValidationError('Invalid detail key')
                if not f.value.strip() or f.value!=f.value.strip():
                    raise PreferenceValidationError('Blank/untrimmed feature')
                if f.attribute=='category_path' and not any(refs[r].field=='category_path' and refs[r].text==f.value for r in f.observation_ids):
                    raise PreferenceValidationError('Preserve exact category path')
                if f.attribute=='material' and all(refs[r].field.startswith('image:') for r in f.observation_ids):
                    raise PreferenceValidationError('No material composition from visuals')
                key=(f.attribute,f.detail_key,f.value.casefold())
                if key in keys:
                    raise PreferenceValidationError('Duplicate feature')
                keys.add(key)
            keys=set()
            for k in result.keywords:
                if not k.observation_ids or not set(k.observation_ids)<=refs.keys():
                    raise PreferenceValidationError('Unknown keyword citation')
                if not any(refs[r].field=='title' and k.original in refs[r].text for r in k.observation_ids):
                    raise PreferenceValidationError('Keyword must quote title')
                if k.normalized in keys or not k.normalized.strip():
                    raise PreferenceValidationError('Duplicate/blank keyword')
                keys.add(k.normalized)
        return output

    @staticmethod
    def validate_categories(request, output, accepted):
        # Only fragments of the SAME snapshot must agree. A marketplace path
        # can contain multiple garment types and is not a canonical category.
        by_snapshot = {sid: list(entries) for sid, entries in accepted.items()}
        originals = {unit.unit_id: unit for unit in request.units}
        for result in output.units:
            if result.category:
                sid = originals[result.unit_id].snapshot_id
                by_snapshot.setdefault(sid, []).append((result.unit_id, result.category))
        for sid, entries in by_snapshot.items():
            if len({category for _, category in entries}) > 1:
                raise PreferenceValidationError(
                    'Category conflict for fragments of the same snapshot: '
                    + json.dumps({'snapshot_id': sid, 'unit_categories': entries}, ensure_ascii=False)
                    + '. Return a consistent category for this item, matching already accepted '
                    'fragments. Use null with no category citations when this fragment cannot '
                    'establish its type. Different items may have different categories even '
                    'when their eBay category_path is identical.')

    def _call(self, request, accepted=None):
        for attempt in range(self.config.max_retries+1):
            bound=input_upper_bound(request)
            if bound>self.config.max_input_tokens:
                raise PreferenceInputTooLarge('Input exceeds budget, including validation feedback')
            record={'batch':self._batches,'attempt':attempt+1,'input_token_upper_bound':bound,
                    'unit_ids':[u.unit_id for u in request.units], 'status':'started'}
            record['input']=request.model_dump(mode='json')
            self.attempts.append(record)
            started=perf_counter()
            try:
                raw=self.brain.analyze(request)
                record['output']=raw.model_dump(mode='json')
                output=self.validate(request,raw)
                self.validate_categories(request, output, accepted or {})
                record['status']='success'
                record['elapsed_seconds']=perf_counter()-started
                return output
            except Exception as exc:
                record.update(status='failed',error_type=type(exc).__name__,elapsed_seconds=perf_counter()-started)
                # Detailed validation feedback stays in user-owned artifacts and
                # model input, never in the shared log / job error_code.
                if isinstance(exc, PreferenceValidationError):
                    record['validation_error'] = str(exc)
                if attempt==self.config.max_retries:
                    exc.preference_retry_exhausted = True
                    raise
                feedback = ('Validation failed: ' + str(exc) if isinstance(exc, PreferenceValidationError)
                            else 'Previous output failed schema validation or API call. Check IDs, citations and types.')
                request=request.model_copy(update={'feedback': feedback})

    def __call__(self, source):
        self.attempts=[];self._batches=0
        cache=dict(source.analyses)
        categories=set(source.previous_profile.by_category if source.previous_profile else [])
        categories.update(a.category for a in cache.values() if a.category)
        start=source.previous_profile.processed_event_cursor if source.previous_profile else 0
        cursor=start
        pending=[(seq,e) for seq,e in source.events if start<seq<=source.job.target_cursor]
        index=0
        while index<len(pending):
            block=[]; ids=set()
            while index+len(block)<len(pending) and len(block)<self.config.max_events_per_batch:
                pair=pending[index+len(block)]
                if block and len(ids|{pair[1].item_snapshot_id})>self.config.max_items_per_batch:
                    break
                block.append(pair);ids.add(pair[1].item_snapshot_id)
            end=block[-1][0]
            effective=replay_events([e for seq,e in source.events if seq<=end])
            missing={e.item_snapshot_id:source.snapshots[e.item_snapshot_id] for e in effective if e.item_snapshot_id not in cache}
            requests=self._pack(missing,categories)
            if self._batches+len(requests)>self.config.max_batches:
                # Shrink the receipt block before deferring work, so small budgets can make progress.
                if len(block)>1:
                    block=block[:1];end=block[-1][0]
                    effective=replay_events([e for seq,e in source.events if seq<=end])
                    missing={e.item_snapshot_id:source.snapshots[e.item_snapshot_id] for e in effective if e.item_snapshot_id not in cache}
                    requests=self._pack(missing,categories)
                if self._batches+len(requests)>self.config.max_batches:
                    if cursor==start:
                        raise PreferenceBudgetExhausted('One event requires more extraction batches than permitted')
                    break
            pieces=defaultdict(list)
            for request in requests:
                # A previous batch may have introduced a reusable category.
                request=request.model_copy(update={'existing_categories':sorted(categories)})
                self._batches+=1
                accepted = {sid: [(u.unit_id, r.category) for u, r in parts if r.category]
                            for sid, parts in pieces.items()}
                output=self._call(request, accepted)
                originals={u.unit_id:u for u in request.units}
                for result in output.units:
                    unit=originals[result.unit_id]
                    pieces[unit.snapshot_id].append((unit,result))
                    if result.category:
                        categories.add(result.category)
            for sid,parts in pieces.items():
                found={r.category for _,r in parts if r.category}
                features={};keywords={};obs={};unresolved=[]
                for unit,result in parts:
                    obs.update({o.observation_id:o for o in unit.observations})
                    unresolved.extend(result.unresolved)
                    for feature in result.features:
                        key=(feature.attribute,feature.detail_key,feature.value.casefold())
                        if key in features:
                            previous=features[key]
                            feature=previous.model_copy(update={'observation_ids':sorted(set(previous.observation_ids+feature.observation_ids))})
                        features[key]=feature
                    for keyword in result.keywords:
                        keywords.setdefault(keyword.normalized,keyword)
                proposed=next(iter(found),None)
                for name,keyword in list(keywords.items()):
                    if keyword.equivalent_attribute is None:
                        equivalent=next((f.attribute for f in features.values() if f.value.casefold()==name.casefold()),None)
                        if proposed==name:
                            equivalent='category_path'
                        if equivalent:
                            keywords[name]=keyword.model_copy(update={'equivalent_attribute':equivalent})
                cache[sid]=CachedAnalysis(snapshot_id=sid,category=next(iter(found),None),
                    features=list(features.values()),keywords=list(keywords.values()),observations=list(obs.values()),unresolved=unresolved)
            cursor=end;index+=len(block)
        if cursor==start:
            raise PreferenceBudgetExhausted('No new receipt boundary processed')
        effective=replay_events([e for seq,e in source.events if seq<=cursor])
        evidence=build_evidence(effective,cache)
        # Expand image citations to the exact stored Ranking observation, never invent new ones.
        for entry in evidence:
            analysis=cache[entry.item_snapshot_id]
            if entry.attribute=='title_keywords':
                continue
            matches=[f for f in analysis.features if f.attribute==entry.attribute and
                     (f.value==entry.value if isinstance(entry.value,str) else f.detail_key==entry.value.key and f.value in entry.value.values)]
            refs={r for f in matches for r in f.observation_ids}
            for obs in analysis.observations:
                if obs.observation_id in refs and obs.field.startswith('image:'):
                    original=source.snapshots[entry.item_snapshot_id].image_observations[int(obs.field.split(':')[1])]
                    if original not in entry.image_observations:
                        entry.image_observations.append(original)
        profile=build_profile(source.job.user_id,(source.previous_profile.profile_version if source.previous_profile else 0)+1,
                              cursor,effective,evidence,now=source.as_of)
        return UpdateOutput(profile,evidence,[a for sid,a in cache.items() if sid not in source.analyses])
