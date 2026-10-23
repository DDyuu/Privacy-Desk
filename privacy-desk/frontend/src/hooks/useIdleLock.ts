import { useEffect, useRef } from "react";

const ACTIVITY_EVENTS: Array<keyof WindowEventMap> = ["mousemove", "keydown", "click", "scroll"];

/**
 * 空闲自动锁定：timeout 毫秒内无鼠标/键盘/滚动操作时触发 onIdle。
 * 仅在 enabled 为 true（已解锁）时生效。
 */
export function useIdleLock(timeout: number, onIdle: () => void, enabled = true) {
  const onIdleRef = useRef(onIdle);
  onIdleRef.current = onIdle;

  useEffect(() => {
    if (!enabled) return;

    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => onIdleRef.current(), timeout);
    };

    const listener = () => reset();
    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, listener, { passive: true }),
    );
    reset();

    return () => {
      clearTimeout(timer);
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, listener));
    };
  }, [timeout, enabled]);
}
