# AGENTS.md - YOLOv8 视频智能分析系统

## 项目概览

基于 YOLOv8 的通用型 AI 视频智能分析系统，采用前后端分离架构。前端使用 Vue3 + Element Plus + Vite，后端使用 Node.js + Express + PostgreSQL。系统支持摄像头管理、视频智能分析（入侵检测/违停检测/火灾检测）、告警管理、数据大屏等功能。

## 技术栈

### 前端
- **框架**: Vue 3 (Composition API) + TypeScript
- **构建**: Vite 5
- **UI 组件**: Element Plus
- **路由**: Vue Router 4
- **状态管理**: Pinia
- **HTTP 请求**: Axios
- **时间处理**: Day.js
- **样式**: Tailwind CSS

### 后端
- **框架**: Express.js
- **数据库**: PostgreSQL
- **认证**: JWT + bcryptjs
- **开发模式**: Vite 开发服务器代理 API 请求到 Express

## 目录结构

```
.
├── server/                    # 后端 Express 服务
│   ├── index.js              # 入口文件
│   ├── db.js                 # 数据库连接与初始化
│   └── routes/
│       ├── auth.js           # 认证接口
│       ├── cameras.js        # 摄像头管理接口
│       ├── alerts.js         # 告警管理接口
│       ├── config.js         # 系统配置接口
│       └── dashboard.js      # 仪表盘数据接口
├── src/                       # 前端源码
│   ├── api/                   # API 请求封装
│   │   └── index.ts
│   ├── assets/                # 静态资源
│   ├── components/            # 通用组件
│   ├── layout/                # 布局组件
│   │   └── index.vue
│   ├── router/                # 路由配置
│   │   └── index.ts
│   ├── stores/                # Pinia 状态管理
│   │   ├── user.ts
│   │   └── app.ts
│   ├── styles/                # 全局样式
│   ├── utils/                 # 工具函数
│   │   └── request.ts
│   ├── views/                 # 页面视图
│   │   ├── login/             # 登录页
│   │   ├── error/             # 错误页
│   │   ├── dashboard/         # 数据大屏
│   │   ├── overview/          # 概览仪表盘
│   │   ├── cameras/           # 摄像头管理
│   │   ├── monitor/           # 实时监控
│   │   ├── alerts/            # 报警中心
│   │   │   ├── index.vue      # 告警列表
│   │   │   └── detail.vue     # 告警详情
│   │   ├── config/            # 系统配置
│   │   │   ├── index.vue      # 系统设置
│   │   │   ├── detection.vue  # 检测参数
│   │   │   ├── strategies.vue # 布防策略
│   │   │   ├── notification.vue # 通知配置
│   │   │   └── users.vue      # 用户管理
│   │   └── profile/           # 个人中心
│   ├── App.vue
│   └── main.ts
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── .coze                      # 项目配置
├── DESIGN.md                  # 设计规范
└── AGENTS.md                  # 本文件
```

## 构建和运行命令

```bash
# 安装依赖
pnpm install

# 开发模式（Vite 前端 + Express 后端）
pnpm run dev

# 构建生产版本
pnpm run build

# 生产模式启动
pnpm run start
```

## API 接口清单

### 认证 (auth)
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/logout` - 用户登出
- `GET /api/auth/profile` - 获取当前用户信息
- `PUT /api/auth/profile` - 更新个人信息
- `PUT /api/auth/password` - 修改密码

### 摄像头 (cameras)
- `GET /api/cameras` - 获取摄像头列表（分页）
- `GET /api/cameras/all` - 获取全部摄像头
- `GET /api/cameras/:id` - 获取摄像头详情
- `POST /api/cameras` - 新增摄像头
- `PUT /api/cameras/:id` - 更新摄像头
- `DELETE /api/cameras/:id` - 删除摄像头
- `POST /api/cameras/batch-delete` - 批量删除
- `POST /api/cameras/:id/toggle` - 切换启用状态

### 告警 (alerts)
- `GET /api/alerts` - 获取告警列表（分页）
- `GET /api/alerts/stats` - 告警统计
- `GET /api/alerts/:id` - 告警详情
- `PUT /api/alerts/:id/handle` - 处理告警
- `POST /api/alerts/batch-handle` - 批量处理

### 系统配置 (config)
- `GET /api/config/settings` - 获取系统设置
- `PUT /api/config/settings` - 更新系统设置
- `GET /api/config/detection` - 获取检测参数
- `PUT /api/config/detection` - 更新检测参数
- `GET /api/config/system-info` - 系统信息
- `GET /api/config/strategies` - 布防策略列表
- `POST /api/config/strategies` - 新增策略
- `PUT /api/config/strategies/:id` - 更新策略
- `DELETE /api/config/strategies/:id` - 删除策略
- `GET /api/config/notification` - 通知配置
- `PUT /api/config/notification` - 更新通知配置

### 仪表盘 (dashboard)
- `GET /api/dashboard/stats` - 概览统计
- `GET /api/dashboard/alert-trend` - 告警趋势
- `GET /api/dashboard/alert-types` - 告警类型分布
- `GET /api/dashboard/recent-alerts` - 最近告警
- `GET /api/dashboard/camera-status` - 摄像头状态

### 用户管理 (users) - admin 权限
- `GET /api/users` - 用户列表
- `POST /api/users` - 新增用户
- `PUT /api/users/:id` - 更新用户
- `DELETE /api/users/:id` - 删除用户
- `POST /api/users/:id/toggle-status` - 切换用户状态
- `PUT /api/users/:id/reset-password` - 重置密码

## 数据库表结构

### users 用户表
- id, username, password, real_name, role, email, phone, avatar, enabled, last_login_at, created_at

### cameras 摄像头表
- id, name, location, ip, type, rtsp, username, password, resolution, channels, status, enabled, detection_types, created_at

### alerts 告警表
- id, camera_id, camera_name, type, level, description, confidence, status, snapshot_url, video_url, triggered_at, resolved_by, resolved_at, resolved_note, detection_boxes(json)

### strategies 布防策略表
- id, name, camera_ids(json), detection_types(json), schedule(json), alert_level, enabled, created_at

### config 配置表
- key, value(json), updated_at

## 设计规范

详见 `DESIGN.md`，核心：
- 主色 #1677ff（科技蓝）
- 深色模式用于数据大屏，浅色模式用于管理后台
- 组件圆角 4-8px，阴影统一

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
| operator | operator123 | 操作员 |
| viewer | viewer123 | 查看者 |

## 常见问题

### 开发模式下后端如何启动？
执行 `node server/index.js`，后端运行在 3001 端口，Vite 代理 `/api` 到后端。

### 数据是真实的吗？
当前版本为 Demo 模式，使用模拟数据和 PostgreSQL 数据库。AI 检测结果为模拟生成，展示系统界面和交互流程。

### 如何切换深色/浅色模式？
点击右上角主题切换按钮，数据大屏默认深色模式。

## 开发注意事项

1. API 请求统一使用 `src/utils/request.ts` 中的 axios 实例
2. 状态管理使用 Pinia，用户状态在 `stores/user.ts`
3. 路由守卫在 `router/index.ts`，未登录自动跳转登录页
4. 后端 Express 路由统一挂载 `/api` 前缀
5. 数据库操作在 `server/db.js` 中封装
