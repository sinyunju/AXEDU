// 화면은 이 파일의 api만 사용합니다. 목/실서버 전환은 VITE_USE_MOCK으로 합니다.
// - 실서버: real.ts (FastAPI 백엔드, 형식 변환 포함)
// - 목: mock.ts (브라우저 localStorage)
import { config } from '../config';
import { mockApi } from './mock';
import { realApi, type Api } from './real';

export const api: Api = config.useMock ? mockApi : realApi;
export { ApiError } from './http';
export type * from './types';
