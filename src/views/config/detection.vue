<template>
  <div class="config-page">
    <el-row :gutter="20">
      <el-col :span="4">
        <el-card class="nav-card">
          <el-menu :default-active="activeMenu" router class="config-menu">
            <el-menu-item index="/config"><el-icon><Tools /></el-icon><span>系统设置</span></el-menu-item>
            <el-menu-item index="/config/detection"><el-icon><Aim /></el-icon><span>检测参数</span></el-menu-item>
            <el-menu-item index="/config/strategies"><el-icon><Lock /></el-icon><span>布防策略</span></el-menu-item>
            <el-menu-item index="/config/notification"><el-icon><Message /></el-icon><span>通知配置</span></el-menu-item>
            <el-menu-item index="/flywheel"><el-icon><EditPen /></el-icon><span>标注台</span></el-menu-item>
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

          <el-form :model="form" label-width="140px" style="max-width: 640px">
            <el-form-item label="模型权重">
              <el-input v-model="form.modelPath" placeholder="本地 .pt 权重绝对路径" clearable />
              <div class="form-desc">YOLOv8 权重路径；保存后 remote 模式会热加载。也可用环境变量 YOLO_WEIGHTS 作默认值</div>
            </el-form-item>

            <el-form-item label="启用推理">
              <el-switch v-model="form.inferEnabled" />
              <span class="form-tip">关闭后停止 YOLO 调度（便于排查）</span>
            </el-form-item>

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
              <div class="form-desc">每秒抽取的视频帧数。帧率越高检测越实时，但占用也越高。建议值：1 - 3</div>
            </el-form-item>

            <el-form-item label="最大检测数">
              <el-input-number v-model="form.maxDetections" :min="10" :max="500" :step="10" />
              <span class="form-tip">每帧最多检测的目标数量</span>
            </el-form-item>

            <el-divider />

            <h4 class="section-title">检测类别（当前权重）</h4>
            <el-form-item label="启用的类别">
              <el-checkbox-group v-model="form.categories" class="category-group">
                <el-checkbox v-for="name in categoryOptions" :key="name" :value="name">{{ name }}</el-checkbox>
              </el-checkbox-group>
              <div class="form-desc">勾选列表来自当前模型权重的类别名。取消勾选只过滤告警，不会改模型输出的 class id。布防映射：火焰/烟雾→火灾，乱停/网格区违停/轿车/卡车→违停，人员/乱扔垃圾→入侵</div>
            </el-form-item>

            <el-divider />

            <h4 class="section-title">追踪设置</h4>
            <el-form-item label="目标追踪">
              <el-switch v-model="form.trackingEnabled" />
              <span class="form-tip">启用简易 IoU 多目标追踪</span>
            </el-form-item>
            <el-form-item v-if="form.trackingEnabled" label="追踪最大丢失">
              <el-input-number v-model="form.trackLostFrames" :min="1" :max="100" />
              <span class="form-tip">帧，目标丢失多少帧后删除追踪</span>
            </el-form-item>

            <el-divider />
            <h4 class="section-title">现场数据采集（飞轮）</h4>
            <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
              <template #title>采集后需审核，通过才进训练集</template>
              <p style="margin: 8px 0 0">
                原始样本写入 MinIO
                <code>{{ stats.bucket }}/{{ stats.prefix }}/auto</code>
                ；标注台通过后复制到
                <code>reviewed/images</code>。
              </p>
            </el-alert>
            <el-row :gutter="12" class="flywheel-stats">
              <el-col :span="6">
                <div class="fw-stat">
                  <div class="fw-num">{{ stats.today }}</div>
                  <div class="fw-label">今日采集</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="fw-stat">
                  <div class="fw-num">{{ stats.total }}</div>
                  <div class="fw-label">累计样本</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="fw-stat">
                  <div class="fw-num">{{ stats.bySource?.alert || 0 }}</div>
                  <div class="fw-label">告警帧</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="fw-stat">
                  <div class="fw-num">{{ stats.bySource?.uncertain || 0 }}</div>
                  <div class="fw-label">不确定帧</div>
                </div>
              </el-col>
            </el-row>
            <el-form-item label="启用采集">
              <el-switch v-model="flywheel.enabled" />
              <span class="form-tip">关闭后不再向数据集写入新图</span>
            </el-form-item>
            <el-form-item label="采集告警帧">
              <el-switch v-model="flywheel.alertFrames" />
            </el-form-item>
            <el-form-item label="采集不确定帧">
              <el-switch v-model="flywheel.uncertainFrames" />
              <span class="form-tip">最高置信度落在下方区间时采样</span>
            </el-form-item>
            <el-form-item label="不确定下限">
              <div class="slider-item">
                <el-slider v-model="flywheel.uncertainLow" :min="0.05" :max="0.8" :step="0.05" style="width: 300px" />
                <span class="slider-value">{{ (flywheel.uncertainLow * 100).toFixed(0) }}%</span>
              </div>
            </el-form-item>
            <el-form-item label="不确定上限">
              <div class="slider-item">
                <el-slider v-model="flywheel.uncertainHigh" :min="0.1" :max="0.95" :step="0.05" style="width: 300px" />
                <span class="slider-value">{{ (flywheel.uncertainHigh * 100).toFixed(0) }}%</span>
              </div>
              <div class="form-desc">建议低于检测置信度阈值，专门收集难例</div>
            </el-form-item>
            <el-form-item label="每路每小时配额">
              <el-input-number v-model="flywheel.quotaPerCameraHour" :min="1" :max="500" :step="5" />
              <span class="form-tip">不确定帧受配额限制；告警帧优先写入</span>
            </el-form-item>
            <el-form-item label="最小采样间隔">
              <el-input-number v-model="flywheel.sampleIntervalSec" :min="3" :max="300" :step="1" />
              <span class="form-tip">秒，同一摄像头不确定帧节流</span>
            </el-form-item>
            <el-form-item label="自动通过阈值">
              <div class="slider-item">
                <el-slider v-model="flywheel.autoLabelMin" :min="0.4" :max="0.99" :step="0.05" style="width: 300px" />
                <span class="slider-value">{{ (flywheel.autoLabelMin * 100).toFixed(0) }}%</span>
              </div>
              <div class="form-desc">告警帧最高置信度不低于此值时，若开启下方开关才自动通过</div>
            </el-form-item>
            <el-form-item label="告警自动通过">
              <el-switch v-model="flywheel.autoApproveAlerts" />
              <span class="form-tip">关闭后告警帧一律进待审，便于标注台看到数据</span>
            </el-form-item>
            <el-form-item label="人工审核">
              <el-button type="primary" @click="goDesk">打开标注台</el-button>
              <span class="form-tip">待审 {{ stats.byStatus?.pending || 0 }} · 已通过 {{ stats.byStatus?.approved || 0 }}</span>
            </el-form-item>

            <el-divider />
            <h4 class="section-title">自学习训练</h4>
            <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
              <template #title>在现有 best.pt 上微调，不推倒重来</template>
              <p style="margin: 8px 0 0">
                把标注台通过的现场图混入
                <code>{{ flywheel.trainRoot }}</code>
                原数据集，训练后对比验证集 mAP50，变差则不上线。
              </p>
            </el-alert>
            <el-form-item label="训练目录">
              <el-input v-model="flywheel.trainRoot" placeholder="yolov8modle 根目录" />
            </el-form-item>
            <el-form-item label="轮数">
              <el-input-number v-model="flywheel.epochs" :min="1" :max="200" />
              <span class="form-tip">增量微调建议 10–30</span>
            </el-form-item>
            <el-form-item label="batch">
              <el-input-number v-model="flywheel.batch" :min="1" :max="32" />
            </el-form-item>
            <el-form-item label="最少通过样本">
              <el-input-number v-model="flywheel.minReviewed" :min="1" :max="200" />
              <span class="form-tip">当前已通过 {{ train.approved }}</span>
            </el-form-item>
            <el-form-item label="训练">
              <el-button type="primary" :loading="train.busy" :disabled="train.busy" @click="startTrain">
                开始微调
              </el-button>
              <el-button
                v-if="train.run?.status === 'rejected' && train.run?.id"
                @click="promoteTrain"
              >
                仍要上线
              </el-button>
              <el-button
                v-if="train.run?.promoted && train.run?.id"
                @click="rollbackTrain"
              >
                回滚旧权重
              </el-button>
            </el-form-item>
            <div v-if="train.run" class="train-status">
              <el-tag :type="trainTag">{{ train.run.status }}</el-tag>
              <span>{{ train.run.message }}</span>
              <div v-if="train.run.oldMap50 != null" class="form-desc">
                mAP50 旧 {{ train.run.oldMap50 }} → 新 {{ train.run.newMap50 }}
              </div>
            </div>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { configApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { Tools, Aim, Lock, Message, User, EditPen } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const saveLoading = ref(false)
const activeMenu = ref('/config/detection')

const form = reactive({
  confidenceThreshold: 0.5,
  iouThreshold: 0.45,
  fps: 2,
  maxDetections: 100,
  categories: [] as string[],
  trackingEnabled: true,
  trackLostFrames: 30,
  modelPath: '',
  inferEnabled: true
})

const categoryOptions = ref<string[]>([])

const flywheel = reactive({
  enabled: true,
  alertFrames: true,
  uncertainFrames: true,
  uncertainLow: 0.25,
  uncertainHigh: 0.55,
  quotaPerCameraHour: 40,
  sampleIntervalSec: 15,
  autoLabelMin: 0.7,
  autoApproveAlerts: false,
  trainRoot: 'D:\\pythonDev\\industrial_anomaly_detection\\yolov8modle',
  epochs: 15,
  batch: 4,
  imgsz: 640,
  minReviewed: 5,
  maxMapDrop: 0.01,
  trainDevice: 'cpu'
})

const train = reactive({
  busy: false,
  approved: 0,
  run: null as any
})

let trainTimer: number | null = null

const trainTag = computed(() => {
  const s = train.run?.status
  if (s === 'promoted') return 'success'
  if (s === 'failed' || s === 'rejected') return 'danger'
  if (s === 'queued') return 'info'
  if (s === 'running') return 'warning'
  return 'info'
})

const stats = reactive({
  today: 0,
  total: 0,
  bucket: 'yolov8pro',
  prefix: 'flywheel/dataset',
  bySource: { alert: 0, uncertain: 0 },
  byStatus: { pending: 0, approved: 0, discarded: 0 }
})

async function loadData() {
  loading.value = true
  try {
    const [res, fw, st, tr]: any[] = await Promise.all([
      configApi.getDetection(),
      configApi.getFlywheel(),
      configApi.getFlywheelStats(),
      configApi.getFlywheelTrain()
    ])
    if (res) {
      form.confidenceThreshold = res.confidenceThreshold ?? 0.5
      form.iouThreshold = res.iouThreshold ?? 0.45
      form.fps = res.fps ?? 2
      form.maxDetections = res.maxDetections ?? 100
      form.categories = Array.isArray(res.categories) ? [...res.categories] : form.categories
      form.trackingEnabled = res.trackingEnabled !== false
      form.trackLostFrames = res.trackLostFrames ?? 30
      form.modelPath = res.modelPath || ''
      form.inferEnabled = res.inferEnabled !== false
      categoryOptions.value = Array.isArray(res.categoryOptions) && res.categoryOptions.length
        ? [...res.categoryOptions]
        : [...form.categories]
    }
    if (fw) Object.assign(flywheel, fw)
    if (st) {
      stats.today = st.today || 0
      stats.total = st.total || 0
      stats.bucket = st.bucket || stats.bucket
      stats.prefix = st.prefix || stats.prefix
      stats.bySource = st.bySource || stats.bySource
      stats.byStatus = st.byStatus || stats.byStatus
    }
    applyTrain(tr)
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saveLoading.value = true
  try {
    const res: any = await configApi.updateDetection({
      confidenceThreshold: form.confidenceThreshold,
      iouThreshold: form.iouThreshold,
      fps: form.fps,
      maxDetections: form.maxDetections,
      categories: form.categories,
      trackingEnabled: form.trackingEnabled,
      trackLostFrames: form.trackLostFrames,
      inferEnabled: form.inferEnabled,
      modelPath: form.modelPath?.trim() || undefined
    })
    const fwRes: any = await configApi.updateFlywheel({ ...flywheel })
    if (res?.detection) {
      Object.assign(form, {
        confidenceThreshold: res.detection.confidenceThreshold,
        iouThreshold: res.detection.iouThreshold,
        fps: res.detection.fps,
        maxDetections: res.detection.maxDetections,
        categories: [...(res.detection.categories || [])],
        trackingEnabled: res.detection.trackingEnabled !== false,
        trackLostFrames: res.detection.trackLostFrames,
        modelPath: res.detection.modelPath || form.modelPath,
        inferEnabled: res.detection.inferEnabled !== false
      })
      if (Array.isArray(res.detection.categoryOptions) && res.detection.categoryOptions.length) {
        categoryOptions.value = [...res.detection.categoryOptions]
      }
    }
    if (fwRes?.flywheel) Object.assign(flywheel, fwRes.flywheel)
    ElMessage.success(res?.message || '检测参数已更新并立即生效')
  } catch (e) {
    // 错误已处理
  } finally {
    saveLoading.value = false
  }
}

function applyTrain(tr: any) {
  if (!tr) return
  train.approved = tr.approved || 0
  train.busy = !!tr.busy
  train.run = tr.run || null
  if (train.busy) startTrainPoll()
  else stopTrainPoll()
}

function startTrainPoll() {
  if (trainTimer != null) return
  trainTimer = window.setInterval(async () => {
    try {
      applyTrain(await configApi.getFlywheelTrain())
    } catch {
      /* ignore */
    }
  }, 4000)
}

function stopTrainPoll() {
  if (trainTimer != null) {
    clearInterval(trainTimer)
    trainTimer = null
  }
}

async function startTrain() {
  try {
    const res: any = await configApi.startFlywheelTrain()
    applyTrain({ ...res, busy: true, approved: train.approved })
    ElMessage.success(res?.message || '训练已开始')
    startTrainPoll()
  } catch {
    /* 错误已处理 */
  }
}

async function promoteTrain() {
  if (!train.run?.id) return
  try {
    const res: any = await configApi.promoteFlywheelTrain(train.run.id)
    train.run = res.run
    ElMessage.success(res?.message || '已上线')
  } catch {
    /* ignore */
  }
}

async function rollbackTrain() {
  if (!train.run?.id) return
  try {
    const res: any = await configApi.rollbackFlywheelTrain(train.run.id)
    train.run = res.run
    ElMessage.success(res?.message || '已回滚')
  } catch {
    /* ignore */
  }
}

function goDesk() {
  router.push('/flywheel')
}

onMounted(() => {
  activeMenu.value = route.path
  loadData()
})

onUnmounted(() => {
  stopTrainPoll()
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

.category-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.form-tip {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
}

.flywheel-stats {
  margin-bottom: 16px;
}

.fw-stat {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px 8px;
  text-align: center;
}

.fw-num {
  font-size: 20px;
  font-weight: 600;
  color: #1677ff;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.fw-label {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}

.train-status {
  margin: 0 0 12px 140px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #4b5563;
}
</style>
