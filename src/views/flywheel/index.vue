<template>
  <div class="desk-page">
    <el-card class="desk-card">
          <template #header>
            <div class="card-header">
              <div>
                <span class="card-title">标注台</span>
                <span class="card-sub">仅「已通过」进入训练集 · A 通过 / X 丢弃 / N 下一张 / S 保存 / H 隐藏框 / D 画框 / V 选择{{ trainMsg ? ' · ' + trainMsg : '' }}</span>
              </div>
              <div class="header-stats">
                <el-button text type="primary" @click="goDetection">采集设置</el-button>
                <el-button type="primary" :loading="trainBusy" :disabled="trainBusy" @click="startTrain">开始微调</el-button>
                <el-tag type="warning">待审 {{ stats.pending }}</el-tag>
                <el-tag type="success">已通过 {{ stats.approved }}</el-tag>
                <el-tag type="info">已丢弃 {{ stats.discarded }}</el-tag>
              </div>
            </div>
          </template>

          <el-row :gutter="16" class="desk-body">
            <el-col :span="17">
              <div v-if="sample" class="stage-toolbar">
                <el-radio-group v-model="tool" size="small">
                  <el-radio-button value="select">选择纠正</el-radio-button>
                  <el-radio-button value="draw">画新框</el-radio-button>
                </el-radio-group>
                <el-button size="small" :type="showBoxes ? 'default' : 'warning'" @click="toggleBoxes">
                  {{ showBoxes ? '隐藏框看原图' : '显示标注框' }}
                </el-button>
                <el-button size="small" type="danger" plain :disabled="!boxes.length" @click="clearBoxes">
                  清空重标
                </el-button>
                <el-button-group>
                  <el-button size="small" @click="setZoom('fit')">适应</el-button>
                  <el-button size="small" @click="setZoom(1)">100%</el-button>
                  <el-button size="small" @click="setZoom(1.5)">150%</el-button>
                  <el-button size="small" @click="setZoom(2)">200%</el-button>
                </el-button-group>
                <span class="toolbar-hint">{{ toolHint }}</span>
              </div>
              <div v-loading="loading" class="stage-wrap">
                <div v-if="!sample" class="empty">
                  <el-empty description="没有待审样本。采集开启后告警帧 / 不确定帧会进入队列。" />
                </div>
                <div v-else class="stage" ref="stageRef">
                  <img
                    v-if="imageUrl"
                    ref="imgRef"
                    :src="imageUrl"
                    :style="imgStyle"
                    alt="sample"
                    draggable="false"
                    @load="onImgLoad"
                  />
                  <canvas
                    ref="cvRef"
                    class="overlay"
                    :class="{ drawing: tool === 'draw' }"
                    @mousedown.prevent="onDown"
                    @mousemove="onMove"
                    @mouseup="onUp"
                    @mouseleave="onUp"
                    @dblclick.prevent="removeSelected"
                  />
                </div>
              </div>
            </el-col>
            <el-col :span="7">
              <div v-if="sample" class="meta">
                <div class="meta-row"><span>样本</span><b>#{{ sample.id }}</b></div>
                <div class="meta-row"><span>摄像头</span><b>{{ sample.cameraName }}</b></div>
                <div class="meta-row">
                  <span>来源</span>
                  <el-tag size="small" :type="sample.source === 'alert' ? 'danger' : 'warning'">
                    {{ sample.source === 'alert' ? '告警帧' : '不确定帧' }}
                  </el-tag>
                </div>
                <div class="meta-row"><span>置信度</span><b>{{ (sample.maxConf * 100).toFixed(0) }}%</b></div>
              </div>

              <div class="panel-title">当前类别</div>
              <el-select v-model="drawLabel" size="small" style="width: 100%" @change="applyLabelToSelected">
                <el-option v-for="name in classNames" :key="name" :label="name" :value="name" />
              </el-select>

              <div class="panel-title">检测框 {{ boxes.length }}</div>
              <div class="box-list">
                <div
                  v-for="(box, idx) in boxes"
                  :key="box.id"
                  class="box-item"
                  :class="{ active: selectedId === box.id }"
                  @click="selectBox(box.id)"
                >
                  <span class="swatch" :style="{ background: colorOf(box.label) }" />
                  <span class="box-name">{{ box.label }}</span>
                  <el-button type="danger" link size="small" @click.stop="removeBox(idx)">删</el-button>
                </div>
                <div v-if="!boxes.length" class="hint">切到「画新框」后拖拽绘制；双击删除选中框</div>
              </div>

              <div class="actions">
                <el-button type="success" :disabled="!sample || busy" :loading="busy" @click="approve">通过 (A)</el-button>
                <el-button type="danger" :disabled="!sample || busy" @click="discard">丢弃 (X)</el-button>
                <el-button :disabled="busy" @click="goNext">下一张 (N)</el-button>
                <el-button :disabled="!sample || busy" @click="saveBoxes">保存框 (S)</el-button>
              </div>

              <div class="panel-title">待审队列</div>
              <div class="queue">
                <div
                  v-for="item in queue"
                  :key="item.id"
                  class="queue-item"
                  :class="{ current: sample?.id === item.id }"
                  @click="openSample(item.id)"
                >
                  <span>#{{ item.id }}</span>
                  <span>{{ item.cameraName }}</span>
                  <span>{{ item.source === 'alert' ? '告警' : '难例' }}</span>
                </div>
                <div v-if="!queue.length" class="hint">队列为空</div>
              </div>
            </el-col>
          </el-row>
        </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { configApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

type BBox = { x: number; y: number; w: number; h: number }
type Box = { id: number; label: string; confidence: number; bbox: BBox }
type Sample = {
  id: number
  cameraId: number
  cameraName: string
  source: string
  status: string
  maxConf: number
  boxes?: Box[]
  classNames?: string[]
}

const PALETTE = ['#1677ff', '#f5222d', '#52c41a', '#fa8c16', '#722ed1', '#13c2c2', '#eb2f96']

const router = useRouter()
const loading = ref(false)
const busy = ref(false)
const sample = ref<Sample | null>(null)
const boxes = ref<Box[]>([])
const classNames = ref<string[]>([])
const drawLabel = ref('火焰')
const selectedId = ref(0)
const imageUrl = ref('')
const queue = ref<Sample[]>([])
const stats = reactive({ pending: 0, approved: 0, discarded: 0 })
const trainBusy = ref(false)
const trainMsg = ref('')
let trainTimer: number | null = null

const stageRef = ref<HTMLElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const cvRef = ref<HTMLCanvasElement | null>(null)
const tool = ref<'select' | 'draw'>('select')
const showBoxes = ref(true)
const zoomMode = ref<'fit' | number>('fit')
const natural = reactive({ w: 0, h: 0 })

const toolHint = computed(() => {
  if (!showBoxes.value) return '框已隐藏，可看清原图；切回显示后再改框'
  if (tool.value === 'draw') return '拖拽画新框（不会误拖旧框）'
  return '点选后拖动/拉角纠正 · 双击删除'
})

const imgStyle = computed(() => {
  if (zoomMode.value === 'fit' || !natural.w) {
    return { maxWidth: '100%', maxHeight: 'calc(100vh - 280px)', width: 'auto', height: 'auto' }
  }
  const z = Number(zoomMode.value)
  return {
    width: `${Math.round(natural.w * z)}px`,
    height: 'auto',
    maxWidth: 'none',
    maxHeight: 'none'
  }
})

type Handle = 'nw' | 'ne' | 'sw' | 'se' | ''
const drag = reactive({
  mode: '' as '' | 'draw' | 'move' | 'resize',
  handle: '' as Handle,
  startX: 0,
  startY: 0,
  orig: { x: 0, y: 0, w: 0, h: 0 } as BBox
})
let draft: BBox | null = null
let observer: ResizeObserver | null = null

const selected = computed(() => boxes.value.find((b) => b.id === selectedId.value) || null)

function colorOf(label: string) {
  const i = Math.max(0, classNames.value.indexOf(label))
  return PALETTE[i % PALETTE.length]
}

function clampBox(b: BBox): BBox {
  let x = Math.min(1, Math.max(0, b.x))
  let y = Math.min(1, Math.max(0, b.y))
  let w = Math.min(1 - x, Math.max(0.004, b.w))
  let h = Math.min(1 - y, Math.max(0.004, b.h))
  return { x, y, w, h }
}

function canvasScale() {
  const cv = cvRef.value
  if (!cv) return 1
  const r = cv.getBoundingClientRect()
  return r.width > 0 ? cv.width / r.width : 1
}

function handleSize() {
  return Math.max(8, 8 * canvasScale())
}

function canvasPoint(ev: MouseEvent) {
  const cv = cvRef.value
  if (!cv) return { x: 0, y: 0 }
  const r = cv.getBoundingClientRect()
  if (r.width < 1 || r.height < 1) return { x: 0, y: 0 }
  return {
    x: (ev.clientX - r.left) * (cv.width / r.width),
    y: (ev.clientY - r.top) * (cv.height / r.height)
  }
}

function toNorm(px: number, py: number): { x: number; y: number } {
  const cv = cvRef.value
  if (!cv || !cv.width || !cv.height) return { x: 0, y: 0 }
  return { x: px / cv.width, y: py / cv.height }
}

function toPx(b: BBox) {
  const cv = cvRef.value
  const w = cv?.width || 1
  const h = cv?.height || 1
  return { x: b.x * w, y: b.y * h, w: b.w * w, h: b.h * h }
}

function hitHandle(px: number, py: number, box: Box): Handle {
  const r = toPx(box.bbox)
  const pad = handleSize()
  const pts: [Handle, number, number][] = [
    ['nw', r.x, r.y],
    ['ne', r.x + r.w, r.y],
    ['sw', r.x, r.y + r.h],
    ['se', r.x + r.w, r.y + r.h]
  ]
  for (const [name, hx, hy] of pts) {
    if (Math.abs(px - hx) <= pad && Math.abs(py - hy) <= pad) return name
  }
  return ''
}

function hitBox(px: number, py: number): Box | null {
  for (let i = boxes.value.length - 1; i >= 0; i--) {
    const b = boxes.value[i]
    const r = toPx(b.bbox)
    if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) return b
  }
  return null
}

