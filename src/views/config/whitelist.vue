<template>
  <div class="config-page">
    <el-row :gutter="20">
      <el-col :span="4">
        <el-card class="nav-card">
          <ConfigSideMenu />
        </el-card>
      </el-col>

      <el-col :span="20">
  <div class="whitelist-page">
    <el-card class="top-card" shadow="never">
      <div class="top-row">
        <div class="top-left">
          <div class="page-title">白名单规则</div>
          <div class="page-desc">
            命中白名单的目标（按摄像头 / 类别 / trackId / 人脸 ID 过滤）不触发告警和推送。
            人脸模糊（侧脸、遮挡、光线差）的处理策略：
            <el-select v-model="cfg.faceUnclearPolicy" style="width: 140px; margin: 0 6px" @change="dirty = true">
              <el-option label="按正常流程告警（默认）" value="alert" />
              <el-option label="转为待确认状态" value="review" />
              <el-option label="直接抑制" value="suppress" />
            </el-select>
            ，宁可多报，不可漏报。
          </div>
        </div>
        <div class="top-right">
          <el-switch v-model="cfg.enabled" active-text="启用白名单" inactive-text="全部告警" @change="dirty = true" />
          <el-button style="margin-left: 12px" @click="faceLibVisible = true">人脸库</el-button>
          <el-button style="margin-left: 12px" @click="addRule">+ 新增规则</el-button>
          <el-button type="primary" :disabled="!dirty" :loading="saving" @click="save">保存</el-button>
        </div>
      </div>
    </el-card>

    <el-card class="rules-card" shadow="never">
      <el-alert v-if="cfg.enabled && rules.length === 0" type="info" :closable="false" title="暂未配置规则——所有检测到的目标都会正常触发告警" />
      <el-alert v-else-if="!cfg.enabled" type="warning" :closable="false" title="白名单当前已关闭，所有检测到的目标都会正常触发告警" />

      <div v-for="(rule, idx) in rules" :key="rule.id" class="rule-block">
        <div class="rule-head">
          <el-input v-model="rule.name" style="width: 200px" placeholder="规则名称" @input="dirty = true" />
          <el-tag v-if="rule.enabled" type="success" size="small">启用</el-tag>
          <el-tag v-else type="info" size="small">关闭</el-tag>
          <el-switch v-model="rule.enabled" style="margin-left: 8px" @change="dirty = true" />
          <el-tag size="small" style="margin-left: auto">ID {{ rule.id }}</el-tag>
          <el-button link type="danger" size="small" @click="removeRule(idx)">删除</el-button>
        </div>

        <div class="rule-body">
          <div class="field">
            <label>告警类型</label>
            <el-select v-model="rule.alertTypes" multiple collapse-tags placeholder="全部类型" @change="dirty = true">
              <el-option label="区域入侵" value="intrusion" />
              <el-option label="违停占道" value="parking" />
              <el-option label="火灾隐患" value="fire" />
              <el-option label="服务异常" value="service" />
            </el-select>
          </div>

          <div class="field">
            <label>类别（label）</label>
            <el-select v-model="rule.labels" multiple collapse-tags placeholder="全部类别" @change="dirty = true">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
            <div class="hint">白名单的物体类别，比如 "轿车"、"person"、"bus"</div>
          </div>

          <div class="field">
            <label>摄像头</label>
            <el-select v-model="rule.cameras" multiple collapse-tags placeholder="全部摄像头" @change="dirty = true">
              <el-option v-for="c in cameras" :key="c.id" :label="`${c.id} ${c.name}`" :value="c.id" />
            </el-select>
          </div>

          <div class="field">
            <label>trackId</label>
            <el-input v-model="rule.trackIdsText" placeholder="逗号分隔，如 12, 34" @input="syncTrackIds(rule)" />
            <div class="hint">仅豁免该 tracking 序列 ID。空 = 不按 trackId 过滤</div>
          </div>

          <div class="field">
            <label>人脸 ID</label>
            <el-input v-model="rule.faceIdsText" placeholder="逗号分隔，如 fae-001, fae-002" @input="syncFaceIds(rule)" />
            <div class="hint">需要 yolo-service 输出 faceId 才生效。空 = 不按人脸过滤</div>
          </div>

          <div class="field">
            <label>置信度上限</label>
            <el-input-number v-model="rule.maxConfidence" :min="0.05" :max="0.99" :step="0.05" :precision="2"
                             controls-position="right" :placeholder="'不限制'" @change="dirty = true" />
            <div class="hint">仅豁免置信度 ≤ 该值的低置信度目标。不填则无限制</div>
          </div>
        </div>
      </div>

      <el-empty v-if="rules.length === 0" description="暂无白名单规则">
        <el-button type="primary" @click="addRule">新增第一条规则</el-button>
      </el-empty>
    </el-card>

    <el-dialog v-model="faceLibVisible" title="人脸库管理" width="760px" @open="loadFaces">
      <div class="enroll-row">
        <el-input v-model="enrollName" placeholder="姓名，如 张三" style="width: 180px" clearable />
        <el-upload :auto-upload="false" :show-file-list="false" accept="image/*" :on-change="onFaceFileChange">
          <el-button>选择照片</el-button>
        </el-upload>
        <span v-if="enrollFile" class="file-name">{{ enrollFile.name }}</span>
        <el-button type="primary" :disabled="!enrollName.trim() || !enrollFile" :loading="enrolling" @click="submitEnroll">注册</el-button>
      </div>
      <div class="hint" style="margin-bottom: 12px">使用清晰正脸照片。注册后点「复制」拿到 faceId，填进规则的「人脸 ID」字段即可生效。</div>

      <el-table :data="faces" v-loading="facesLoading" size="small" max-height="380">
        <el-table-column label="照片" width="70">
          <template #default="{ row }">
            <el-image v-if="row.hasPhoto" :src="facePhotoUrl(row.faceId)" style="width: 44px; height: 44px; border-radius: 4px" fit="cover" :preview-src-list="[facePhotoUrl(row.faceId)]" preview-teleported />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="姓名" width="110" />
        <el-table-column label="faceId" min-width="170">
          <template #default="{ row }">
            <span class="fid">{{ row.faceId }}</span>
            <el-button link size="small" type="primary" @click="copyFaceId(row.faceId)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80" />
        <el-table-column label="注册时间" min-width="150">
          <template #default="{ row }">{{ fmtTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeFace(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { configApi, cameraApi } from '@/api'
