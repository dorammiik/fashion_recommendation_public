import { useState } from 'react';
import type { QuickStartID } from './types';

export interface QuickStart { id: QuickStartID; mode: 'cold' | 'warm'; request: string }
const examples: (QuickStart & {icon: string; title: string; description?: string})[] = [
  {
    mode: 'cold', icon: '🪡', title: '복잡한 조건으로 찾기', id: 'complex',
    request: '페스티벌에 입고 가기 좋은 꽃무늬 드레스 추천해줘. 투피스로 된 것도 괜찮은데 바지는 별로야. 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어',
  },
  {
    mode: 'cold', icon: '📩', title: '이전 추천과 비슷하게', id: 'similar',
    request: '이전 추천 1번과 비슷한 원피스 찾아줘',
    description: '이전 추천 1번은 검은색 바탕에 분홍색과 흰색 꽃무늬가 있는 롱 원피스예요. 발목까지 오는 길이예요.',
  },
  {
    mode: 'warm', icon: '👩🏻', title: '사용자 A 취향으로', id: 'profile_a',
    request: '주말에 편하게 입을 티셔츠 찾아줘',
    description: 'A : 직장 여성, 여, 30대, 단정한 오피스룩을 선호하고 와이드 팬츠와 민소매 상의에 관심이 있는 편이에요.',
  },
  {
    mode: 'warm', icon: '👨🏻', title: '사용자 B 취향으로', id: 'profile_b',
    request: '주말에 편하게 입을 티셔츠 찾아줘',
    description: 'B : 개발자, 남, 30대, 그래픽 티셔츠와 체크 셔츠같은 편안한 스타일을 선호하는 편이에요.',
  },
];

// Original image of the fixed RS001 anchor in evals/relation/case_plan_v3.json.
const anchorImage = 'https://i.ebayimg.com/images/g/ZqQAAeSwQKxpzSqq/s-l1600.jpg';
function AnchorPreview() {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  return <span className="anchor-info" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
    <button type="button" className="anchor-info-button" aria-label="이전 추천 1번 이미지 보기" aria-expanded={open} aria-controls="quick-start-anchor-preview"
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen(true)} onKeyDown={event => {if (event.key === 'Escape') {event.stopPropagation(); setOpen(false);}}}>
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="8" fill="currentColor"/><path d="M10 9v5" stroke="#fff" strokeWidth="1.5" strokeLinecap="round"/><circle cx="10" cy="6" r="1" fill="#fff"/></svg>
    </button>
    {open && <span className="anchor-preview" id="quick-start-anchor-preview" role="tooltip">
      {failed ? <span>기준 상품 이미지를 불러오지 못했어요.</span> : <img src={anchorImage} alt="이전 추천 1번: 검은 바탕에 분홍색과 흰색 꽃무늬가 있는 롱 원피스" referrerPolicy="no-referrer" onError={() => setFailed(true)}/>}
      <span className="anchor-preview-caption">이전 추천 1번 · 기준 상품</span>
    </span>}
  </span>;
}

export function HomeExamples({onStart, disabled}: {onStart: (example: QuickStart) => void; disabled: boolean}) {
  return <section className="home-examples" aria-labelledby="home-examples-heading">
    <h2 id="home-examples-heading">준비된 예시로 빠르게 확인해보세요</h2>
    <div className="home-example-grid">
      {examples.map(example => <article className="home-example-card" key={example.title}>
        <button type="button" className="quick-start-trigger" aria-label={example.title} disabled={disabled} onClick={() => onStart(example)}/>
        <span className={`home-example-mode ${example.mode}`}>{example.mode}</span>
        <h3><span aria-hidden="true">{example.icon}</span> {example.title}</h3>
        <p className="home-example-request">{example.request}</p>
        {example.description && <p className="home-example-description">{example.description}{example.id === 'similar' && <AnchorPreview/>}</p>}
      </article>)}
    </div>
  </section>;
}
