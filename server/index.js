// 后端 Express 服务 - YOLOv8 视频智能分析系统
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { initDB, testDB } from './db.js';
import authRoutes from './routes/auth.js';
import cameraRoutes from './routes/cameras.js';
import alertRoutes from './routes/alerts.js';
import configRoutes from './routes/config.js';
import dashboardRoutes from './routes/dashboard.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = parseInt(process.env.DEPLOY_RUN_PORT || '5000') + 1;
// 生产环境后端与前端同端口，前端静态由 express 提供
const IS_PROD = process.env.COZE_PROJECT_ENV === 'PROD' || process.env.NODE_ENV === 'production';

// 中间件
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// API 路由
app.use('/api/auth', authRoutes);
app.use('/api/cameras', cameraRoutes);
app.use('/api/alerts', alertRoutes);
app.use('/api/config', configRoutes);
app.use('/api/dashboard', dashboardRoutes);

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// 生产环境：提供前端静态文件
if (IS_PROD) {
  const distPath = path.join(__dirname, '..', 'dist');
  app.use(express.static(distPath));
  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api/')) return next();
    res.sendFile(path.join(distPath, 'index.html'));
  });
}

// 错误处理
app.use((err, req, res, next) => {
  console.error('[API Error]', err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal Server Error',
    code: err.code || 'INTERNAL_ERROR'
  });
});

async function start() {
  try {
    await initDB();
    await testDB();
    app.listen(PORT, () => {
      console.log(`🚀 后端服务启动成功，运行在端口 ${PORT}`);
      console.log(`📡 API 地址: http://localhost:${PORT}/api`);
      console.log(`🔧 环境: ${IS_PROD ? '生产' : '开发'}`);
    });
  } catch (error) {
    console.error('启动失败:', error);
    process.exit(1);
  }
}

start();
