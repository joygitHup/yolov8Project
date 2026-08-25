// 告警管理路由
import express from 'express';
import { getCollection, findById, update, db } from '../db.js';
import { authMiddleware } from './auth.js';

const router = express.Router();

// 获取告警列表
router.get('/', authMiddleware, (req, res) => {
  const {
    page = 1,
    pageSize = 10,
    type = '',
    level = '',
    status = '',
    cameraId = '',
    startDate = '',
    endDate = '',
    keyword = ''
  } = req.query;

  let alerts = [...getCollection('alerts')];

  if (type) {
    alerts = alerts.filter(a => a.type === type);
  }
  if (level) {
    alerts = alerts.filter(a => a.level === level);
  }
  if (status) {
    alerts = alerts.filter(a => a.status === status);
  }
  if (cameraId) {
    alerts = alerts.filter(a => a.cameraId === parseInt(cameraId));
  }
  if (startDate) {
    alerts = alerts.filter(a => new Date(a.triggeredAt) >= new Date(startDate));
  }
  if (endDate) {
    const end = new Date(endDate);
    end.setHours(23, 59, 59, 999);
    alerts = alerts.filter(a => new Date(a.triggeredAt) <= end);
  }
  if (keyword) {
    alerts = alerts.filter(a =>
      a.description.includes(keyword) ||
      a.cameraName.includes(keyword)
    );
  }

  // 按触发时间倒序
  alerts.sort((a, b) => new Date(b.triggeredAt) - new Date(a.triggeredAt));

  const total = alerts.length;
  const start = (page - 1) * pageSize;
  const list = alerts.slice(start, start + parseInt(pageSize));

  res.json({ list, total, page: parseInt(page), pageSize: parseInt(pageSize) });
});

// 获取告警统计
router.get('/stats', authMiddleware, (req, res) => {
  const alerts = getCollection('alerts');
  const now = new Date();

  // 今日告警
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const todayAlerts = alerts.filter(a => new Date(a.triggeredAt) >= today);

  // 本周告警
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - today.getDay());
  const weekAlerts = alerts.filter(a => new Date(a.triggeredAt) >= weekStart);

  // 各状态统计
  const statusCounts = {
    unhandled: alerts.filter(a => a.status === 'unhandled').length,
    processing: alerts.filter(a => a.status === 'processing').length,
    resolved: alerts.filter(a => a.status === 'resolved').length
  };

  // 各类型统计
  const typeCounts = {
    intrusion: alerts.filter(a => a.type === 'intrusion').length,
    parking: alerts.filter(a => a.type === 'parking').length,
    fire: alerts.filter(a => a.type === 'fire').length
  };

  // 各级别统计
  const levelCounts = {
    high: alerts.filter(a => a.level === 'high').length,
    medium: alerts.filter(a => a.level === 'medium').length,
    low: alerts.filter(a => a.level === 'low').length
  };

  // 最近7天趋势
  const dailyStats = [];
  for (let i = 6; i >= 0; i--) {
    const dayStart = new Date(today);
    dayStart.setDate(today.getDate() - i);
    const dayEnd = new Date(dayStart);
    dayEnd.setDate(dayStart.getDate() + 1);

    const dayAlerts = alerts.filter(a => {
      const t = new Date(a.triggeredAt);
      return t >= dayStart && t < dayEnd;
    });

    dailyStats.push({
      date: dayStart.toISOString().split('T')[0],
      total: dayAlerts.length,
      intrusion: dayAlerts.filter(a => a.type === 'intrusion').length,
      parking: dayAlerts.filter(a => a.type === 'parking').length,
      fire: dayAlerts.filter(a => a.type === 'fire').length
    });
  }

  res.json({
    today: todayAlerts.length,
    week: weekAlerts.length,
    total: alerts.length,
    statusCounts,
    typeCounts,
    levelCounts,
    dailyStats
  });
});

// 获取告警详情
router.get('/:id', authMiddleware, (req, res) => {
  const alert = findById('alerts', req.params.id);
  if (!alert) {
    return res.status(404).json({ error: '告警不存在' });
  }
  res.json(alert);
});

// 处理告警
router.post('/:id/handle', authMiddleware, (req, res) => {
  const { status, note } = req.body;
  const validStatuses = ['processing', 'resolved'];
  if (!validStatuses.includes(status)) {
    return res.status(400).json({ error: '无效的状态' });
  }

  const updateData = { status };
  if (status === 'resolved') {
    updateData.resolvedAt = new Date().toISOString();
    updateData.resolvedBy = req.user.username;
    updateData.resolvedNote = note || '';
  }

  const alert = update('alerts', req.params.id, updateData);
  if (!alert) {
    return res.status(404).json({ error: '告警不存在' });
  }
  res.json(alert);
});

// 批量处理告警
router.post('/batch-handle', authMiddleware, (req, res) => {
  const { ids, status, note } = req.body;
  if (!Array.isArray(ids) || ids.length === 0) {
    return res.status(400).json({ error: '请选择告警' });
  }

  let count = 0;
  const updateData = { status };
  if (status === 'resolved') {
    updateData.resolvedAt = new Date().toISOString();
    updateData.resolvedBy = req.user.username;
    updateData.resolvedNote = note || '';
  }

  ids.forEach(id => {
    if (update('alerts', id, updateData)) count++;
  });

  res.json({ message: `成功处理 ${count} 条告警`, count });
});

// 告警热力图数据
router.get('/heatmap/data', authMiddleware, (req, res) => {
  const cameras = getCollection('cameras');
  const alerts = getCollection('alerts');

  const data = cameras.map(cam => {
    const camAlerts = alerts.filter(a => a.cameraId === cam.id);
    return {
      id: cam.id,
      name: cam.name,
      location: cam.location,
      total: camAlerts.length,
      today: camAlerts.filter(a => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return new Date(a.triggeredAt) >= today;
      }).length,
      unhandled: camAlerts.filter(a => a.status === 'unhandled').length,
      high: camAlerts.filter(a => a.level === 'high').length
    };
  });

  data.sort((a, b) => b.total - a.total);
  res.json(data);
});

export default router;
