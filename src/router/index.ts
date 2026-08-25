// 路由配置
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '数据大屏', icon: 'DataBoard', requiresAuth: true }
      },
      {
        path: 'overview',
        name: 'Overview',
        component: () => import('@/views/overview/index.vue'),
        meta: { title: '总览分析', icon: 'DataAnalysis', requiresAuth: true }
      },
      {
        path: 'monitor',
        name: 'Monitor',
        component: () => import('@/views/monitor/index.vue'),
        meta: { title: '实时监控', icon: 'VideoCamera', requiresAuth: true }
      },
      {
        path: 'cameras',
        name: 'Cameras',
        component: () => import('@/views/cameras/index.vue'),
        meta: { title: '摄像头管理', icon: 'Camera', requiresAuth: true }
      },
      {
        path: 'alerts',
        name: 'Alerts',
        component: () => import('@/views/alerts/index.vue'),
        meta: { title: '报警中心', icon: 'Bell', requiresAuth: true, badge: true }
      },
      {
        path: 'alerts/:id',
        name: 'AlertDetail',
        component: () => import('@/views/alerts/detail.vue'),
        meta: { title: '告警详情', icon: 'Bell', requiresAuth: true, hidden: true }
      },
      {
        path: 'config',
        name: 'Config',
        component: () => import('@/views/config/index.vue'),
        meta: { title: '系统配置', icon: 'Setting', requiresAuth: true, roles: ['admin', 'operator'] }
      },
      {
        path: 'config/users',
        name: 'UserManagement',
        component: () => import('@/views/config/users.vue'),
        meta: { title: '用户管理', icon: 'User', requiresAuth: true, roles: ['admin'], hidden: true }
      },
      {
        path: 'config/detection',
        name: 'DetectionConfig',
        component: () => import('@/views/config/detection.vue'),
        meta: { title: '检测参数', icon: 'Aim', requiresAuth: true, roles: ['admin', 'operator'], hidden: true }
      },
      {
        path: 'config/strategies',
        name: 'StrategyConfig',
        component: () => import('@/views/config/strategies.vue'),
        meta: { title: '布防策略', icon: 'Shield', requiresAuth: true, roles: ['admin', 'operator'], hidden: true }
      },
      {
        path: 'config/notification',
        name: 'NotificationConfig',
        component: () => import('@/views/config/notification.vue'),
        meta: { title: '通知配置', icon: 'Message', requiresAuth: true, roles: ['admin'], hidden: true }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/index.vue'),
        meta: { title: '个人中心', icon: 'UserFilled', requiresAuth: true, hidden: true }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()
  const title = to.meta.title as string
  if (title) {
    document.title = `${title} - YOLOv8 视频智能分析系统`
  }

  // 不需要登录的页面
  if (to.meta.requiresAuth === false) {
    if (to.path === '/login' && userStore.isLoggedIn) {
      next('/')
    } else {
      next()
    }
    return
  }

  // 需要登录
  if (!userStore.token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 已登录，获取用户信息
  if (!userStore.userInfo) {
    try {
      await userStore.fetchUserInfo()
    } catch {
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
  }

  // 权限校验
  const roles = to.meta.roles as string[] | undefined
  if (roles && userStore.userInfo && !roles.includes(userStore.userInfo.role)) {
    next('/403')
    return
  }

  next()
})

export default router
