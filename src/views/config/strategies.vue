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
              <span class="card-title">布防策略管理</span>
              <el-button type="primary" :icon="Plus" @click="handleAdd">新增策略</el-button>
            </div>
          </template>

          <el-table :data="strategies" border stripe>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="name" label="策略名称" min-width="150" />
            <el-table-column label="关联摄像头" min-width="200">
              <template #default="{ row }">
                <div class="camera-tags">
                  <el-tag
                    v-for="name in row.cameraNames?.slice(0, 3)"
                    :key="name"
                    size="small"
                    type="info"
                    style="margin-right: 4px"
                  >
                    {{ name }}
                  </el-tag>
                  <span v-if="(row.cameraIds?.length || 0) > 3" class="more-text">
                    +{{ row.cameraIds.length - 3 }}
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="检测类型" width="150">
              <template #default="{ row }">
                <el-tag v-for="t in row.detectionTypes" :key="t" size="small" style="margin-right: 4px">
                  {{ typeText(t) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="布防时间" width="140">
              <template #default="{ row }">
                {{ scheduleText(row.schedule) }}
              </template>
            </el-table-column>
            <el-table-column label="告警级别" width="90">
              <template #default="{ row }">
                <el-tag :type="levelTagType(row.alertLevel)" size="small">
                  {{ levelText(row.alertLevel) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" size="small" @change="handleToggle(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="handleEdit(row)">编辑</el-button>
                <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'add' ? '新增布防策略' : '编辑布防策略'"
      width="600px"
    >
      <el-form :model="formData" label-width="100px">
        <el-form-item label="策略名称">
          <el-input v-model="formData.name" placeholder="请输入策略名称" />
        </el-form-item>
        <el-form-item label="关联摄像头">
          <el-select
            v-model="formData.cameraIds"
            multiple
            filterable
            placeholder="请选择摄像头"
            style="width: 100%"
          >
            <el-option
              v-for="cam in cameraOptions"
              :key="cam.id"
              :label="cam.name"
              :value="cam.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="检测类型">
          <el-checkbox-group v-model="formData.detectionTypes">
            <el-checkbox value="intrusion">区域入侵</el-checkbox>
            <el-checkbox value="parking">违停检测</el-checkbox>
            <el-checkbox value="fire">火灾检测</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="布防时间">
          <el-radio-group v-model="formData.schedule.type">
            <el-radio value="always">全天布防</el-radio>
            <el-radio value="custom">自定义时段</el-radio>
            <el-radio value="worktime">工作时间</el-radio>
            <el-radio value="night">夜间</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="formData.schedule.type === 'custom'" label="时间段">
          <el-time-picker
            v-model="formData.schedule.start"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="开始时间"
          />
          <span style="margin: 0 8px">至</span>
          <el-time-picker
            v-model="formData.schedule.end"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="结束时间"
          />
        </el-form-item>
        <el-form-item label="告警级别">
          <el-radio-group v-model="formData.alertLevel">
            <el-radio value="high">高危</el-radio>
            <el-radio value="medium">中危</el-radio>
            <el-radio value="low">低危</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { configApi, cameraApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, Aim, Lock, Message, User, Plus } from '@element-plus/icons-vue'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const submitLoading = ref(false)
const activeMenu = ref('/config/strategies')
const strategies = ref<any[]>([])
const cameraOptions = ref<any[]>([])
const dialogVisible = ref(false)
const dialogMode = ref<'add' | 'edit'>('add')

const formData = reactive<any>({
  name: '',
  cameraIds: [] as number[],
  detectionTypes: ['intrusion'] as string[],
  schedule: { type: 'always' as string, start: '08:00', end: '20:00' },
  alertLevel: 'medium',
  enabled: true
})

function typeText(type: string) {
  const map: Record<string, string> = {
    intrusion: '区域入侵',
    parking: '违停检测',
    fire: '火灾检测'
  }
  return map[type] || type
}

function levelText(level: string) {
  const map: Record<string, string> = { high: '高危', medium: '中危', low: '低危' }
  return map[level] || level
}

function levelTagType(level: string) {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', low: 'info' }
  return map[level] || 'info'
}

function scheduleText(schedule: any) {
  if (!schedule) return '-'
  const map: Record<string, string> = {
    always: '全天布防',
    worktime: '工作时间 08:00-20:00',
    night: '夜间 22:00-06:00',
    custom: `${schedule.start} - ${schedule.end}`
  }
  return map[schedule.type] || '-'
}

async function loadData() {
  loading.value = true
  try {
    const [stratRes, camRes] = await Promise.all([
      configApi.getStrategies(),
      cameraApi.getAll()
    ])
    strategies.value = (stratRes as any).list || []
    cameraOptions.value = (camRes as any) || []
  } finally {
    loading.value = false
  }
}

function handleAdd() {
  dialogMode.value = 'add'
  Object.assign(formData, {
    name: '',
    cameraIds: [],
    detectionTypes: ['intrusion'],
    schedule: { type: 'always', start: '08:00', end: '20:00' },
    alertLevel: 'medium',
    enabled: true
  })
  dialogVisible.value = true
}

function handleEdit(row: any) {
  dialogMode.value = 'edit'
  Object.assign(formData, JSON.parse(JSON.stringify(row)))
  if (!formData.schedule) {
    formData.schedule = { type: 'always', start: '08:00', end: '20:00' }
  }
  dialogVisible.value = true
}

async function handleToggle(row: any) {
  try {
    await configApi.toggleStrategy(row.id)
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch (e) {
    row.enabled = !row.enabled
  }
}

function handleDelete(row: any) {
  ElMessageBox.confirm(`确定要删除策略"${row.name}"吗？`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    await configApi.deleteStrategy(row.id)
    ElMessage.success('删除成功')
    loadData()
  }).catch(() => {})
}

async function handleSubmit() {
  submitLoading.value = true
  try {
    if (dialogMode.value === 'add') {
      await configApi.addStrategy(formData)
      ElMessage.success('新增成功')
    } else {
      await configApi.updateStrategy(formData.id, formData)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    // 错误已处理
  } finally {
    submitLoading.value = false
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

.camera-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.more-text {
  font-size: 12px;
  color: #9ca3af;
}
</style>
