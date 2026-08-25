// 认证相关路由
import express from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import { getCollection, findById, insert, update, remove } from '../db.js';

const router = express.Router();
const JWT_SECRET = 'yolov8-video-analysis-secret-key-2024';
const JWT_EXPIRES_IN = '24h';

// 生成 token
function generateToken(user) {
  return jwt.sign(
    { id: user.id, username: user.username, role: user.role },
    JWT_SECRET,
    { expiresIn: JWT_EXPIRES_IN }
  );
}

// 认证中间件
export function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: '未提供认证令牌' });
  }

  try {
    const token = authHeader.split(' ')[1];
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: '认证令牌无效或已过期' });
  }
}

// 权限中间件
export function requireRole(...roles) {
  return (req, res, next) => {
    if (!req.user || !roles.includes(req.user.role)) {
      return res.status(403).json({ error: '权限不足' });
    }
    next();
  };
}

// 登录
router.post('/login', async (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: '用户名和密码不能为空' });
  }

  const users = getCollection('users');
  const user = users.find(u => u.username === username);

  if (!user) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  if (user.status !== 'active') {
    return res.status(401).json({ error: '账户已被禁用' });
  }

  const isValid = await bcrypt.compare(password, user.password);
  if (!isValid) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  const token = generateToken(user);
  const { password: _, ...userInfo } = user;

  res.json({
    token,
    user: userInfo
  });
});

// 获取当前用户信息
router.get('/me', authMiddleware, (req, res) => {
  const user = findById('users', req.user.id);
  if (!user) {
    return res.status(404).json({ error: '用户不存在' });
  }
  const { password: _, ...userInfo } = user;
  res.json(userInfo);
});

// 修改密码
router.post('/change-password', authMiddleware, async (req, res) => {
  const { oldPassword, newPassword } = req.body;
  const user = findById('users', req.user.id);

  if (!user) {
    return res.status(404).json({ error: '用户不存在' });
  }

  const isValid = await bcrypt.compare(oldPassword, user.password);
  if (!isValid) {
    return res.status(400).json({ error: '原密码错误' });
  }

  const hashedPassword = await bcrypt.hash(newPassword, 10);
  update('users', req.user.id, { password: hashedPassword });

  res.json({ message: '密码修改成功' });
});

// 登出
router.post('/logout', authMiddleware, (req, res) => {
  // JWT 无状态，客户端删除 token 即可
  res.json({ message: '登出成功' });
});

// 用户列表（管理员）
router.get('/users', authMiddleware, requireRole('admin'), (req, res) => {
  const { page = 1, pageSize = 10, keyword = '', role = '' } = req.query;
  let users = getCollection('users');

  if (keyword) {
    users = users.filter(u =>
      u.username.includes(keyword) || u.name.includes(keyword)
    );
  }
  if (role) {
    users = users.filter(u => u.role === role);
  }

  const total = users.length;
  const start = (page - 1) * pageSize;
  const list = users.slice(start, start + parseInt(pageSize)).map(({ password: _, ...u }) => u);

  res.json({ list, total, page: parseInt(page), pageSize: parseInt(pageSize) });
});

// 新增用户（管理员）
router.post('/users', authMiddleware, requireRole('admin'), async (req, res) => {
  const { username, password, name, role, email, phone } = req.body;
  const users = getCollection('users');

  if (users.find(u => u.username === username)) {
    return res.status(400).json({ error: '用户名已存在' });
  }

  const hashedPassword = await bcrypt.hash(password || '123456', 10);
  const user = insert('users', {
    username,
    password: hashedPassword,
    name,
    role: role || 'viewer',
    email: email || '',
    phone: phone || '',
    status: 'active'
  });

  const { password: _, ...userInfo } = user;
  res.json(userInfo);
});

// 更新用户（管理员）
router.put('/users/:id', authMiddleware, requireRole('admin'), (req, res) => {
  const { name, role, email, phone, status } = req.body;
  const user = update('users', req.params.id, { name, role, email, phone, status });
  if (!user) {
    return res.status(404).json({ error: '用户不存在' });
  }
  const { password: _, ...userInfo } = user;
  res.json(userInfo);
});

// 删除用户（管理员）
router.delete('/users/:id', authMiddleware, requireRole('admin'), (req, res) => {
  if (parseInt(req.params.id) === req.user.id) {
    return res.status(400).json({ error: '不能删除自己' });
  }
  const result = remove('users', req.params.id);
  if (!result) {
    return res.status(404).json({ error: '用户不存在' });
  }
  res.json({ message: '删除成功' });
});

// 重置用户密码（管理员）
router.post('/users/:id/reset-password', authMiddleware, requireRole('admin'), async (req, res) => {
  const { newPassword } = req.body;
  const hashedPassword = await bcrypt.hash(newPassword || '123456', 10);
  const user = update('users', req.params.id, { password: hashedPassword });
  if (!user) {
    return res.status(404).json({ error: '用户不存在' });
  }
  res.json({ message: '密码重置成功' });
});

export default router;
