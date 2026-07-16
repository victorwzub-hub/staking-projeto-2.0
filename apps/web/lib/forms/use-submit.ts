"use client";

import { useCallback, useState } from "react";

export function useSubmit<T>() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [data, setData] = useState<T | null>(null);

  const run = useCallback(
    async (operation: () => Promise<T>) => {
      if (pending) return null;
      setPending(true);
      setError(null);
      try {
        const result = await operation();
        setData(result);
        return result;
      } catch (reason) {
        setError(reason as Error);
        return null;
      } finally {
        setPending(false);
      }
    },
    [pending],
  );

  const reset = useCallback(() => {
    setError(null);
    setData(null);
  }, []);

  return { pending, error, data, run, reset };
}