import ConfigSideMenu from '@/components/ConfigSideMenu.vue'

type Camera = { id: number; name: string; rtspConfigured?: boolean }

const cameras = ref<Camera[]>([])
const categories = ref<string[]>([])
const saving = ref(false)
const dirty = ref(false)

function emptyRule(): any {
  return {
    id: Math.random().toString(36).slice(2, 14),
    name: '',
    enabled: true,
    alertTypes: [],
    labels: [],
    trackIds: [],
    faceIds: [],
    trackIdsText: '',
    faceIdsText: '',
    cameras: [],
    maxConfidence: null as number | null,
  }
}

const cfg = reactive<any>({
  enabled: true,
  faceUnclearPolicy: 'alert',
  rules: [],
})

const rules = computed({
  get: () => cfg.rules,
  set: (v) => { cfg.rules = v },
})

function syncTrackIds(rule: any) {
  rule.trackIds = (rule.trackIdsText || '')
    .split(/[,，\s]+/)
    .map((s: string) => s.trim())
    .filter(Boolean)
  dirty.value = true
}

function syncFaceIds(rule: any) {
  rule.faceIds = (rule.faceIdsText || '')
    .split(/[,，\s]+/)
    .map((s: string) => s.trim())
    .filter(Boolean)
  dirty.value = true
}

async function load() {
  try {
    const wl: any = await configApi.getWhitelist()
    cfg.enabled = wl.enabled !== false
    cfg.faceUnclearPolicy = wl.faceUnclearPolicy || 'alert'
    cfg.rules = (wl.rules || []).map((r: any) => ({
      ...emptyRule(),
      ...r,
      trackIdsText: (r.trackIds || []).join(', '),
      faceIdsText: (r.faceIds || []).join(', '),
    }))
  } catch {}
  try {
    const camRes: any = await cameraApi.getList({ page: 1, pageSize: 500 })
    cameras.value = camRes?.items || camRes?.list || camRes || []
  } catch {}
  try {
    const det: any = await configApi.getDetection()
    categories.value = det?.categories || []
  } catch {}
}

