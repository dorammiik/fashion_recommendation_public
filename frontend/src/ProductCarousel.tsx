import { Children, useEffect, useRef, useState, type ReactNode } from 'react';

export function ProductCarousel({children}: {children: ReactNode}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({previous: false, next: false});
  const count = Children.count(children);
  useEffect(() => {
    const element = viewport.current!;
    const update = () => setEdges({previous: element.scrollLeft > 2, next: element.scrollLeft < element.scrollWidth - element.clientWidth - 2});
    update();
    element.addEventListener('scroll', update, {passive: true});
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => { element.removeEventListener('scroll', update); observer.disconnect(); };
  }, [count]);
  const slide = (direction: number) => {
    const element = viewport.current!;
    const card = element.firstElementChild as HTMLElement | null;
    if (!card) return;
    const gap = parseFloat(getComputedStyle(element).columnGap) || 0;
    const step = card.getBoundingClientRect().width + gap;
    const visible = Math.max(1, Math.floor((element.clientWidth + gap + 1) / step));
    const target = (Math.round(element.scrollLeft / step) + direction * visible) * step;
    element.scrollTo({left: Math.max(0, Math.min(target, element.scrollWidth - element.clientWidth)),
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  };
  return <div className="product-carousel">
    <div className="carousel" ref={viewport} aria-label="추천 상품 목록" tabIndex={0}>{children}</div>
    <button type="button" className="carousel-arrow carousel-next" aria-label="다음 상품 보기" hidden={!edges.next} onClick={() => slide(1)}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5m7-7-7 7 7 7"/></svg>
    </button>
    <button type="button" className="carousel-arrow carousel-previous" aria-label="이전 상품 보기" hidden={!edges.previous} onClick={() => slide(-1)}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14m-7-7 7 7-7 7"/></svg>
    </button>
  </div>;
}
