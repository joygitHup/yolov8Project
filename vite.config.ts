import { defineConfig, loadEnv, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import http from 'node:http'

function rewriteMtxHeaders(headers: http.IncomingHttpHeaders): http.OutgoingHttpHeaders {
  const out: http.OutgoingHttpHeaders = { ...headers }
  const loc = headers.location
  if (typeof loc === 'string' && loc.startsWith('/') && !loc.startsWith('/mtx-hls/')) {
    out.location = `/mtx-hls${loc}`
  }
  const rawCookie = headers['set-cookie']
  if (rawCookie) {
    const list = Array.isArray(rawCookie) ? rawCookie : [rawCookie]
    // Dev is http://localhost — drop Secure so browser stores cookies for proxy path
    out['set-cookie'] = list.map((c) =>
      c.replace(/;\s*Secure/gi, '').replace(/;\s*Partitioned/gi, '')
    )
  }
  return out
}

function proxyHttp(
  req: http.IncomingMessage,
  res: http.ServerResponse,
  target: URL,
  pathOverride?: string,
  rewriteHeaders?: (h: http.IncomingHttpHeaders) => http.OutgoingHttpHeaders
) {
  const url = pathOverride ?? req.url ?? '/'
  const opts: http.RequestOptions = {
    hostname: target.hostname,
    port: target.port,
    path: url,
    method: req.method,
    headers: { ...req.headers, host: `${target.hostname}:${target.port}` },
  }
  const proxyReq = http.request(opts, (proxyRes) => {
    const headers = rewriteHeaders ? rewriteHeaders(proxyRes.headers) : proxyRes.headers
    res.writeHead(proxyRes.statusCode || 502, headers)
    proxyRes.pipe(res)
  })
  proxyReq.on('error', (err) => {
    console.error('[dev-proxy]', target.host, err.message)
    if (!res.headersSent) {
      res.statusCode = 502
      res.end('Bad Gateway')
    }
  })
  req.pipe(proxyReq)
}

/** Force-proxy /media/* to Django and /mtx-hls/* to MediaMTX. */
function streamProxies(apiTarget: string, mtxHlsTarget: string): Plugin {
  const api = new URL(apiTarget)
  const mtx = new URL(mtxHlsTarget)
  return {
    name: 'stream-proxies',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || ''
        if (url.startsWith('/media/')) {
          proxyHttp(req, res, api)
          return
        }
        if (url.startsWith('/mtx-hls/') || url.startsWith('/mtx-hls?')) {
          const rewritten = url.replace(/^\/mtx-hls/, '') || '/'
          proxyHttp(req, res, mtx, rewritten, rewriteMtxHeaders)
          return
        }
        next()
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const port = parseInt(process.env.DEPLOY_RUN_PORT || env.DEPLOY_RUN_PORT || '5000', 10)
  const apiTarget = `http://127.0.0.1:${port + 1}`
  const mtxHlsTarget = process.env.MEDIAMTX_HLS_BASE || env.MEDIAMTX_HLS_BASE || 'http://127.0.0.1:8888'

  return {
    plugins: [vue(), streamProxies(apiTarget, mtxHlsTarget)],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      port: port,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true
        },
        '/media': {
          target: apiTarget,
          changeOrigin: true
        },
        '/mtx-hls': {
          target: mtxHlsTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/mtx-hls/, '') || '/',
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              const loc = proxyRes.headers.location
              if (typeof loc === 'string' && loc.startsWith('/') && !loc.startsWith('/mtx-hls/')) {
                proxyRes.headers.location = `/mtx-hls${loc}`
              }
              const cookies = proxyRes.headers['set-cookie']
              if (cookies) {
                const list = Array.isArray(cookies) ? cookies : [cookies]
                proxyRes.headers['set-cookie'] = list.map((c) =>
                  c.replace(/;\s*Secure/gi, '').replace(/;\s*Partitioned/gi, '')
                )
              }
            })
          }
        },
        '/ws': {
          target: `ws://127.0.0.1:${port + 1}`,
          ws: true
        }
      }
    },
    build: {
      outDir: 'dist',
      sourcemap: false
    }
  }
})
