// 数据大屏路由
import express from 'express';
import { db, getCollection } from '../db.js';
import { authMiddleware } from './auth.js';

const router = express.Router();

// 大屏概览数据
router.get('/overview', authMiddleware, (req, res) => {
  const cameras = getCollection('cameras');
  const alerts = getCollection('alerts');
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  const todayAlerts = alerts.filter(a => new Date(a.triggeredAt) >= today);
  const unhandledAlerts = alerts.filter(a => a.status === 'unhandled');

  res.json({
    cameras: {
      total: cameras.length,
      online: cameras.filter(c => c.status === 'online').length,
      offline: cameras.filter(c => c.status === 'offline').length,
      rate: cameras.length > 0 ? (cameras.filter(c => c.status === 'online').length / cameras.length * 100).toFixed(1) : 0
    },
    alerts: {
      today: todayAlerts.length,
      total: alerts.length,
      unhandled: unhandledAlerts.length,
      resolved: alerts.filter(a => a.status === 'resolved').length
    },
    detection: {
      totalToday: todayAlerts.length * 15, // 模拟检测总次数
      fps: 2,
      avgConfidence: '0.86'
    },
    system: {
      cpu: (40 + Math.random() * 20).toFixed(1),
      memory: (50 + Math.random() * 15).toFixed(1),
      gpu: (30 + Math.random() * 25).toFixed(1),
      uptime: '7天 12小时 36分'
    }
  });
});

// 告警趋势数据（24小时）
router.get('/alert-trend', authMiddleware, (req, res) => {
  const alerts = getCollection('alerts');
  const now = new Date();
  const hours = [];

  for (let i = 23; i >= 0; i--) {
    const hourStart = new Date(now);
    hourStart.setHours(now.getHours() - i, 0, 0, 0);
    const hourEnd = new Date(hourStart);
    hourEnd.setHours(hourStart.getHours() + 1);

    const hourAlerts = alerts.filter(a => {
      const t = new Date(a.triggeredAt);
      return t >= hourStart && t < hourEnd;
    });

    hours.push({
      hour: `${hourStart.getHours().toString().padStart(2, '0')}:00`,
      total: hourAlerts.length + Math.floor(Math.random() * 3),
      intrusion: hourAlerts.filter(a => a.type === 'intrusion').length + Math.floor(Math.random() * 2),
      parking: hourAlerts.filter(a => a.type === 'parking').length + Math.floor(Math.random() * 2),
      fire: hourAlerts.filter(a => a.type === 'fire').length + Math.floor(Math.random() * 1)
    });
  }

  res.json(hours);
});

// 告警类型分布
router.get('/alert-types', authMiddleware, (req, res) => {
  const alerts = getCollection('alerts');
  
  const types = [
    { name: '区域入侵', value: alerts.filter(a => a.type === 'intrusion').length, color: '#e74c3c' },
    { name: '违停占道', value: alerts.filter(a => a.type === 'parking').length, color: '#f39c12' },
    { name: '火灾隐患', value: alerts.filter(a => a.type === 'fire').length, color: '#e67e22' }
  ];

  res.json(types);
});

// 告警级别分布
router.get('/alert-levels', authMiddleware, (req, res) => {
  const alerts = getCollection('alerts');
  
  const levels = [
    { name: '高危', value: alerts.filter(a => a.level === 'high').length, color: '#f5222d' },
    { name: '中危', value: alerts.filter(a => a.level === 'medium').length, color: '#faad14' },
    { name: '低危', value: alerts.filter(a => a.level === 'low').length, color: '#52c41a' }
  ];

  res.json(levels);
});

// 摄像头告警排行
router.get('/camera-rank', authMiddleware, (req, res) => {
  const cameras = getCollection('cameras');
  const alerts = getCollection('alerts');

  const rank = cameras.map(cam => {
    const camAlerts = alerts.filter(a => a.cameraId === cam.id);
    return {
      id: cam.id,
      name: cam.name,
      location: cam.location,
      total: camAlerts.length,
      high: camAlerts.filter(a => a.level === 'high').length,
      status: cam.status
    };
  }).sort((a, b) => b.total - a.total).slice(0, 10);

  res.json(rank);
});

// 实时告警流（最近10条）
router.get('/recent-alerts', authMiddleware, (req, res) => {
  const alerts = getCollection('alerts');
  const recent = [...alerts]
    .sort((a, b) => new Date(b.triggeredAt) - new Date(a.triggeredAt))
    .slice(0, 10);

  res.json(recent);
});

// 区域告警分布
router.get('/area-distribution', authMiddleware, (req, res) => {
  const areas = [
    { name: '大门区域', value: 12, color: '#f5222d' },
    { name: '围墙周边', value: 18, color: '#faad14' },
    { name: '地下车库', value: 8, color: '#1890ff' },
    { name: '楼宇通道', value: 6, color: '#52c41a' },
    { name: '中央广场', value: 4, color: '#722ed1' },
    { name: '其他区域', value: 2, color: '#8c8c8c' }
  ];

  res.json(areas);
});

// 实时检测数据（模拟流式数据）
router.get('/realtime-detections', authMiddleware, (req, res) => {
  const cameras = getCollection('cameras');
  const types = ['person', 'car', 'truck', 'fire', 'smoke'];
  
  const data = cameras.filter(c => c.status === 'online').map(cam => {
    const count = Math.floor(Math.random() * 6);
    const detections = [];
    for (let i = 0; i < count; i++) {
      detections.push({
        label: types[Math.floor(Math.random() * types.length)],
        confidence: (0.65 + Math.random() * 0.32).toFixed(2)
      });
    }
    return {
      cameraId: cam.id,
      cameraName: cam.name,
      detectionCount: count,
      detections,
      timestamp: new Date().toISOString()
    };
  });

  res.json(data);
});

export default router;