function draw() {
  const cv = cvRef.value
  const ctx = cv?.getContext('2d')
  if (!cv || !ctx) return
  ctx.clearRect(0, 0, cv.width, cv.height)
  const scale = canvasScale()
  const all: Box[] = []
  if (showBoxes.value) all.push(...boxes.value)
  if (draft) all.push({ id: 0, label: drawLabel.value, confidence: 1, bbox: draft })
  for (const box of all) {
    const r = toPx(box.bbox)
    const color = colorOf(box.label)
    const active = box.id === selectedId.value
    ctx.strokeStyle = color
    ctx.lineWidth = (active ? 2.5 : 1.6) * scale
    ctx.setLineDash([])
    ctx.strokeRect(r.x, r.y, r.w, r.h)
    if (active) {
      ctx.fillStyle = color
      ctx.globalAlpha = 0.08
      ctx.fillRect(r.x, r.y, r.w, r.h)
      ctx.globalAlpha = 1
    }
    ctx.font = `${Math.round(12 * scale)}px sans-serif`
    const tag = box.label
    const pad = 4 * scale
    const th = 16 * scale
    const tw = ctx.measureText(tag).width + pad * 2
    const ty = r.y > th + 2 ? r.y - th : r.y
    ctx.fillStyle = color
    ctx.fillRect(r.x, ty, tw, th)
    ctx.fillStyle = '#fff'
    ctx.fillText(tag, r.x + pad, ty + th - 4 * scale)
    if (active) {
      const hs = handleSize() / 2
      ctx.fillStyle = '#fff'
      ctx.strokeStyle = color
      ctx.lineWidth = 1.2 * scale
      const pts = [
        [r.x, r.y],
        [r.x + r.w, r.y],
        [r.x, r.y + r.h],
        [r.x + r.w, r.y + r.h]
      ]
      for (const [hx, hy] of pts) {
        ctx.fillRect(hx - hs, hy - hs, hs * 2, hs * 2)
        ctx.strokeRect(hx - hs, hy - hs, hs * 2, hs * 2)
      }
    }
  }
}

