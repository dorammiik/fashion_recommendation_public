# Fashion Recommendation UI

```sh
npm ci
npm run dev
```

http://127.0.0.1:5173 의 기본 모드는 실제 API를 호출하지 않는 모의 데모입니다. 실제 서비스 설치와 버전 정보는 [루트 실행 안내](../README.md)를 참고하세요.

`/?mode=live`에서 로컬 서버에 연결합니다. 기본 주소는 `http://127.0.0.1:8765`이며, 변경하려면 `.env.example`을 참고해 `.env.local`의 `VITE_API_BASE_URL`을 지정합니다. API 키는 넣지 않습니다. live 모드의 유사 상품·A/B 고정 예제는 공개본에서 제외한 데이터가 필요합니다. 일반 요청을 직접 입력하세요.

`src/App.tsx`는 화면, `src/store.ts`는 요청·세션 상태, `src/api.ts`는 쿠키·CSRF API, `src/mock.ts`와 `mockSummary.ts`는 모의 응답을 담당합니다.

```sh
npm test
npm run build
```

Chrome 설치 시 `npm run test:e2e`로 모의 브라우저 테스트를 실행할 수 있습니다. `npm run check:connection`은 실행 중인 실제 로컬 서버 연결을 검사하며 별도 익명 사용자를 생성합니다.
