// 브라우저 Web Speech API 래퍼. 크롬·엣지에서 동작합니다.
// 확정된 문장(final)이 나올 때마다 onFinal(text, tag)을 호출합니다. 음성 원본은 저장하지 않습니다.
//
// tag: 그 문장을 "말하기 시작했을 때" getTag()가 돌려준 값 (예: 그때 보던 페이지 번호).
//   크롬은 말이 잠깐 끊겨야 문장을 확정하므로, 확정 시점의 페이지를 쓰면
//   말하면서 다음 장으로 넘긴 경우 앞 페이지 설명이 다음 페이지로 들어간다.
// flush(): 지금까지 들은 말을 바로 확정시킨다 (페이지를 넘기기 직전에 호출).
import { useCallback, useEffect, useRef, useState } from 'react';

/* eslint-disable @typescript-eslint/no-explicit-any */
const SpeechRecognitionImpl: any =
  typeof window !== 'undefined'
    ? (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    : undefined;

// 다시 시작해도 소용없는 오류 → 멈추고 안내
const FATAL_ERRORS: Record<string, string> = {
  'not-allowed': '마이크 사용이 허용되지 않았어요. 주소창의 자물쇠 아이콘에서 마이크를 허용해 주세요.',
  'service-not-allowed': '이 브라우저에서 음성 인식을 쓸 수 없어요. 크롬을 사용해 주세요.',
  'audio-capture': '마이크를 찾을 수 없어요. 마이크 연결을 확인해 주세요.',
};

export function useSpeechRecognition<T>(onFinal: (text: string, tag: T) => void, getTag: () => T) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState('');
  const recRef = useRef<any>(null);
  const wantRef = useRef(false);
  const tagsRef = useRef(new Map<number, T>()); // result index → 말하기 시작할 때의 tag
  const flushTagRef = useRef<{ tag: T } | null>(null); // flush() 뒤 세션이 끝날 때까지 나오는 말의 tag
  const onFinalRef = useRef(onFinal);
  const getTagRef = useRef(getTag);
  onFinalRef.current = onFinal;
  getTagRef.current = getTag;

  const supported = Boolean(SpeechRecognitionImpl);

  const start = useCallback(() => {
    if (!supported || recRef.current) return;
    const rec = new SpeechRecognitionImpl();
    rec.lang = 'ko-KR';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e: any) => {
      let partial = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (!tagsRef.current.has(i)) tagsRef.current.set(i, flushTagRef.current ? flushTagRef.current.tag : getTagRef.current());
        if (r.isFinal) {
          const text = r[0].transcript.trim();
          if (text) onFinalRef.current(text, tagsRef.current.get(i) as T);
        } else partial += r[0].transcript;
      }
      setInterim(partial);
    };
    rec.onerror = (e: any) => {
      const message = FATAL_ERRORS[e.error];
      if (message) {
        wantRef.current = false; // onend에서 다시 시작하지 않음
        setError(message);
      }
      // no-speech, network, aborted 등은 onend에서 다시 시작
    };
    // 크롬은 침묵이 길거나 flush()로 멈추면 끝나므로, 켜 둔 상태면 다시 시작
    rec.onend = () => {
      tagsRef.current.clear(); // 새 세션은 result index가 0부터 다시 시작
      flushTagRef.current = null;
      setInterim('');
      if (wantRef.current) {
        try {
          rec.start();
          return;
        } catch {
          // 이미 시작됐거나 시작할 수 없는 상태 → 끔
        }
      }
      recRef.current = null;
      wantRef.current = false;
      setListening(false);
    };
    recRef.current = rec;
    wantRef.current = true;
    setError('');
    rec.start();
    setListening(true);
  }, [supported]);

  const stop = useCallback(() => {
    wantRef.current = false;
    recRef.current?.stop();
    setInterim('');
  }, []);

  /** 지금까지 들은 말을 확정시킨다. stop()하면 남은 말이 final로 나오고, onend에서 다시 시작된다. */
  // 페이지 번호를 바꾸기 *전에* 호출해야 한다: 넘기기 직전에 한 말(아직 인식 결과가 안 온 말)도 이전 tag로 간다.
  const flush = useCallback(() => {
    if (!wantRef.current || !recRef.current) return;
    if (!flushTagRef.current) flushTagRef.current = { tag: getTagRef.current() };
    recRef.current.stop();
  }, []);

  useEffect(() => stop, [stop]);

  return { supported, listening, interim, error, start, stop, flush };
}