function bindObserver() {
  observer?.disconnect()
  observer = null
  const img = imgRef.value
  if (!img) return
  observer = new ResizeObserver(() => syncCanvas())
  observer.observe(img)
}

function syncCanvas() {
  const img = imgRef.value
  const cv = cvRef.value
  if (!img || !cv) return
  const w = img.clientWidth
  const h = img.clientHeight
  if (w < 2 || h < 2) return
  const dpr = window.devicePixelRatio || 1
  const bw = Math.max(1, Math.round(w * dpr))
  const bh = Math.max(1, Math.round(h * dpr))
  cv.style.width = `${w}px`
  cv.style.height = `${h}px`
  if (cv.width !== bw || cv.height !== bh) {
    cv.width = bw
    cv.height = bh
  }
  draw()
}

function onImgLoad() {
  const img = imgRef.value
  if (img) {
    natural.w = img.naturalWidth
    natural.h = img.naturalHeight
  }
  nextTick(() => {
    requestAnimationFrame(() => {
      syncCanvas()
      bindObserver()
    })
  })
}

function setZoom(mode: 'fit' | number) {
  zoomMode.value = mode
  nextTick(() => requestAnimationFrame(() => syncCanvas()))
}

function toggleBoxes() {
  showBoxes.value = !showBoxes.value
  draw()
}

