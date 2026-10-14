import type { API, Auth, Event, Kind, Receipt, Run, Submission } from './types';
export class APIError extends Error { constructor(public status: number, public code: string) { super(code); } }
export class LiveAPI implements API {
  private csrf = '';
  constructor(private base: string) {}
  private async post<T>(path: string, body: unknown, bootstrap = false, keepalive = false): Promise<T> {
    const response = await fetch(`${this.base}${path}`, {
      method: 'POST', credentials: 'include', keepalive, signal: AbortSignal.timeout(30000),
      headers: { 'Content-Type': 'application/json', ...(!bootstrap ? {'X-CSRF-Token': this.csrf} : {}) },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new APIError(response.status, data.error || 'unknown');
    return data;
  }
  async profileUpdatesEnabled() {
    const response = await fetch(`${this.base}/health`, {signal: AbortSignal.timeout(10000), cache: 'no-store'});
    if (!response.ok) throw new APIError(response.status, 'health_unavailable');
    const health = await response.json();
    return health.processor_connected === true && health.scheduler_running === true;
  }
  async bootstrap() { const auth = await this.post<Auth>('/api/preference/bootstrap', {}, true); this.csrf = auth.csrf_token; return auth; }
  submit(body: Submission) { return this.post<Run>('/api/recommendations', body); }
  status(request_id: string) { return this.post<Run>('/api/recommendations/status', {request_id}); }
  confirm(request_id: string, kind: Kind) { return this.post<Run>('/api/recommendations/confirm', {request_id, kind}); }
  event(body: Event) { return this.post<Receipt>('/api/preference/events', body); }
  end(session_id: string) { return this.post('/api/preference/sessions/end', {session_id}, false, true); }
}
export function errorMessage(error: unknown) {
  if (error instanceof APIError) {
    if (error.code === 'quick_start_data_unavailable') return '빠른 시작에 필요한 프로필 또는 기준 상품 데이터를 불러오지 못했어요. 저장 데이터를 확인해 주세요.';
    if (error.status === 403) return '연결 권한을 확인할 수 없어요. 허용된 프런트엔드 주소와 인증 설정을 확인해 주세요.';
    if (error.status === 409) return '요청 상태가 변경되었거나 연결 정보를 사용할 수 없어요.';
    if (error.status === 422) return '입력 정보를 확인해 주세요.';
    if (error.status === 503) return '지금은 서버를 사용할 수 없어요. 잠시 후 다시 시도해 주세요.';
  }
  return '서버와 연결하지 못했어요. 이미 접수된 작업은 계속 진행될 수 있어요.';
}
