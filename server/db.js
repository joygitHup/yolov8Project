// 数据库模块 - 内存存储模式（沙箱环境）
// 生产环境可切换为 PostgreSQL
import bcrypt from 'bcryptjs';

// 内存数据存储
let db = {
  users: [],
  cameras: [],
  alerts: [],
  settings: {},
  strategies: []
};

let nextId = {
  users: 1,
  cameras: 1,
  alerts: 1,
  strategies: 1
};

// 初始化默认数据
async function initDB() {
  console.log('📦 初始化数据库（内存模式）...');
  
  // 默认管理员用户 admin / admin123
  const hashedPassword = await bcrypt.hash('admin123', 10);
  db.users.push({
    id: nextId.users++,
    username: 'admin',
    password: hashedPassword,
    name: '系统管理员',
    role: 'admin',
    email: 'admin@example.com',
    phone: '13800138000',
    status: 'active',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  db.users.push({
    id: nextId.users++,
    username: 'operator',
    password: await bcrypt.hash('operator123', 10),
    name: '值班操作员',
    role: 'operator',
    email: 'operator@example.com',
    phone: '13900139000',
    status: 'active',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  db.users.push({
    id: nextId.users++,
    username: 'viewer',
    password: await bcrypt.hash('viewer123', 10),
    name: '查看员',
    role: 'viewer',
    email: 'viewer@example.com',
    phone: '13700137000',
    status: 'active',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });

  // 默认摄像头
  const defaultCameras = [
    { name: '东大门入口', location: '园区东门', ip: '192.168.1.101', rtsp: 'rtsp://192.168.1.101/stream', type: 'hikvision', status: 'online', channels: 1, resolution: '1920x1080' },
    { name: '西大门入口', location: '园区西门', ip: '192.168.1.102', rtsp: 'rtsp://192.168.1.102/stream', type: 'hikvision', status: 'online', channels: 1, resolution: '1920x1080' },
    { name: '地下车库A区', location: '地库A-01', ip: '192.168.1.103', rtsp: 'rtsp://192.168.1.103/stream', type: 'dahua', status: 'online', channels: 1, resolution: '1280x720' },
    { name: '地下车库B区', location: '地库B-01', ip: '192.168.1.104', rtsp: 'rtsp://192.168.1.104/stream', type: 'dahua', status: 'offline', channels: 1, resolution: '1280x720' },
    { name: '消防通道-1号楼', location: '1号楼一层', ip: '192.168.1.105', rtsp: 'rtsp://192.168.1.105/stream', type: 'hikvision', status: 'online', channels: 1, resolution: '1920x1080' },
    { name: '围墙-北侧', location: '北围墙中段', ip: '192.168.1.106', rtsp: 'rtsp://192.168.1.106/stream', type: 'hikvision', status: 'online', channels: 1, resolution: '1920x1080' },
    { name: '围墙-东侧', location: '东围墙北段', ip: '192.168.1.107', rtsp: 'rtsp://192.168.1.107/stream', type: 'dahua', status: 'online', channels: 1, resolution: '1280x720' },
    { name: '中央广场', location: '园区中心', ip: '192.168.1.108', rtsp: 'rtsp://192.168.1.108/stream', type: 'hikvision', status: 'online', channels: 1, resolution: '1920x1080' }
  ];

  defaultCameras.forEach((cam, idx) => {
    db.cameras.push({
      id: nextId.cameras++,
      ...cam,
      enabled: true,
      detectionTypes: ['intrusion', 'parking', 'fire'],
      createdAt: new Date(Date.now() - idx * 86400000).toISOString(),
      updatedAt: new Date().toISOString()
    });
  });

  // 生成模拟告警数据
  const alertTypes = ['intrusion', 'parking', 'fire'];
  const alertLevels = ['high', 'medium', 'low'];
  const statuses = ['unhandled', 'processing', 'resolved'];
  const descriptions = {
    intrusion: ['检测到人员进入警戒区域', '检测到车辆越界', '围墙区域发现可疑人员', '禁区内检测到移动物体'],
    parking: ['消防通道发现违停车辆', '通道处检测到电动车停放', '禁停区域有物品堆放', '应急通道被占用'],
    fire: ['检测到明火', '发现烟雾', '疑似火灾隐患', '烟雾浓度异常']
  };

  for (let i = 0; i < 50; i++) {
    const type = alertTypes[Math.floor(Math.random() * alertTypes.length)];
    const camId = Math.floor(Math.random() * 8) + 1;
    const cam = db.cameras.find(c => c.id === camId);
    const status = i < 15 ? 'unhandled' : (i < 30 ? 'processing' : 'resolved');
    const level = type === 'fire' ? 'high' : (type === 'intrusion' ? 'medium' : 'low');
    
    db.alerts.push({
      id: nextId.alerts++,
      cameraId: camId,
      cameraName: cam?.name || '未知',
      type: type,
      level: level,
      description: descriptions[type][Math.floor(Math.random() * descriptions[type].length)],
      status: status,
      confidence: (0.75 + Math.random() * 0.24).toFixed(2),
      imageUrl: `/mock/alert-${i % 8}.jpg`,
      videoUrl: `/mock/alert-${i % 8}.mp4`,
      detectionBoxes: generateMockBoxes(type),
      triggeredAt: new Date(Date.now() - i * 3600000 * (Math.random() * 2 + 0.5)).toISOString(),
      resolvedAt: status === 'resolved' ? new Date(Date.now() - i * 3600000 + 1800000).toISOString() : null,
      resolvedBy: status === 'resolved' ? 'admin' : null,
      resolvedNote: status === 'resolved' ? '已确认并处置完毕' : null,
      createdAt: new Date(Date.now() - i * 3600000).toISOString()
    });
  }

  // 系统设置
  db.settings = {
    detection: {
      confidenceThreshold: 0.5,
      iouThreshold: 0.45,
      fps: 2,
      maxDetections: 100
    },
    notification: {
      enabled: true,
      dingTalk: { enabled: false, webhook: '' },
      wechat: { enabled: false, webhook: '' },
      email: { enabled: false, smtp: '', port: 465, user: '', pass: '', receivers: '' },
      sms: { enabled: false, apiKey: '', receivers: '' }
    },
    alertDeduplication: {
      enabled: true,
      interval: 30
    },
    system: {
      title: 'YOLOv8 视频智能分析系统',
      logo: ''
    }
  };

  // 布防策略
  db.strategies = [
    {
      id: nextId.strategies++,
      name: '全天入侵检测',
      cameraIds: [1, 2, 6, 7],
      detectionTypes: ['intrusion'],
      schedule: { type: 'always' },
      alertLevel: 'medium',
      enabled: true,
      createdAt: new Date().toISOString()
    },
    {
      id: nextId.strategies++,
      name: '工作时间消防通道检测',
      cameraIds: [5],
      detectionTypes: ['parking', 'fire'],
      schedule: { type: 'worktime', start: '08:00', end: '20:00' },
      alertLevel: 'high',
      enabled: true,
      createdAt: new Date().toISOString()
    },
    {
      id: nextId.strategies++,
      name: '夜间围墙重点布防',
      cameraIds: [6, 7],
      detectionTypes: ['intrusion', 'fire'],
      schedule: { type: 'night', start: '22:00', end: '06:00' },
      alertLevel: 'high',
      enabled: true,
      createdAt: new Date().toISOString()
    }
  ];

  console.log('✅ 数据库初始化完成');
  console.log(`   - 用户: ${db.users.length} 个`);
  console.log(`   - 摄像头: ${db.cameras.length} 个`);
  console.log(`   - 告警: ${db.alerts.length} 条`);
}

function generateMockBoxes(type) {
  const boxes = [];
  const count = Math.floor(Math.random() * 3) + 1;
  for (let i = 0; i < count; i++) {
    const x = Math.random() * 0.6 + 0.1;
    const y = Math.random() * 0.5 + 0.2;
    const w = Math.random() * 0.2 + 0.1;
    const h = Math.random() * 0.3 + 0.15;
    let label = 'person';
    if (type === 'parking') label = Math.random() > 0.5 ? 'car' : 'truck';
    if (type === 'fire') label = Math.random() > 0.5 ? 'fire' : 'smoke';
    boxes.push({
      x: x.toFixed(4),
      y: y.toFixed(4),
      w: w.toFixed(4),
      h: h.toFixed(4),
      label,
      confidence: (0.7 + Math.random() * 0.28).toFixed(2)
    });
  }
  return boxes;
}

async function testDB() {
  console.log('🔍 数据库连接测试: 正常（内存模式）');
  return true;
}

// 工具函数
function getNextId(collection) {
  return nextId[collection]++;
}

function getCollection(name) {
  return db[name];
}

function findById(collection, id) {
  return db[collection].find(item => item.id === parseInt(id));
}

function insert(collection, data) {
  const item = {
    id: getNextId(collection),
    ...data,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
  db[collection].unshift(item);
  return item;
}

function update(collection, id, data) {
  const index = db[collection].findIndex(item => item.id === parseInt(id));
  if (index === -1) return null;
  db[collection][index] = {
    ...db[collection][index],
    ...data,
    updatedAt: new Date().toISOString()
  };
  return db[collection][index];
}

function remove(collection, id) {
  const index = db[collection].findIndex(item => item.id === parseInt(id));
  if (index === -1) return false;
  db[collection].splice(index, 1);
  return true;
}

export {
  initDB,
  testDB,
  getCollection,
  findById,
  insert,
  update,
  remove,
  db
};
