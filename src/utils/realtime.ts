import { useUserStore } from '@/stores/user'

type RealtimeHandler = (payload: any, message?: any) => void

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let intentionalClose = false

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
let reconnectDelay = RECONNECT_BASE_MS

const handlers = new Map<string, Set<RealtimeHandler>>()

export function onRealtime(event: string, handler: RealtimeHandler) {
  if (!handlers.has(event)) handlers.set(event, new Set())
  handlers.get(event)!.add(handler)
  return () => handlers.get(event)?.delete(handler)
}

export function connectRealtime() {
  const userStore = useUserStore()
  if (!userStore.isLoggedIn || (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING))) {
    return
  }
  intentionalClose = false
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  socket = new WebSocket(`${protocol}//${location.host}/ws`)

  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      handlers.get(message.event)?.forEach((fn) => fn(message.payload, message))
    } catch {
      // ignore malformed frames
    }
  }

  socket.onopen = () => {
    // Connection restored — reset backoff so the next drop reconnects fast.
    reconnectDelay = RECONNECT_BASE_MS
  }

  socket.onclose = () => {
    socket = null
    if (!intentionalClose && useUserStore().isLoggedIn) {
      // Exponential backoff with jitter: 1s → 2s → 4s → 8s → 16s → 30s cap.
      const jitter = Math.random() * 500
      reconnectTimer = setTimeout(connectRealtime, reconnectDelay + jitter)
      reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)
    }
  }
}

export function disconnectRealtime() {
  intentionalClose = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = null
  reconnectDelay = RECONNECT_BASE_MS
  socket?.close()
  socket = null
}
