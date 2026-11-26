import { useEffect, useState } from "react";
import { utcMs } from "../lib/format";

/** Milliseconds remaining until ``target`` (naive-UTC ISO string or Date); updates every ``tickMs``. */
export function useCountdown(target: string | Date | null | undefined, tickMs = 1000): { ms: number; expired: boolean } {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), tickMs);
    return () => clearInterval(id);
  }, [target, tickMs]);
  const end = utcMs(target);
  const ms = Number.isNaN(end) ? 0 : Math.max(0, end - now);
  return { ms, expired: ms <= 0 };
}
