/**
 * Toast 通知：像素风右下角提示（成功黄色 / 错误红色）。
 */

import { createContext, useCallback, useContext, useRef, useState } from 'react'

interface ToastState {
  text: string
  kind: 'ok' | 'error'
}

const ToastContext = createContext<{ toast: (text: string, kind?: 'ok' | 'error') => void }>({
  toast: () => {},
})

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ToastState | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const toast = useCallback((text: string, kind: 'ok' | 'error' = 'ok') => {
    clearTimeout(timer.current)
    setState({ text, kind })
    timer.current = setTimeout(() => setState(null), 3200)
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className={`toast ${state ? 'show' : ''} ${state?.kind === 'error' ? 'error' : ''}`} role="status">
        {state?.text}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
