<template>
  <div class="login-container">
    <div class="login-bg">
      <div class="bg-overlay"></div>
      <div class="bg-grid"></div>
    </div>
    
    <div class="login-card">
      <div class="login-header">
        <div class="logo">
          <el-icon class="logo-icon"><VideoCamera /></el-icon>
        </div>
        <h1 class="title">{{ appStore.systemTitle }}</h1>
        <p class="subtitle">AI 驱动的智能安防视频识别平台</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            {{ loading ? '登录中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-tips">
        <p>默认账号：admin / admin123</p>
        <p>操作员账号：operator / operator123</p>
        <p>查看员账号：viewer / viewer123</p>
      </div>

      <div class="login-footer">
        <p>© 2024 YOLOv8 Video Analysis System</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, VideoCamera } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()

const loginFormRef = ref<FormInstance>()
const loading = ref(false)

const loginForm = reactive({
  username: 'admin',
  password: 'admin123'
})

const loginRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不少于6位', trigger: 'blur' }
  ]
}

async function handleLogin() {
  if (!loginFormRef.value) return

  try {
    await loginFormRef.value.validate()
    loading.value = true

    await userStore.login(loginForm.username, loginForm.password)
    ElMessage.success('登录成功')

    const redirect = (route.query.redirect as string) || '/dashboard'
    router.push(redirect)
  } catch (err: any) {
    // 错误已在 request 拦截器中处理
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  appStore.loadPublicSettings()
})
</script>

<style scoped>
.login-container {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0e17;
}

.login-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background:
    radial-gradient(ellipse at top, #0f172a 0%, #0a0e17 50%),
    linear-gradient(135deg, #0a0e17 0%, #111827 100%);
}

.bg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(22, 119, 255, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(82, 196, 26, 0.05) 0%, transparent 50%);
}

.bg-grid {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    linear-gradient(rgba(22, 119, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22, 119, 255, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}

.login-card {
  position: relative;
  z-index: 10;
  width: 420px;
  padding: 40px;
  background: rgba(17, 24, 39, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 12px;
  backdrop-filter: blur(20px);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: linear-gradient(135deg, #1677ff, #0958d9);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(22, 119, 255, 0.3);
}

.logo-icon {
  font-size: 32px;
  color: #fff;
}

.title {
  font-size: 24px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 8px;
}

.subtitle {
  font-size: 14px;
  color: #9ca3af;
  margin: 0;
}

.login-form {
  margin-bottom: 24px;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  background: linear-gradient(135deg, #1677ff, #0958d9);
  border: none;
}

.login-btn:hover {
  opacity: 0.9;
}

.login-tips {
  padding: 12px 16px;
  background: rgba(22, 119, 255, 0.1);
  border: 1px solid rgba(22, 119, 255, 0.2);
  border-radius: 8px;
  font-size: 12px;
  color: #60a5fa;
  line-height: 1.8;
}

.login-tips p {
  margin: 0;
}

.login-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 12px;
  color: #6b7280;
}

.login-footer p {
  margin: 0;
}

:deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: none;
}

:deep(.el-input__wrapper:hover) {
  border-color: rgba(22, 119, 255, 0.5);
}

:deep(.el-input__wrapper.is-focus) {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.2);
}

:deep(.el-input__inner) {
  color: #e5e7eb;
}

:deep(.el-input__inner::placeholder) {
  color: #6b7280;
}

:deep(.el-input__prefix-inner) {
  color: #6b7280;
}
</style>
