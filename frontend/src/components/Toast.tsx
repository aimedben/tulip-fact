import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Icon } from "./Icon";

type ToastTone = "success" | "error" | "info" | "warning";
interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const ToastContext = createContext<{
  show: (message: string, tone?: ToastTone) => void;
}>({ show: () => undefined });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const show = useCallback((message: string, tone: ToastTone = "info") => {
    const id = Date.now() + Math.random();
    setItems((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => {
      setItems((current) => current.filter((item) => item.id !== id));
    }, 5500);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={`toast toast-${item.tone}`}>
            <Icon name={item.tone === "error" ? "alert" : item.tone === "success" ? "check" : item.tone === "warning" ? "alert" : "spark"} size={16} />
            <span>{item.message}</span>
            <button
              type="button"
              className="toast-close"
              onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}
              aria-label="Fermer"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
