<template>
  <el-menu :default-active="route.path" router class="config-menu">
    <el-menu-item index="/config"><el-icon><Tools /></el-icon><span>系统设置</span></el-menu-item>
    <el-menu-item index="/config/detection"><el-icon><Aim /></el-icon><span>检测参数</span></el-menu-item>
    <el-menu-item index="/config/strategies"><el-icon><Lock /></el-icon><span>布防策略</span></el-menu-item>
    <el-menu-item index="/config/whitelist"><el-icon><UserFilled /></el-icon><span>白名单</span></el-menu-item>
    <el-menu-item index="/config/notification"><el-icon><Message /></el-icon><span>通知配置</span></el-menu-item>
    <el-menu-item index="/flywheel"><el-icon><EditPen /></el-icon><span>标注台</span></el-menu-item>
    <el-menu-item v-if="userStore.isAdmin" index="/config/users"><el-icon><User /></el-icon><span>用户管理</span></el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Tools, Aim, Lock, Message, User, EditPen, UserFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()
</script>

<style scoped>
.config-menu { border-right: none; }
.config-menu :deep(.el-menu-item) { height: 48px; line-height: 48px; }
</style>
