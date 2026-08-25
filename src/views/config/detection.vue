<template>
  <div class="config-page">
    <el-row :gutter="20">
      <el-col :span="4">
        <el-card class="nav-card">
          <el-menu :default-active="activeMenu" router class="config-menu">
            <el-menu-item index="/config"><el-icon><Setting /></el-icon><span>系统设置</span></el-menu-item>
            <el-menu-item index="/config/detection"><el-icon><Aim /></el-icon><span>检测参数</span></el-menu-item>
            <el-menu-item index="/config/strategies"><el-icon><Lock /></el-icon><span>布防策略</span></el-menu-item>
            <el-menu-item index="/config/notification"><el-icon><Message /></el-icon><span>通知配置</span></el-menu-item>
            <el-menu-item v-if="userStore.isAdmin" index="/config/users"><el-icon><User /></el-icon><span>用户管理</span></el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <el-col :span="20">
        <el-card v-loading="loading" class="content-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">检测参数配置</span>
              <el-button type="primary" :loading="saveLoading" @click="handleSave">保存配置</el-button>
            </div>
          </template>

          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 20px"
          >
            <template #title>参数说明</template>
            <p style="margin: 8px 0 0">调整这些参数将影响所有摄像头的检测效果。调高置信度可减少误报，但可能增加漏报；降低 IoU 阈值可减少重叠框。</p>
          </el-alert>

          <el-form :model="form" label-width="140px" style="max-width: 600px">
            <el-form-item label="置信度阈值">
              <div class="slider-item">
                <el-slider
                  v-model="form.confidenceThreshold"
                  :min="0.1"
                  :max="0.95"
                  :step="0.05"
                  :show-tooltip="true"
                  style="width: 300px"
                />
                <span class="slider-value">{{ (form.confidenceThreshold * 100).toFixed(0) }}%</span>
              </div>
              <div class="form-desc">低于此置信度的检测结果将被过滤。建议值：0.4 - 0.6</div>
            </el-form-item>

            <el-form-item label="IoU 阈值">
              <div class="slider-item">
                <el-slider
                  v-model="form.iouThreshold"
                  :min="0.1"
                  :max="0.9"
                  :step="0.05"
                  style="width: 300px"
                />
                <span class="slider-value">{{ (form.iouThreshold * 100).toFixed(0) }}%</span>
              </div>
              <div class="form-desc">非极大值抑制的 IoU 阈值。值越低，合并的检测框越多。建议值：0.4 - 0.5</div>
            </el-form-item>

            <el-form-item label="抽帧率">
              <div class="slider-item">
                <el-slider
                  v-model="form.fps"
                  :min="0.5"
                  :max="10"
                  :step="0.5"
                  style="width: 300px"
                />
                <span class="slider-value">{{ form.fps }} FPS</span>
              </div>
              <div class="form-desc">每秒抽取的视频帧数。帧率越高检测越实时，但 GPU 占用也越高。建议值：1 - 3</div>
            </el-form-item>

            <el-form-item label="最大检测数">
              <el-input-number v-model="form.maxDetections" :min="10" :max="500" :step="10" />
              <span class="form-tip">每帧最多检测的目标数量</span>
            </el-form-item>

            <el-divider />

            <h4 class="section-title">检测类别</h4>
            <el-form-item label="启用的类别">
              <el-checkbox-group v-model="form.categories">
                <el-checkbox value="person">人员</el-checkbox>
                <el-checkbox value="car">轿车</el-checkbox>
                <el-checkbox value="truck">卡车</el-checkbox>
                <el-checkbox value="bus">公交车</el-checkbox>
                <el-checkbox value="bicycle">自行车</el-checkbox>
                <el-checkbox value="motorcycle">摩托车</el-checkbox>
                <el-checkbox value="fire">火焰</el-checkbox>
                <el-checkbox value="smoke">烟雾</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <el-divider />

            <h4 class="section-title">追踪设置</h4>
            <el-form-item label="目标追踪">
              <el-switch v-model="form.trackingEnabled" />
              <span class="form-tip">启用 ByteTrack 多目标追踪算法</span>
            </el-form-item>
            <el-form-item v-if="form.trackingEnabled" label="追踪最大丢失">
              <el-input-number v-model="form.trackLostFrames" :min="1" :max="100" />
              <span class="form-tip">帧，目标丢失多少帧后删除追踪</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { configApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { Setting, Aim, Lock, Message, User } from '@element-plus/icons-vue'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const saveLoading = ref(false)
const activeMenu = ref('/config/detection')

const form = reactive({
  confidenceThreshold: 0.5,
  iouThreshold: 0.45,
  fps: 2,
  maxDetections: 100,
  categories: ['person', 'car', 'truck', 'fire', 'smoke'] as string[],
  trackingEnabled: true,
  trackLostFrames: 30
})

async function loadData() {
  loading.value = true
  try {
    const res: any = await configApi.getDetection()
    if (res) {
      form.confidenceThreshold = res.confidenceThreshold || 0.5
      form.iouThreshold = res.iouThreshold || 0.45
      form.fps = res.fps || 2
      form.maxDetections = res.maxDetections || 100
    }
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saveLoading.value = true
  try {
    await configApi.updateDetection({
      confidenceThreshold: form.confidenceThreshold,
      iouThreshold: form.iouThreshold,
      fps: form.fps,
      maxDetections: form.maxDetections
    })
    ElMessage.success('检测参数已更新')
  } catch (e) {
    // 错误已处理
  } finally {
    saveLoading.value = false
  }
}

onMounted(() => {
  activeMenu.value = route.path
  loadData()
})
</script>

<style scoped>
.config-page {
  padding: 4px;
}

.nav-card {
  padding: 0;
}

.config-menu {
  border-right: none;
}

.config-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 16px;
}

.slider-item {
  display: flex;
  align-items: center;
  gap: 16px;
}

.slider-value {
  min-width: 80px;
  font-size: 14px;
  font-weight: 600;
  color: #1677ff;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.form-desc {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 6px;
}

.form-tip {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
}
</style>
