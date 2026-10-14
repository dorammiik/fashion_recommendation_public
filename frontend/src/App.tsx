import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent, type MouseEvent } from 'react';
import { active, type Item, type Run } from './types';
import { Store } from './store';
import { HomeExamples, type QuickStart } from './HomeExamples';
import { ProductCarousel } from './ProductCarousel';
import { MockAPI, scenarios, type Scenario } from './mock';

function Icon({name}: {name: 'up' | 'down' | 'arrow' | 'external' | 'plus' | 'check'}) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{name === 'arrow' ? <path d="M12 19V5m-6 6 6-6 6 6"/> : name === 'external' ? <><path d="M14 4h6v6m0-6L10 14"/><path d="M10 5H5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1v-5"/></> : name === 'plus' ? <path d="M12 5v14M5 12h14"/> : name === 'check' ? <path d="m5 12 4 4L19 6"/> : <g transform={name === 'down' ? 'rotate(180 12 12)' : undefined}><path d="M7 10v10H3V10h4Zm0 0 5-7c2 0 2 2 1 6h6c1 0 2 1 1.7 2.2l-1.5 7A2 2 0 0 1 17.3 20H7"/></g>}</svg>;
}
const safeURL = (url: string | null) => { try { const parsed = new URL(url || ''); return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : undefined; } catch { return undefined; } };
function ItemImage({item}: {item: Item}) {
  const [failed, setFailed] = useState(false);
  return item.image_url && !failed ? <img src={item.image_url} onError={() => setFailed(true)} alt={item.title} loading="lazy" referrerPolicy="no-referrer"/> : <div className="image-empty"><span>이미지 준비 중</span><small>아래 상품 설명을 확인해 주세요</small></div>;
}
function Progress({run}: {run: Run}) {
  const stages: Record<string, string> = {search: 'eBay에서 찾는 중', relation: '상품의 조합과 유사성을 살펴보는 중', ranking: '어울리는 아이템을 비교하는 중', summary: '추천을 정리하는 중', planner: '추천 방향을 정하는 중', stylist: '스타일을 살펴보는 중', request_assessment: '원하는 조건을 살펴보는 중'};
  const title = run.status === 'queued' ? '추천을 기다리는 중' : run.status === 'classifying' ? '요청을 살펴보는 중' : stages[run.progress.stage || ''] || '추천을 준비하는 중';
  return <section className="progress" role="status"><div className="progress-heading"><span className="spinner"/>{title}</div><p>조금만 기다려 주세요. 원하는 조건에 맞춰 살펴보고 있어요.</p><div className="progress-meta">{run.progress.completed_searches !== undefined && <span>검색 {run.progress.completed_searches}회 완료</span>}{run.progress.completed_batches !== undefined && run.progress.total_batches !== undefined && <span>상품 비교 {run.progress.completed_batches} / {run.progress.total_batches} 묶음</span>}</div>{run.updated_at && <small>마지막 상태 갱신 {new Date(run.updated_at).toLocaleTimeString('ko-KR')}</small>}</section>;
}
export function App({store, mock}: {store: Store; mock?: MockAPI}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  // Submitted mode belongs to each request; do not derive old badges from the current toggle.
  const [profileMode, setProfileMode] = useState<'cold' | 'warm'>(mock && new URLSearchParams(location.search).get('profile') === 'warm' ? 'warm' : 'cold');
  const [query, setQuery] = useState(''); const [scenario, setScenario] = useState<Scenario>('normal');
  const input = useRef<HTMLTextAreaElement>(null); const latest = useRef<HTMLElement>(null);
  const profileUpdating = !mock && state.ready && state.profileUpdatesEnabled;
  const current = state.turns.at(-1)?.run;
  const inProgress = active(current) || current?.status === 'awaiting_confirmation';
  const pending = state.pending; const disabled = !state.ready || state.busy || !!pending || inProgress;
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const suggestions = current?.status === 'completed' && current.response?.recommendations?.length
    ? current.response.next_recommendation || [] : [];
  const suggestionKey = JSON.stringify(suggestions);
  useEffect(() => {
    setSuggestionIndex(0);
    if (disabled || query.length > 0 || suggestions.length !== 2) return;
    const timer = window.setInterval(() => setSuggestionIndex(index => (index + 1) % 2), 3000);
    return () => window.clearInterval(timer);
  }, [current?.request_id, disabled, query, suggestionKey]);
  const hasConversation = state.turns.length > 0 || pending?.type === 'submit';
  useEffect(() => { void store.init(); return () => store.dispose(); }, [store]);
  useEffect(() => { if (current?.request_id) { setQuery(''); latest.current?.scrollIntoView({behavior: 'smooth', block: 'start'}); } }, [current?.request_id]);
  useEffect(() => { if (!hasConversation) { setQuery(''); input.current?.focus(); } }, [hasConversation]);
  const goHome = () => {
    if ((active(current) || pending?.type === 'submit' || (pending?.type === 'confirm' && state.busy)) &&
      !window.confirm('추천을 진행 중이에요. 홈으로 돌아갈까요?\n진행 중인 추천은 서버에서 계속 처리될 수 있어요.')) return false;
    store.goHome();
    setQuery(''); setProfileMode('cold');
    window.scrollTo({top: 0, behavior: 'instant'});
    return true;
  };
  const switchMode = (event: MouseEvent<HTMLAnchorElement>, target: 'mock' | 'live') => {
    // Opening a second tab leaves this screen's session intact.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!goHome()) { event.preventDefault(); return; }
    try { sessionStorage.setItem('fashion.ui.mode-entry', target); } catch { /* Navigation still works. */ }
  };
  const startQuick = (example: QuickStart) => {
    if (disabled || hasConversation) return;
    setQuery(example.request);
    setProfileMode(example.mode);
    void store.submit(example.request, example.mode, example.id);
  };
  const submit = (e: FormEvent) => { e.preventDefault(); if (disabled || !query.trim()) return; void store.submit(query, profileMode); };
  const link = (item: Item, snapshot?: string, card = false) => {
    const href = safeURL(item.item_web_url);
    return href ? <a className={card ? 'card-link' : 'text-link'} href={href} target="_blank" rel="noopener noreferrer" onClick={() => {if (snapshot) void store.click(snapshot);}}>{card ? `${item.rank}번 추천 아이템 바로가기` : '상품 바로가기'}<Icon name="external"/></a> : <span className={card ? 'card-link unavailable' : 'muted'}>상품 링크가 없어요</span>;
  };
  const result = (run: Run) => {
    const response = run.response; const items = [...(response?.recommendations || [])].sort((a,b) => a.rank-b.rank);
    const snapshot = (item: Item) => run.item_snapshots.find(s => s.item_id === item.item_id)?.item_snapshot_id;
    return <div className={`results${items.length === 0 ? ' results-empty' : ''}`}>
      <div className="result-copy result-lead">
        {response?.intro && <p className="intro">{response.intro}</p>}
        {items.length === 0 && !response?.remarks && <div className="empty-state"><span>아직 맞는 아이템을 찾지 못했어요.</span><p>옷의 종류나 원하는 조건을 바꿔서 다시 알려주세요.</p></div>}
      </div>
      {items.length > 0 && <ProductCarousel>{items.map(item => {
        const kind = run.final_ranking?.ranked_items.some(row => row.item_id === item.item_id) ? run.final_ranking.personalization_v12.selection[item.item_id]?.kind : undefined;
        const badge = kind ? {personalized: '취향 반영', nonpersonalized_supplement: '취향 미반영', nonpersonalized: '취향 미반영'}[kind] : undefined;
        const sid = snapshot(item); const selected = sid ? state.reactions[sid]?.action : undefined;
        const locked = !sid || !state.ready || state.busy || (sid ? state.sending.includes(sid) || !!state.events[sid] : false);
        return <article className="product" key={item.item_id}><div className="product-image"><ItemImage item={item}/><span className="rank">{String(item.rank).padStart(2, '0')}</span><div className="reactions">{(['like','dislike'] as const).map(action => <button key={action} type="button" className={`reaction ${selected === action ? 'selected' : ''}`} aria-label={`${item.rank}번 상품 ${action === 'like' ? '좋아요' : '싫어요'}`} aria-pressed={selected === action} disabled={locked} onClick={() => sid && void store.react(sid, action)}><Icon name={action === 'like' ? 'up' : 'down'}/></button>)}</div></div><div className="product-details">{badge && <span className={`preference-badge ${kind}`} title={kind === 'personalized' ? '취향을 고려한 추천이며, 취향에 잘 맞는다는 보장은 아니에요.' : undefined}>{badge}</span>}<h3>{safeURL(item.item_web_url) ? <a className="product-title-link" href={safeURL(item.item_web_url)} target="_blank" rel="noopener noreferrer" onClick={() => {if (sid) void store.click(sid);}}>{item.title}</a> : item.title}</h3><p className="product-price">{item.price ? `${item.price.value} ${item.price.currency}` : '가격 정보 없음'}</p><p>{item.recommendation_reason}</p>{item.key_features?.length > 0 && <div className="tags">{item.key_features.map(feature => <span key={feature}>{feature}</span>)}</div>}</div>{link(item, sid, true)}{sid && state.events[sid] && !state.sending.includes(sid) && <button className="event-retry" onClick={() => void store.retryEvent(sid)}>피드백 저장 다시 시도</button>}</article>;
      })}</ProductCarousel>}
        {response?.remarks && <aside className="remarks-box" aria-label="이용 전 참고해주세요"><h3 className="remarks-heading">이용 전 참고해주세요 <span aria-hidden="true">💡</span></h3><ul className="remarks">{response.remarks.split(/\n+/).flatMap(line => Array.from(new Intl.Segmenter('ko', {granularity: 'sentence'}).segment(line), part => part.segment.trim())).filter(Boolean).map((sentence, index) => <li key={index}>{sentence}</li>)}</ul></aside>}
      <div className="result-copy">
        {(items.length > 0 || response?.remarks) && response?.outro && <p className="outro">{response.outro}</p>}
        {items.length > 0 && response?.feedback_notice && <p className="feedback-notice">{response.feedback_notice}</p>}
      </div>
    </div>;
  };
  return <div className="app">
    <header className="header">
      {hasConversation && <button type="button" className="header-new header-home" onClick={goHome}>홈 돌아가기<Icon name="plus"/></button>}
      {!hasConversation && <div className="profile-mode">
        <div className="profile-toggle" role="group" aria-label="추천 프로필 모드">
          {(['cold', 'warm'] as const).map(mode => <button type="button" key={mode} aria-pressed={profileMode === mode} onClick={() => setProfileMode(mode)}>{mode === 'cold' ? 'Cold' : 'Warm'}</button>)}
        </div>
        <p className="profile-caption" data-mode={profileMode} aria-live="polite">{profileMode === 'cold' ? '취향 정보 없이 기본 추천을 보여드려요' : '취향을 반영해 추천하고, 사용할수록 업데이트돼요'}</p>
      </div>}
      <div className="header-right"><span className={`mode-dot ${profileUpdating ? 'live updating' : ''}`} aria-hidden="true"/><span className="mode-label" role="status">{mock ? 'mock 모드' : profileUpdating ? '프로필 자동 갱신 중' : '프로필 갱신 OFF'}</span></div>
    </header>
    <main className={hasConversation ? 'conversation' : 'welcome'}>
      {!hasConversation && <div className="welcome-heading"><h1>어떤 옷을 찾고 있나요?</h1></div>}
      {state.turns.map((turn, i) => <section className="turn" key={turn.run.request_id} ref={i === state.turns.length - 1 ? latest : undefined}><div className="user-message">{turn.query}</div>
        {active(turn.run) && <Progress run={turn.run}/>}
        {turn.run.status === 'awaiting_confirmation' && <section className="confirmation"><span className="eyebrow">잠깐, 확인할게요</span><h2>{turn.run.question || '이전 추천에 이어서 찾으시는 건가요?'}</h2><p>이전 조건을 이어갈지, 새로운 조건으로 찾을지 알려주세요.</p><div className="button-row"><button className="primary" disabled={state.busy || !!pending || !state.ready} onClick={() => void store.confirm('followup')}>이어서 찾기</button><button className="secondary" disabled={state.busy || !!pending || !state.ready} onClick={() => void store.confirm('new')}>새로 찾기</button></div></section>}
        {turn.run.status === 'completed' && result(turn.run)}
        {['blocked','failed','interrupted'].includes(turn.run.status) && <section className="terminal">
          <h2>{turn.run.status === 'interrupted' ? '추천이 중단됐어요.' : ['request_assessment', 'classifying'].includes(String(turn.run.progress?.stage)) ? '요청을 해석하지 못했어요. 원하는 상품과 조건을 다시 알려주세요.' : turn.run.error_type === 'SearchPlanUnavailable' ? '검색 조건을 구성하지 못했어요.' : turn.run.error_type === 'SearchUnavailable' ? '상품 정보를 가져오지 못했어요.' : turn.run.response?.intro || '요청을 처리하지 못했어요. 다시 입력해 주세요.'}</h2>
          {turn.run.status === 'failed' && <p>{turn.run.error_type === 'SearchPlanUnavailable' ? '검색을 진행하지 못했어요. 원하는 상품 종류와 조건을 구체적으로 알려주세요.' : turn.run.error_type === 'SearchUnavailable' ? '상품 조회 중 오류가 발생했어요. 요청을 다시 입력해 주세요.' : '추천을 마치지 못했어요. 요청을 다시 입력해 주세요.'}</p>}
          {turn.run.response?.reasons?.map((reason, n) => <p key={n}>{reason.reason}</p>)}
          {turn.run.recovery_reason && <p>{turn.run.recovery_reason}</p>}
        </section>}
      </section>)}
      {pending?.type === 'submit' && <section className="turn"><div className="user-message">{pending.input.user_query}</div><p className="pending-label">{state.busy ? '요청을 접수하고 있어요…' : '접수 결과를 아직 확인하지 못했어요. 같은 요청으로 다시 확인해 주세요.'}</p></section>}
      {state.error && <div className="error-banner" role="alert"><p>{state.error}</p><button disabled={state.busy} onClick={() => void store.retry()}>{!state.ready ? '연결 다시 시도' : pending ? '같은 요청 다시 시도' : '상태 다시 확인'}</button></div>}
      {pending && !state.error && !state.busy && <div className="error-banner"><p>전송 결과 확인이 필요해요. 기존 요청으로 안전하게 다시 시도할 수 있어요.</p><button onClick={() => void store.retry()}>같은 요청 다시 시도</button></div>}
      {Object.entries(state.events).filter(([key, event]) => event.action === 'click' && !state.sending.includes(key)).map(([key]) => <div className="error-banner" key={key}><p>상품 클릭 기록을 저장하지 못했어요.</p><button onClick={() => void store.retryEvent(key)}>기록 저장 다시 시도</button></div>)}
      {hasConversation && !inProgress && !pending && <div className="new-request"><button className="primary" disabled={!state.ready || state.busy || Object.keys(state.events).length > 0} onClick={() => void store.startNew()}>새 추천 시작하기<Icon name="plus"/></button><span>새로운 조건으로 처음부터 찾아볼까요?</span></div>}
      <div className={`composer-area ${hasConversation ? 'conversation-composer' : ''}`}>

        <form className="composer" onSubmit={submit}><textarea ref={input} rows={1} aria-label="추천 요청" maxLength={12000} disabled={disabled} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); if (!disabled && query.trim()) {void store.submit(query, profileMode);}}}} placeholder={current?.status === 'awaiting_confirmation' ? '현재 검색창은 이용할 수 없어요' : inProgress ? '추천이 끝나면 이어서 이야기할 수 있어요' : hasConversation ? suggestions[suggestionIndex] || '' : '원하는 조건을 말해주시면 취향에 맞게 골라드릴게요.'}/><button className="send" type="submit" aria-label="추천 요청 전송" disabled={disabled || !query.trim()}><Icon name="arrow"/></button></form>
        {!hasConversation && <HomeExamples onStart={startQuick} disabled={!!disabled}/>}
      </div>
    </main>
    <footer className="footer">{import.meta.env.DEV && <details className="dev-panel"><summary>개발 미리보기</summary><div>{mock ? <><label>화면 시나리오<select aria-label="화면 시나리오" value={scenario} disabled={!!inProgress || state.busy || !!pending} onChange={e => {const value = e.target.value as Scenario; setScenario(value); mock.scenario = value;}}>{Object.entries(scenarios).map(([key,label]) => <option value={key} key={key}>{label}</option>)}</select></label><p>Summary v9 형식의 고정 예시입니다. 상품과 가격은 실제 검색 결과가 아니며, 시나리오는 다음 제출에 적용됩니다.</p><a href="/?mode=live" onClick={event => switchMode(event, 'live')}>실제 API 모드 열기</a><small>실제 모드에서 전송하면 유료 추천이 실행됩니다.</small></> : <><p>실제 서버 연결 모드입니다.</p><a href="/" onClick={event => switchMode(event, 'mock')}>mock 미리보기로 이동</a></>}</div></details>}</footer>
    {state.toast && <div className="toast" role="status"><Icon name="check"/>{state.toast}</div>}
  </div>;
}
