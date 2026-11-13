import { useCallback, useEffect, useState } from 'react';

/** 간단한 데이터 로딩 훅. deps가 바뀌면 다시 불러옵니다. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    run()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [run]);

  useEffect(reload, [reload]);

  return { data, setData, error, loading, reload };
}
