import { useUserStore } from '@/stores/user'

type RealtimeHandler = (payload: any, message?: any) => void

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let intentionalClose = false

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

  socket.onclose = () => {
    socket = null
    if (!intentionalClose && useUserStore().isLoggedIn) {
      reconnectTimer = setTimeout(connectRealtime, 4000)
    }
  }
}

export function disconnectRealtime() {
  intentionalClose = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  socket?.close()
  socket = null
}
