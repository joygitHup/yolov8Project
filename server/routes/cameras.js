// 摄像头管理路由
import express from 'express';
import { getCollection, findById, insert, update, remove } from '../db.js';
import { authMiddleware } from './auth.js';

const router = express.Router();

// 获取摄像头列表
router.get('/', authMiddleware, (req, res) => {
  const { page = 1, pageSize = 10, keyword = '', status = '', type = '' } = req.query;
  let cameras = getCollection('cameras');

  if (keyword) {
    cameras = cameras.filter(c =>
      c.name.includes(keyword) ||
      c.location.includes(keyword) ||
      c.ip.includes(keyword)
    );
  }
  if (status) {
    cameras = cameras.filter(c => c.status === status);
  }
  if (type) {
    cameras = cameras.filter(c => c.type === type);
  }

  const total = cameras.length;
  const start = (page - 1) * pageSize;
  const list = cameras.slice(start, start + parseInt(pageSize));

  res.json({ list, total, page: parseInt(page), pageSize: parseInt(pageSize) });
});

// 获取所有摄像头（下拉选择用）
router.get('/all', authMiddleware, (req, res) => {
  const cameras = getCollection('cameras');
  const list = cameras.map(c => ({ id: c.id, name: c.name, status: c.status, location: c.location }));
  res.json(list);
});

// 获取摄像头详情
router.get('/:id', authMiddleware, (req, res) => {
  const camera = findById('cameras', req.params.id);
  if (!camera) {
    return res.status(404).json({ error: '摄像头不存在' });
  }
  res.json(camera);
});

// 新增摄像头
router.post('/', authMiddleware, (req, res) => {
  const { name, location, ip, rtsp, type, username, password, channels, resolution, enabled, detectionTypes } = req.body;
  
  if (!name || !rtsp) {
    return res.status(400).json({ error: '名称和RTSP地址不能为空' });
  }

  const camera = insert('cameras', {
    name,
    location: location || '',
    ip: ip || '',
    rtsp,
    type: type || 'hikvision',
    username: username || 'admin',
    password: password || '',
    channels: channels || 1,
    resolution: resolution || '1920x1080',
    enabled: enabled !== undefined ? enabled : true,
    status: 'online',
    detectionTypes: detectionTypes || ['intrusion', 'parking', 'fire']
  });

  res.json(camera);
});

// 更新摄像头
router.put('/:id', authMiddleware, (req, res) => {
  const { name, location, ip, rtsp, type, username, password, channels, resolution, enabled, detectionTypes } = req.body;
  const camera = update('cameras', req.params.id, {
    name, location, ip, rtsp, type, username, password, channels, resolution, enabled, detectionTypes
  });
  if (!camera) {
    return res.status(404).json({ error: '摄像头不存在' });
  }
  res.json(camera);
});

// 删除摄像头
router.delete('/:id', authMiddleware, (req, res) => {
  const result = remove('cameras', req.params.id);
  if (!result) {
    return res.status(404).json({ error: '摄像头不存在' });
  }
  res.json({ message: '删除成功' });
});

// 批量删除
router.post('/batch-delete', authMiddleware, (req, res) => {
  const { ids } = req.body;
  if (!Array.isArray(ids)) {
    return res.status(400).json({ error: '参数错误' });
  }
  let count = 0;
  ids.forEach(id => {
    if (remove('cameras', id)) count++;
  });
  res.json({ message: `成功删除 ${count} 个摄像头`, count });
});

// 启用/禁用摄像头
router.post('/:id/toggle', authMiddleware, (req, res) => {
  const camera = findById('cameras', req.params.id);
  if (!camera) {
    return res.status(404).json({ error: '摄像头不存在' });
  }
  const updated = update('cameras', req.params.id, { enabled: !camera.enabled });
  res.json({ enabled: updated.enabled });
});

// 云台控制
router.post('/:id/ptz', authMiddleware, (req, res) => {
  const { direction, speed } = req.body;
  // 模拟 PTZ 控制
  res.json({
    success: true,
    message: `云台${direction}控制指令已发送`,
    direction,
    speed: speed || 1
  });
});

// 获取实时检测数据（模拟）
router.get('/:id/detection', authMiddleware, (req, res) => {
  // 生成模拟检测结果
  const types = ['person', 'car', 'truck', 'fire', 'smoke'];
  const count = Math.floor(Math.random() * 5);
  const detections = [];

  for (let i = 0; i < count; i++) {
    const label = types[Math.floor(Math.random() * types.length)];
    detections.push({
      id: i,
      label,
      confidence: (0.6 + Math.random() * 0.38).toFixed(2),
      bbox: {
        x: (Math.random() * 0.8).toFixed(4),
        y: (Math.random() * 0.7).toFixed(4),
        w: (0.1 + Math.random() * 0.2).toFixed(4),
        h: (0.15 + Math.random() * 0.25).toFixed(4)
      }
    });
  }

  res.json({
    cameraId: parseInt(req.params.id),
    timestamp: new Date().toISOString(),
    fps: 2,
    detections
  });
});

export default router;
