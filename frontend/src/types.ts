export type Status = 'queued' | 'classifying' | 'running' | 'awaiting_confirmation' | 'completed' | 'blocked' | 'failed' | 'interrupted';
export type Reaction = 'like' | 'dislike';
export type Kind = 'followup' | 'new';
export interface Item { rank: number; item_id: string; title: string; price?: {value: number; currency: string} | null; image_url: string | null; item_web_url: string | null; recommendation_reason: string; key_features: string[] }
export interface Response { intro: string; recommendations?: Item[]; remarks?: string; next_recommendation?: string[]; outro?: string; feedback_notice?: string | null; status?: 'blocked'; reasons?: {state_id?: string; reason: string}[]; response_id?: string }
export interface Run { final_ranking?: RankingSelection; request_id: string; session_id: string | null; status: Status; question: string | null; response: Response | null; item_snapshots: {item_id: string; rank: number; item_snapshot_id: string}[]; error_type: string | null; progress: {stage?: string; status?: string; completed_searches?: number; completed_batches?: number; total_batches?: number}; updated_at: string | null; resumable: boolean; recovery_reason: string | null }
export type QuickStartID = 'complex' | 'similar' | 'profile_a' | 'profile_b';
export interface Submission { quick_start?: QuickStartID; personalization_mode?: 'cold' | 'warm'; user_query: string; idempotency_key: string; new_request: boolean; previous_request_id?: string }
export interface Event { event_id: string; item_snapshot_id: string; action: Reaction | 'click'; operation: 'record' | 'cancel' | 'correct'; target_event_id?: string; occurred_at: string }
export interface Auth { user_id: string; csrf_token: string; expires_at: string }
export interface Receipt { event_id: string; inserted: boolean; receipt_sequence: number; profile_updated: boolean }
export interface API { profileUpdatesEnabled?(): Promise<boolean>; bootstrap(): Promise<Auth>; submit(input: Submission): Promise<Run>; status(id: string): Promise<Run>; confirm(id: string, kind: Kind): Promise<Run>; event(input: Event): Promise<Receipt>; end(id: string): Promise<unknown> }
export const active = (run?: Run) => !!run && ['queued', 'classifying', 'running'].includes(run.status);

export type SelectionKind = 'personalized' | 'nonpersonalized_supplement' | 'nonpersonalized';
export interface RankingSelection { ranked_items: {item_id: string}[]; personalization_v12: {selection: Record<string, {kind: SelectionKind}>} }
