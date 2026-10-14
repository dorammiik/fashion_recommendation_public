import type { API, Event, Kind, Run, Submission } from './types';
import { APIError } from './api';
import { mockSummary } from './mockSummary';
export const scenarios = { normal: '추천 완료', confirmation: '확인 질문', empty: '빈 결과', blocked: '조건 확인 필요', failed: '추천 실패', interrupted: '서버 중단', missing: '이미지·링크 없음', no_notice: '피드백 안내 없음' };
export type Scenario = keyof typeof scenarios;
const wait = () => new Promise(resolve => setTimeout(resolve, 250));
type MockRecord = {input: Submission; run: Run; started: number; scenario: Scenario; confirmed?: Kind};
export class MockAPI implements API {
  scenario: Scenario = 'normal';
  private key = 'fashion.mock.server.v1';
  private read(): Record<string, MockRecord> { return JSON.parse(sessionStorage.getItem(this.key) || '{}'); }
  private write(records: Record<string, MockRecord>) { sessionStorage.setItem(this.key, JSON.stringify(records)); }
  async bootstrap() { await wait(); return {user_id: 'mock-user', csrf_token: 'mock-csrf', expires_at: '2099-01-01T00:00:00Z'}; }
  async submit(input: Submission) {
    await wait(); const records = this.read();
    const existing = Object.values(records).find(r => r.input.idempotency_key === input.idempotency_key);
    if (existing) { if (JSON.stringify(existing.input) !== JSON.stringify(input)) throw new APIError(409, 'invalid_state'); return this.status(existing.run.request_id); }
    const id = crypto.randomUUID();
    records[id] = {input, scenario: this.scenario, started: Date.now(), run: {request_id: id, session_id: input.previous_request_id && !input.new_request ? records[input.previous_request_id]?.run.session_id || crypto.randomUUID() : crypto.randomUUID(), status: 'queued', question: null, response: null, item_snapshots: [], error_type: null, progress: {}, updated_at: new Date().toISOString(), resumable: false, recovery_reason: null}};
    this.write(records); return records[id].run;
  }
  async status(id: string) {
    await wait(); const records = this.read(); const record = records[id];
    if (!record) throw new APIError(409, 'invalid_state');
    const elapsed = Date.now() - record.started; const run = record.run;
    if (elapsed < 600) run.status = 'queued';
    else if (elapsed < 1400) run.status = 'classifying';
    else if (record.scenario === 'confirmation' && !record.confirmed) { run.status = 'awaiting_confirmation'; run.question = '이전 추천에 이어서 찾으시는 건가요?'; }
    else if (elapsed < 3400) { run.status = 'running'; run.progress = {stage: 'search', completed_searches: 2}; }
    else {
      run.status = record.scenario === 'blocked' ? 'blocked' : record.scenario === 'failed' ? 'failed' : record.scenario === 'interrupted' ? 'interrupted' : 'completed';
      if (run.status === 'completed') {
        run.response = mockSummary(record.scenario, id, record.input.personalization_mode || 'cold');
        run.final_ranking = {ranked_items: run.response.recommendations!.map(item => ({item_id: item.item_id})),
          personalization_v12: {selection: Object.fromEntries(run.response.recommendations!.map((item,i) =>
            [item.item_id, {kind: record.input.personalization_mode === 'warm' ? (i < 2 ? 'personalized' : 'nonpersonalized_supplement') : 'nonpersonalized'}]))}};
        run.item_snapshots = run.response.recommendations!.map(item => ({item_id: item.item_id, rank: item.rank, item_snapshot_id: `${id}-${item.item_id}`}));
      } else if (run.status === 'blocked') {
        run.progress = {stage: 'stylist', status: 'blocked'};
        run.response = {response_id: `response_${id}`, status: 'blocked', intro: '찾으시는 옷의 종류를 확인하지 못해 추천을 진행하지 못했어요.',
          reasons: [{state_id: 'product_type', reason: '원피스, 셔츠, 바지처럼 찾으시는 옷의 종류를 알려주세요.'}]};
      } else if (run.status === 'failed') {
        run.progress = {stage: 'summary', status: 'error'};
        run.error_type = 'SummaryExecutionError';
        run.response = null;
      } else if (run.status === 'interrupted') {
        run.error_type = 'ServerRestarted';
        run.response = null;
        run.resumable = false;
        run.recovery_reason = '서버 재시작으로 추천이 중단됐어요. 요청을 다시 입력해 주세요. 이전 대화를 이어갈지 새로 시작할지 판단할게요.';
      }
    }
    run.updated_at = new Date().toISOString(); this.write(records); return structuredClone(run);
  }
  async confirm(id: string, kind: Kind) { await wait(); const records = this.read(); const r = records[id]; if (r.confirmed && r.confirmed !== kind) throw new APIError(409, 'invalid_state'); if (!r.confirmed) { r.confirmed = kind; r.started = Date.now(); r.run.question = null; r.run.status = 'queued'; if (kind === 'new') r.run.session_id = crypto.randomUUID(); this.write(records); } return r.run; }
  async event(event: Event) { await wait(); return {event_id: event.event_id, inserted: true, receipt_sequence: 1, profile_updated: false}; }
  async end(_id: string) { await wait(); return {queued: true, profile_updated: false}; }
}