async function clearBoxes() {
  if (!boxes.value.length) {
    tool.value = 'draw'
    showBoxes.value = true
    return
  }
  try {
    await ElMessageBox.confirm('清空当前全部检测框，然后重新画框？', '清空重标', {
      type: 'warning',
      confirmButtonText: '清空并画框',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  boxes.value = []
  selectedId.value = 0
  tool.value = 'draw'
  showBoxes.value = true
  draw()
}

function onDown(ev: MouseEvent) {
  if (!sample.value) return
  const p = canvasPoint(ev)
  const current = selected.value
  if (tool.value === 'select' && current && showBoxes.value) {
    const handle = hitHandle(p.x, p.y, current)
    if (handle) {
      drag.mode = 'resize'
      drag.handle = handle
      drag.startX = p.x
      drag.startY = p.y
      drag.orig = { ...current.bbox }
      return
    }
  }
  if (tool.value === 'select' && showBoxes.value) {
    const hit = hitBox(p.x, p.y)
    if (hit) {
      selectedId.value = hit.id
      drawLabel.value = hit.label
      drag.mode = 'move'
      drag.handle = ''
      drag.startX = p.x
      drag.startY = p.y
      drag.orig = { ...hit.bbox }
      draw()
      return
    }
  }
  selectedId.value = 0
  drag.mode = 'draw'
  drag.startX = p.x
  drag.startY = p.y
  draft = null
  if (!showBoxes.value) showBoxes.value = true
  draw()
}

function onMove(ev: MouseEvent) {
  if (!drag.mode) return
  const p = canvasPoint(ev)
  const a = toNorm(drag.startX, drag.startY)
  const b = toNorm(p.x, p.y)
  if (drag.mode === 'draw') {
    const x = Math.min(a.x, b.x)
    const y = Math.min(a.y, b.y)
    draft = clampBox({ x, y, w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) })
    draw()
    return
  }
  const box = selected.value
  if (!box) return
  if (drag.mode === 'move') {
    box.bbox = clampBox({
      x: drag.orig.x + (b.x - a.x),
      y: drag.orig.y + (b.y - a.y),
      w: drag.orig.w,
      h: drag.orig.h
    })
  } else if (drag.mode === 'resize') {
    const o = drag.orig
    let x1 = o.x
    let y1 = o.y
    let x2 = o.x + o.w
    let y2 = o.y + o.h
    if (drag.handle.includes('n')) y1 = b.y
    if (drag.handle.includes('s')) y2 = b.y
    if (drag.handle.includes('w')) x1 = b.x
    if (drag.handle.includes('e')) x2 = b.x
    box.bbox = clampBox({
      x: Math.min(x1, x2),
      y: Math.min(y1, y2),
      w: Math.abs(x2 - x1),
      h: Math.abs(y2 - y1)
    })
  }
  draw()
}

function onUp() {
  if (drag.mode === 'draw' && draft && draft.w > 0.01 && draft.h > 0.01) {
    const id = (boxes.value.reduce((m, b) => Math.max(m, b.id), 0) || 0) + 1
    boxes.value.push({
      id,
      label: drawLabel.value,
      confidence: 1,
      bbox: draft
    })
    selectedId.value = id
  }
  draft = null
  drag.mode = ''
  drag.handle = ''
  draw()
}

function selectBox(id: number) {
  selectedId.value = id
  tool.value = 'select'
  showBoxes.value = true
  const box = boxes.value.find((b) => b.id === id)
  if (box) drawLabel.value = box.label
  draw()
}

function applyLabelToSelected() {
  const box = selected.value
  if (box) box.label = drawLabel.value
  draw()
}

function removeBox(idx: number) {
  const [gone] = boxes.value.splice(idx, 1)
  if (gone && selectedId.value === gone.id) selectedId.value = 0
  draw()
}

function removeSelected() {
  const idx = boxes.value.findIndex((b) => b.id === selectedId.value)
  if (idx >= 0) removeBox(idx)
}

function revokeImage() {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = ''
  }
}

async function loadStats() {
  const st: any = await configApi.getFlywheelStats()
  stats.pending = st?.byStatus?.pending || 0
  stats.approved = st?.byStatus?.approved || 0
  stats.discarded = st?.byStatus?.discarded || 0
}

async function loadQueue() {
  const res: any = await configApi.getFlywheelSamples({ status: 'pending', page: 1, pageSize: 30 })
  queue.value = res?.list || []
}

async function loadImage(id: number) {
  revokeImage()
  const blob = (await configApi.getFlywheelSampleImage(id)) as unknown as Blob
  if (!blob || (blob.type && !blob.type.startsWith('image/') && blob.type !== 'application/octet-stream')) {
    ElMessage.error('样本图片加载失败')
    return
  }
  imageUrl.value = URL.createObjectURL(blob)
}

async function applySample(row: Sample) {
  sample.value = row
  boxes.value = (row.boxes || []).map((b, i) => ({
    id: b.id || i + 1,
    label: b.label,
    confidence: b.confidence ?? 1,
    bbox: { ...b.bbox }
  }))
  if (row.classNames?.length) {
    classNames.value = row.classNames
    if (!classNames.value.includes(drawLabel.value)) drawLabel.value = classNames.value[0]
  }
  selectedId.value = boxes.value[0]?.id || 0
  if (selected.value) drawLabel.value = selected.value.label
  tool.value = boxes.value.length ? 'select' : 'draw'
  showBoxes.value = true
  zoomMode.value = 'fit'
  await loadImage(row.id)
}

async function openSample(id: number) {
  loading.value = true
  try {
    const row: any = await configApi.getFlywheelSample(id)
    await applySample(row)
  } finally {
    loading.value = false
  }
}

async function goNext(afterId?: number) {
  const aid = typeof afterId === 'number' ? afterId : (sample.value?.id ?? 0)
  const had = !!sample.value
  loading.value = true
  try {
    const res: any = await configApi.getFlywheelSampleNext({ afterId: aid })
    if (!res?.sample) {
      sample.value = null
      boxes.value = []
      revokeImage()
      if (had) ElMessage.info('没有更多待审样本')
      return
    }
    await applySample(res.sample)
  } finally {
    loading.value = false
    await Promise.all([loadStats(), loadQueue()])
  }
}

async function saveBoxes() {
  if (!sample.value) return
  busy.value = true
  try {
    await configApi.updateFlywheelSample(sample.value.id, { boxes: boxes.value })
    ElMessage.success('检测框已保存')
  } finally {
    busy.value = false
  }
}

async function approve() {
  if (!sample.value) return
  busy.value = true
  const id = sample.value.id
  try {
    await configApi.approveFlywheelSample(id, { boxes: boxes.value })
    ElMessage.success('已通过，写入 reviewed')
    await goNext(id)
  } finally {
    busy.value = false
  }
}

async function discard() {
  if (!sample.value) return
  busy.value = true
  const id = sample.value.id
  try {
    await configApi.discardFlywheelSample(id)
    ElMessage.success('已丢弃')
    await goNext(id)
  } finally {
    busy.value = false
  }
}

function onKey(ev: KeyboardEvent) {
  const tag = (ev.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (drag.mode) return
  const key = ev.key.toLowerCase()
  if (key === 'a') {
    ev.preventDefault()
    approve()
  } else if (key === 'x') {
    ev.preventDefault()
    discard()
  } else if (key === 'n') {
    ev.preventDefault()
    goNext()
  } else if (key === 's') {
    ev.preventDefault()
    saveBoxes()
  } else if (key === 'h') {
    ev.preventDefault()
    toggleBoxes()
  } else if (key === 'd') {
    ev.preventDefault()
    tool.value = 'draw'
  } else if (key === 'v') {
    ev.preventDefault()
    tool.value = 'select'
  } else if (key === 'delete' || key === 'backspace') {
    ev.preventDefault()
    removeSelected()
  } else if (key === 'escape') {
    selectedId.value = 0
    draw()
  }
}

function goDetection() {
  router.push('/config/detection')
}

async function refreshTrain() {
  try {
    const tr: any = await configApi.getFlywheelTrain()
    trainBusy.value = !!tr?.busy
    trainMsg.value = tr?.run?.message || ''
    if (trainBusy.value) {
      if (trainTimer == null) {
        trainTimer = window.setInterval(refreshTrain, 4000)
      }
    } else if (trainTimer != null) {
      clearInterval(trainTimer)
      trainTimer = null
    }
  } catch {
    /* ignore */
  }
}

async function startTrain() {
  try {
    const res: any = await configApi.startFlywheelTrain()
    trainBusy.value = true
    trainMsg.value = res?.message || '训练已开始'
    ElMessage.success(trainMsg.value)
    refreshTrain()
  } catch {
    /* 错误已处理 */
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  loading.value = true
  try {
    await Promise.all([loadStats(), loadQueue(), refreshTrain()])
    try {
      const det: any = await configApi.getDetection()
      const names = det?.categoryOptions || det?.categories || []
      if (Array.isArray(names) && names.length && !classNames.value.length) {
        classNames.value = [...names]
        if (!names.includes(drawLabel.value)) drawLabel.value = names[0]
      }
    } catch {
      /* ignore */
    }
    await goNext(0)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  observer?.disconnect()
  observer = null
  revokeImage()
  if (trainTimer != null) {
    clearInterval(trainTimer)
    trainTimer = null
  }
})
</script>

<style scoped>
.desk-page {
  padding: 4px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.card-title {
  font-weight: 600;
  font-size: 16px;
}
.card-sub {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
}
.header-stats {
  display: flex;
  gap: 8px;
}
.desk-body {
  min-height: 520px;
}
.stage-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.toolbar-hint {
  font-size: 12px;
  color: #6b7280;
}
.stage-wrap {
  min-height: 480px;
  max-height: calc(100vh - 220px);
  background: #0b1220;
  border-radius: 8px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  overflow: auto;
}
.empty {
  padding: 48px 0;
  margin: auto;
}
.stage {
  position: relative;
  display: inline-block;
  line-height: 0;
  max-width: 100%;
}
.stage img {
  display: block;
  user-select: none;
  image-rendering: auto;
}
.overlay {
  position: absolute;
  left: 0;
  top: 0;
  cursor: grab;
}
.overlay.drawing {
  cursor: crosshair;
}
.meta {
  margin-bottom: 12px;
}
.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  margin-bottom: 6px;
  color: #6b7280;
}
.meta-row b {
  color: #111827;
  font-weight: 600;
}
.panel-title {
  margin: 14px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}
.box-list,
.queue {
  max-height: 180px;
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.box-item,
.queue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  border-bottom: 1px solid #f3f4f6;
}
.box-item.active,
.queue-item.current {
  background: #e6f4ff;
}
.swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.box-name {
  flex: 1;
}
.hint {
  padding: 10px;
  font-size: 12px;
  color: #9ca3af;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0 4px;
}
</style>
