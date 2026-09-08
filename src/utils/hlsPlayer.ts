import Hls from 'hls.js'
import type { Ref } from 'vue'

export type HlsHandle = {
  destroy: () => void
}

/**
 * Attach HLS (or native HLS) to a video element. Returns a destroy handle.
 */
export function attachHls(video: HTMLVideoElement, url: string): HlsHandle {
  if (!url || !video) {
    return { destroy: () => undefined }
  }

  const absoluteUrl = url.startsWith('http') ? url : url

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        liveDurationInfinity: true,
        maxLiveSyncPlaybackRate: 1.5,
        // Tolerate briefly stale live playlists after segment gaps
        manifestLoadingMaxRetry: 4,
        levelLoadingMaxRetry: 4,
        fragLoadingMaxRetry: 4,
        xhrSetup: (xhr) => {
          xhr.withCredentials = true
        }
      })
      hls.loadSource(absoluteUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => undefined)
      })
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data?.fatal) return
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          try {
            hls.recoverMediaError()
          } catch {
            /* ignore */
          }
          return
        }
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          try {
            hls.startLoad()
          } catch {
            /* ignore */
          }
        }
      })
      return {
        destroy: () => {
          try {
            hls.destroy()
          } catch {
            /* ignore */
          }
        }
      }
    }

  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.crossOrigin = 'use-credentials'
    video.src = absoluteUrl
    video.addEventListener('loadedmetadata', () => {
      video.play().catch(() => undefined)
    })
    return {
      destroy: () => {
        video.removeAttribute('src')
        video.load()
      }
    }
  }

  return { destroy: () => undefined }
}

/** Manage multiple camera video elements by id. */
export function createHlsPool() {
  const handles = new Map<number, HlsHandle>()

  function bind(cameraId: number, video: HTMLVideoElement | null, url: string | null | undefined) {
    const prev = handles.get(cameraId)
    if (prev) {
      prev.destroy()
      handles.delete(cameraId)
    }
    if (!video || !url) return
    handles.set(cameraId, attachHls(video, url))
  }

  function unbind(cameraId: number) {
    const prev = handles.get(cameraId)
    if (prev) {
      prev.destroy()
      handles.delete(cameraId)
    }
  }

  function destroyAll() {
    handles.forEach((h) => h.destroy())
    handles.clear()
  }

  return { bind, unbind, destroyAll }
}

export function setVideoRef(
  map: Ref<Record<number, HTMLVideoElement | null>>,
  id: number,
  el: Element | null
) {
  map.value[id] = (el as HTMLVideoElement) || null
}
