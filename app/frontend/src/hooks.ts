import { useEffect, useRef, useState } from "react";

/** 轮询 hook：active 为 true 时按 interval 拉取。 */
export function usePoll<T>(fn: () => Promise<T>, interval: number, active: boolean, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!active) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const d = await fnRef.current();
        if (alive) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
      if (alive) timer = setTimeout(tick, interval);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, interval, ...deps]);

  return { data, error, setData };
}

/** 主题默认浅色；Studio 使用独立存储键，不继承旧版可能残留的深色偏好。 */
export function useTheme() {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem("auk-studio-theme") ?? "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("auk-studio-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return { theme, setTheme };
}