import { defineConfig, loadEnv, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import http from 'node:http'

function proxyHttp(
  req: http.IncomingMessage,
  res: http.ServerResponse,
  target: URL,
  pathOverride?: string
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
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers)
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

/** Force-proxy /media/* to Django (authenticated HLS / evidence). */
function streamProxies(apiTarget: string): Plugin {
  const api = new URL(apiTarget)
  return {
    name: 'stream-proxies',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || ''
        if (url.startsWith('/media/')) {
          proxyHttp(req, res, api)
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

  return {
    plugins: [vue(), streamProxies(apiTarget)],
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
