// 브라우저 Web Speech API 래퍼. 크롬·엣지에서 동작합니다.
// 확정된 문장(final)이 나올 때마다 onFinal을 호출합니다. 음성 원본은 저장하지 않습니다.
import { useCallback, useEffect, useRef, useState } from 'react';

/* eslint-disable @typescript-eslint/no-explicit-any */
const SpeechRecognitionImpl: any =
  typeof window !== 'undefined'
    ? (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    : undefined;

export function useSpeechRecognition(onFinal: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const recRef = useRef<any>(null);
  const wantRef = useRef(false);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

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
        if (r.isFinal) onFinalRef.current(r[0].transcript.trim());
        else partial += r[0].transcript;
      }
      setInterim(partial);
    };
    // 크롬은 침묵이 길면 스스로 멈추므로, 켜 둔 상태면 다시 시작
    rec.onend = () => {
      if (wantRef.current) rec.start();
      else {
        recRef.current = null;
        setListening(false);
      }
    };
    recRef.current = rec;
    wantRef.current = true;
    rec.start();
    setListening(true);
  }, [supported]);

  const stop = useCallback(() => {
    wantRef.current = false;
    recRef.current?.stop();
    setInterim('');
  }, []);

  useEffect(() => stop, [stop]);

  return { supported, listening, interim, start, stop };
}
