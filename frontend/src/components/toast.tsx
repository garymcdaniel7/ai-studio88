"use client";
import { useState, useEffect, createContext, useContext, useCallback } from "react";
import { X, CheckCircle2, AlertCircle, Info } from "lucide-react";

interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}

const ToastContext = createContext<{ show: (message: string, type?: Toast["type"]) => void }>({ show: () => {} });

export function useToast() { return useContext(ToastContext); }

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, type: Toast["type"] = "info") => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  function dismiss(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  const icons = { success: CheckCircle2, error: AlertCircle, info: Info };
  const colors = { success: "border-green-500/30 bg-green-500/10 text-green-400", error: "border-red-500/30 bg-red-500/10 text-red-400", info: "border-purple-500/30 bg-purple-500/10 text-purple-400" };

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-sm">
        {toasts.map((t) => {
          const Icon = icons[t.type];
          return (
            <div key={t.id} className={`flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm ${colors[t.type]}`}>
              <Icon className="h-4 w-4 shrink-0" />
              <p className="text-sm flex-1">{t.message}</p>
              <button onClick={() => dismiss(t.id)} className="p-0.5 opacity-60 hover:opacity-100"><X className="h-3.5 w-3.5" /></button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
