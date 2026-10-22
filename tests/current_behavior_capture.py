"""Isolated offline capture of synthetic service cases; never calls external APIs."""
from pathlib import Path
import sys,json,socket,uuid,copy,gzip
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('offline'))
uuid.uuid4=lambda:uuid.UUID(int=1)
from importlib import import_module as raw_import
try:
 from fashion_recommendation_v2.module_compat import import_module
except ImportError:import_module=raw_import
from fashion_recommendation_v2.agents.ranking_runner import RankingRunner
from fashion_recommendation_v2.agents.relation import RelationAgent
Input=import_module('fashion_recommendation_v2.schemas.ranking_v12').RankingAgentInputV12
Assessment=import_module('fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v16').PreferenceAssessmentV16
RelationInput=import_module('fashion_recommendation_v2.schemas.relation').RelationAgentInput
D=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/role_synthetic_input.json.gz').read_bytes()).decode());out={}
class Brain:
 def __init__(self,fail=False):self.calls=0;self.fail=fail
 def request_profile_lookup(self):return {'tool':'lookup_preference_profile','arguments':{}}
 def assess_preference(self,source):
  self.calls+=1
  if self.fail:raise ValueError('synthetic failure')
  rows=[dict(interpretation_id=x['interpretation_id'],judgment='not_applicable',reason_code='out_of_scope',product_evidence_refs=[],explanation='Synthetic scope mismatch') for x in source.frozen_profile['interpretations']]
  return Assessment(item_id=source.item_id,interpretation_assessments=rows,overall_fit='undetermined',assessment_confidence='low',explanation='Synthetic response')
for mode in ['cold','warm']:
 for relation in ['similarity','none']:
  for profile in ['available','not_found','failed']:
   data=copy.deepcopy(D['ranking'] if relation=='similarity' else D['ranking_no_relation']);data['personalization_mode']=mode
   brain=Brain(fail=profile=='failed');runner=RankingRunner(brain=brain,policy_version='ranking_eval_v17',profile_lookup=lambda:copy.deepcopy(D['profile']) if profile!='not_found' else {'status':'not_found'})
   key=f'ranking/{mode}/{relation}/{profile}'
   try:out[key]={'output':runner.run(Input.model_validate(data)).model_dump(mode='json'),'calls':brain.calls}
   except Exception as e:out[key]={'error_type':type(e).__name__,'message':str(e),'calls':brain.calls}
class LLM:
 def __init__(self,mode):self.mode=mode;self.calls={}
 def generate(self,**kw):
  item=kw['user_input'].items[0].item_id;count=self.calls.get(item,0);self.calls[item]=count+1
  raw=copy.deepcopy(D['relation_response']);raw['evaluations']=[e for e in raw['evaluations'] if e['item_id']==item]
  if self.mode=='fail' or self.mode=='repair' and count==0:
   exc=ValueError('synthetic relation failure');exc.response_snapshot={'model_response':raw,'model_response_text':json.dumps(raw)};raise exc
  # v9 accepts the saved image material observation; v8 used metadata only.
  for row in raw['evaluations']:
   for criterion in row['criteria']:
    for facet in criterion['facets']:
     if facet['facet']=='material':
      for side in ('anchor_evidence','candidate_evidence'):
       facet[side]=[ref.replace('.metadata','.image_observation') for ref in facet[side]]
  result=kw['output_schema'].model_validate(raw);result._model_response=raw;result._model_response_text=json.dumps(raw);return result
for mode in ['success','repair','fail']:
 data=copy.deepcopy(D['relation']);data['evaluation_version']='v9';llm=LLM(mode)
 try:out['relation/'+mode]={'output':RelationAgent(llm=llm,version='v9',max_workers=1).run(RelationInput.model_validate(data)).model_dump(mode='json'),'calls':llm.calls}
 except Exception as e:out['relation/'+mode]={'error_type':type(e).__name__,'message':str(e),'calls':llm.calls}
# Timings are diagnostic; compare every other output field, including scores, raw responses and provenance.
def stable(value):
 if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in {'elapsed_seconds','duration_seconds','elapsed_ms','started_at','finished_at','completed_at'}}
 if isinstance(value,list):return [stable(v) for v in value]
 return value
out=stable(out);Path(sys.argv[2]).write_text(json.dumps(out,ensure_ascii=False,sort_keys=True));print({k:('output' if 'output' in v else v['error_type']) for k,v in out.items()})
