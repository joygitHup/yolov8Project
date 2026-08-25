// 系统配置路由
import express from 'express';
import { db, getCollection, findById, insert, update, remove } from '../db.js';
import { authMiddleware, requireRole } from './auth.js';

const router = express.Router();

// 获取系统设置
router.get('/settings', authMiddleware, (req, res) => {
  res.json(db.settings);
});

// 更新系统设置
router.put('/settings', authMiddleware, requireRole('admin'), (req, res) => {
  const { detection, notification, alertDeduplication, system } = req.body;
  
  if (detection) {
    db.settings.detection = { ...db.settings.detection, ...detection };
  }
  if (notification) {
    db.settings.notification = { ...db.settings.notification, ...notification };
  }
  if (alertDeduplication) {
    db.settings.alertDeduplication = { ...db.settings.alertDeduplication, ...alertDeduplication };
  }
  if (system) {
    db.settings.system = { ...db.settings.system, ...system };
  }

  res.json({ message: '设置已更新', settings: db.settings });
});

// 获取检测参数配置
router.get('/detection', authMiddleware, (req, res) => {
  res.json(db.settings.detection);
});

// 更新检测参数
router.put('/detection', authMiddleware, requireRole('admin'), (req, res) => {
  const { confidenceThreshold, iouThreshold, fps, maxDetections } = req.body;
  db.settings.detection = {
    confidenceThreshold: confidenceThreshold ?? db.settings.detection.confidenceThreshold,
    iouThreshold: iouThreshold ?? db.settings.detection.iouThreshold,
    fps: fps ?? db.settings.detection.fps,
    maxDetections: maxDetections ?? db.settings.detection.maxDetections
  };
  res.json({ message: '检测参数已更新', detection: db.settings.detection });
});

// 获取通知配置
router.get('/notification', authMiddleware, requireRole('admin'), (req, res) => {
  res.json(db.settings.notification);
});

// 更新通知配置
router.put('/notification', authMiddleware, requireRole('admin'), (req, res) => {
  db.settings.notification = { ...db.settings.notification, ...req.body };
  res.json({ message: '通知配置已更新', notification: db.settings.notification });
});

// 测试通知通道
router.post('/notification/test', authMiddleware, requireRole('admin'), (req, res) => {
  const { channel } = req.body;
  // 模拟测试
  setTimeout(() => {
    res.json({ success: true, message: `${channel} 测试消息发送成功` });
  }, 1000);
});

// 布防策略列表
router.get('/strategies', authMiddleware, (req, res) => {
  const strategies = getCollection('strategies');
  const cameras = getCollection('cameras');
  
  const list = strategies.map(s => ({
    ...s,
    cameraNames: s.cameraIds
      .map(id => cameras.find(c => c.id === id)?.name)
      .filter(Boolean)
  }));

  res.json({ list, total: list.length });
});

// 获取布防策略详情
router.get('/strategies/:id', authMiddleware, (req, res) => {
  const strategy = findById('strategies', req.params.id);
  if (!strategy) {
    return res.status(404).json({ error: '策略不存在' });
  }
  res.json(strategy);
});

// 新增布防策略
router.post('/strategies', authMiddleware, requireRole('admin'), (req, res) => {
  const { name, cameraIds, detectionTypes, schedule, alertLevel, enabled } = req.body;
  
  if (!name || !cameraIds?.length || !detectionTypes?.length) {
    return res.status(400).json({ error: '请填写完整的策略信息' });
  }

  const strategy = insert('strategies', {
    name,
    cameraIds,
    detectionTypes,
    schedule: schedule || { type: 'always' },
    alertLevel: alertLevel || 'medium',
    enabled: enabled !== undefined ? enabled : true
  });

  res.json(strategy);
});

// 更新布防策略
router.put('/strategies/:id', authMiddleware, requireRole('admin'), (req, res) => {
  const { name, cameraIds, detectionTypes, schedule, alertLevel, enabled } = req.body;
  const strategy = update('strategies', req.params.id, {
    name, cameraIds, detectionTypes, schedule, alertLevel, enabled
  });
  if (!strategy) {
    return res.status(404).json({ error: '策略不存在' });
  }
  res.json(strategy);
});

// 删除布防策略
router.delete('/strategies/:id', authMiddleware, requireRole('admin'), (req, res) => {
  const result = remove('strategies', req.params.id);
  if (!result) {
    return res.status(404).json({ error: '策略不存在' });
  }
  res.json({ message: '删除成功' });
});

// 启用/禁用策略
router.post('/strategies/:id/toggle', authMiddleware, requireRole('admin'), (req, res) => {
  const strategy = findById('strategies', req.params.id);
  if (!strategy) {
    return res.status(404).json({ error: '策略不存在' });
  }
  const updated = update('strategies', req.params.id, { enabled: !strategy.enabled });
  res.json({ enabled: updated.enabled });
});

// 获取系统信息
router.get('/system/info', authMiddleware, (req, res) => {
  const cameras = getCollection('cameras');
  const alerts = getCollection('alerts');
  const users = getCollection('users');

  res.json({
    system: {
      name: db.settings.system.title,
      version: '1.0.0',
      environment: process.env.NODE_ENV || 'development',
      uptime: process.uptime()
    },
    stats: {
      cameras: {
        total: cameras.length,
        online: cameras.filter(c => c.status === 'online').length,
        offline: cameras.filter(c => c.status === 'offline').length,
        enabled: cameras.filter(c => c.enabled).length
      },
      alerts: {
        total: alerts.length,
        today: alerts.filter(a => {
          const today = new Date();
          today.setHours(0, 0, 0, 0);
          return new Date(a.triggeredAt) >= today;
        }).length,
        unhandled: alerts.filter(a => a.status === 'unhandled').length
      },
      users: {
        total: users.length,
        active: users.filter(u => u.status === 'active').length
      }
    },
    detection: db.settings.detection
  });
});

export default router;
