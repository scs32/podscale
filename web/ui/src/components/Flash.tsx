import { useCallback, useEffect, useRef, useState } from "react";
import { Alert } from "./Alert";

// Self-resolving action feedback: success messages dismiss themselves after
// a few seconds; errors persist until closed. Replaces the bare Alert-with-
// useState pattern that left banners on screen forever.

export interface FlashMsg {
  kind: "ok" | "err";
  text: string;
}

const OK_TTL_MS = 5000;

export function useFlash(): {
  flash: FlashMsg | null;
  show: (msg: FlashMsg) => void;
  clear: () => void;
} {
  const [flash, setFlash] = useState<FlashMsg | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setFlash(null);
  }, []);

  const show = useCallback((msg: FlashMsg) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setFlash(msg);
    if (msg.kind === "ok") {
      timer.current = setTimeout(() => setFlash(null), OK_TTL_MS);
    }
  }, []);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { flash, show, clear };
}

export function FlashView({
  flash,
  onClose,
}: {
  flash: FlashMsg | null;
  onClose: () => void;
}) {
  if (!flash) return null;
  return (
    <div className="flash" style={{ marginTop: "var(--sp-5)" }}>
      <Alert kind={flash.kind}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--sp-3)" }}>
          <div style={{ flex: 1 }}>{flash.text}</div>
          <button className="flash__close" aria-label="Dismiss" onClick={onClose}>
            ×
          </button>
        </div>
      </Alert>
    </div>
  );
}