function addRule() {
  rules.value.push(emptyRule())
  dirty.value = true
}

function removeRule(idx: number) {
  ElMessageBox.confirm('确定删除这条规则？', '删除确认', { type: 'warning' })
    .then(() => {
      rules.value.splice(idx, 1)
      dirty.value = true
    })
    .catch(() => {})
}

async function save() {
  saving.value = true
  try {
    const payload = {
      enabled: cfg.enabled,
      faceUnclearPolicy: cfg.faceUnclearPolicy,
      rules: rules.value.map((r: any) => {
        // ensure trackIds/faceIds synced from textarea before save
        syncTrackIds(r)
        syncFaceIds(r)
        return {
          id: r.id,
          name: r.name || '未命名规则',
          enabled: !!r.enabled,
          alertTypes: r.alertTypes || [],
          labels: r.labels || [],
          trackIds: r.trackIds || [],
          faceIds: r.faceIds || [],
          cameras: r.cameras || [],
          maxConfidence: r.maxConfidence,
        }
      }),
    }
    await configApi.updateWhitelist(payload)
    dirty.value = false
    ElMessage.success('白名单配置已更新')
  } catch {
    /* interceptor */
  } finally {
    saving.value = false
  }
}

onMounted(load)

// ---------------- 人脸库 ----------------
const faceLibVisible = ref(false)
const faces = ref<any[]>([])
const facesLoading = ref(false)
const enrollName = ref('')
const enrollFile = ref<File | null>(null)
const enrolling = ref(false)

async function loadFaces() {
  facesLoading.value = true
  try {
    faces.value = (await configApi.listFaces()).list || []
  } finally {
    facesLoading.value = false
  }
}

function onFaceFileChange(uploadFile: any) {
  enrollFile.value = uploadFile.raw || null
}

async function submitEnroll() {
  if (!enrollFile.value || !enrollName.value.trim()) return
  enrolling.value = true
  try {
    const res = await configApi.enrollFace(enrollName.value.trim(), enrollFile.value)
    ElMessage.success(`已注册：${res.name}（${res.faceId}），可在规则中引用`)
    enrollName.value = ''
    enrollFile.value = null
    await loadFaces()
  } catch {
    // 拦截器已提示错误原因
  } finally {
    enrolling.value = false
  }
}

async function removeFace(row: any) {
  await ElMessageBox.confirm(
    `确认删除「${row.name || row.faceId}」？删除后引用该 faceId 的白名单规则将不再命中。`,
    '删除人脸',
    { type: 'warning' },
  )
  await configApi.deleteFace(row.faceId)
  ElMessage.success('已删除')
  await loadFaces()
}

const facePhotoUrl = (fid: string) => configApi.facePhotoUrl(fid)

async function copyFaceId(fid: string) {
  try {
    await navigator.clipboard.writeText(fid)
    ElMessage.success(`已复制 ${fid}`)
  } catch {
    ElMessage.info(fid)
  }
}

function fmtTime(iso: string) {
  return iso ? iso.replace('T', ' ').slice(0, 19) : '—'
}
</script>

<style scoped>
.config-page { padding: 4px; }
.nav-card { padding: 0; }
.whitelist-page { padding: 0; }
.enroll-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.file-name { color: #909399; font-size: 12px; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fid { font-family: Consolas, monospace; font-size: 12px; margin-right: 4px; }
.top-card { margin-bottom: 16px; }
.top-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.top-left { flex: 1; }
.page-title { font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 4px; }
.page-desc { color: #6b7280; font-size: 13px; line-height: 1.6; }
.top-right { display: flex; align-items: center; gap: 8px; }

.rule-block {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  background: #fafafa;
}
.rule-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.rule-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 18px;
}
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: #6b7280; font-weight: 500; }
.hint { font-size: 11px; color: #9ca3af; line-height: 1.4; }
</style>
