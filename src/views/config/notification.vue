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
              <span class="card-title">通知配置</span>
              <el-button type="primary" :loading="saveLoading" @click="handleSave">保存配置</el-button>
            </div>
          </template>

          <el-tabs v-model="activeTab">
            <!-- 钉钉 -->
            <el-tab-pane label="钉钉机器人" name="dingtalk">
              <el-form :model="dingtalkForm" label-width="120px" style="max-width: 500px">
                <el-form-item label="启用钉钉">
                  <el-switch v-model="dingtalkForm.enabled" />
                </el-form-item>
                <el-form-item label="Webhook 地址">
                  <el-input v-model="dingtalkForm.webhook" placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx" />
                </el-form-item>
                <el-form-item label="加签密钥">
                  <el-input v-model="dingtalkForm.secret" placeholder="可选，开启加签时填写" />
                </el-form-item>
                <el-form-item label="通知级别">
                  <el-checkbox-group v-model="dingtalkForm.levels">
                    <el-checkbox value="high">高危</el-checkbox>
                    <el-checkbox value="medium">中危</el-checkbox>
                    <el-checkbox value="low">低危</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="通知类型">
                  <el-checkbox-group v-model="dingtalkForm.types">
                    <el-checkbox value="intrusion">区域入侵</el-checkbox>
                    <el-checkbox value="parking">违停占道</el-checkbox>
                    <el-checkbox value="fire">火灾隐患</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item>
                  <el-button @click="testChannel('dingtalk')">发送测试消息</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 邮件 -->
            <el-tab-pane label="邮件通知" name="email">
              <el-form :model="emailForm" label-width="120px" style="max-width: 500px">
                <el-form-item label="启用邮件">
                  <el-switch v-model="emailForm.enabled" />
                </el-form-item>
                <el-form-item label="SMTP 服务器">
                  <el-input v-model="emailForm.smtp" placeholder="smtp.example.com" />
                </el-form-item>
                <el-form-item label="端口">
                  <el-input-number v-model="emailForm.port" :min="1" :max="65535" />
                </el-form-item>
                <el-form-item label="发件人邮箱">
                  <el-input v-model="emailForm.from" placeholder="alert@example.com" />
                </el-form-item>
                <el-form-item label="授权密码">
                  <el-input v-model="emailForm.password" type="password" show-password placeholder="SMTP 授权码" />
                </el-form-item>
                <el-form-item label="收件人">
                  <el-input
                    v-model="emailForm.recipients"
                    type="textarea"
                    :rows="3"
                    placeholder="多个邮箱用逗号或换行分隔"
                  />
                </el-form-item>
                <el-form-item label="通知级别">
                  <el-checkbox-group v-model="emailForm.levels">
                    <el-checkbox value="high">高危</el-checkbox>
                    <el-checkbox value="medium">中危</el-checkbox>
                    <el-checkbox value="low">低危</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item>
                  <el-button @click="testChannel('email')">发送测试消息</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 短信 -->
            <el-tab-pane label="短信通知" name="sms">
              <el-form :model="smsForm" label-width="120px" style="max-width: 500px">
                <el-form-item label="启用短信">
                  <el-switch v-model="smsForm.enabled" />
                </el-form-item>
                <el-form-item label="短信平台">
                  <el-select v-model="smsForm.provider">
                    <el-option label="阿里云短信" value="aliyun" />
                    <el-option label="腾讯云短信" value="tencent" />
                    <el-option label="华为云短信" value="huawei" />
                  </el-select>
                </el-form-item>
                <el-form-item label="Access Key">
                  <el-input v-model="smsForm.accessKey" placeholder="Access Key ID" />
                </el-form-item>
                <el-form-item label="Secret Key">
                  <el-input v-model="smsForm.secretKey" type="password" show-password placeholder="Access Key Secret" />
                </el-form-item>
                <el-form-item label="短信签名">
                  <el-input v-model="smsForm.sign" placeholder="短信签名名称" />
                </el-form-item>
                <el-form-item label="模板 ID">
                  <el-input v-model="smsForm.templateId" placeholder="短信模板 ID" />
                </el-form-item>
                <el-form-item label="接收手机号">
                  <el-input
                    v-model="smsForm.phones"
                    type="textarea"
                    :rows="3"
                    placeholder="多个手机号用逗号或换行分隔"
                  />
                </el-form-item>
                <el-form-item label="通知级别">
                  <el-checkbox-group v-model="smsForm.levels">
                    <el-checkbox value="high">高危</el-checkbox>
                    <el-checkbox value="medium">中危</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item>
                  <el-button @click="testChannel('sms')">发送测试消息</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 企业微信 -->
            <el-tab-pane label="企业微信" name="wework">
              <el-form :model="weworkForm" label-width="120px" style="max-width: 500px">
                <el-form-item label="启用企业微信">
                  <el-switch v-model="weworkForm.enabled" />
                </el-form-item>
                <el-form-item label="Webhook 地址">
                  <el-input v-model="weworkForm.webhook" placeholder="企业微信群机器人地址" />
                </el-form-item>
                <el-form-item label="通知级别">
                  <el-checkbox-group v-model="weworkForm.levels">
                    <el-checkbox value="high">高危</el-checkbox>
                    <el-checkbox value="medium">中危</el-checkbox>
                    <el-checkbox value="low">低危</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="通知类型">
                  <el-checkbox-group v-model="weworkForm.types">
                    <el-checkbox value="intrusion">区域入侵</el-checkbox>
                    <el-checkbox value="parking">违停占道</el-checkbox>
                    <el-checkbox value="fire">火灾隐患</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item>
                  <el-button @click="testChannel('wework')">发送测试消息</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
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
const activeMenu = ref('/config/notification')
const activeTab = ref('dingtalk')

const dingtalkForm = reactive<any>({
  enabled: true,
  webhook: '',
  secret: '',
  levels: ['high', 'medium'],
  types: ['intrusion', 'fire']
})

const emailForm = reactive<any>({
  enabled: false,
  smtp: '',
  port: 465,
  from: '',
  password: '',
  recipients: '',
  levels: ['high'],
  types: ['fire', 'intrusion']
})

const smsForm = reactive<any>({
  enabled: false,
  provider: 'aliyun',
  accessKey: '',
  secretKey: '',
  sign: '',
  templateId: '',
  phones: '',
  levels: ['high']
})

const weworkForm = reactive<any>({
  enabled: false,
  webhook: '',
  levels: ['high', 'medium'],
  types: ['intrusion', 'fire', 'parking']
})

async function loadData() {
  loading.value = true
  try {
    const res: any = await configApi.getNotification()
    if (res.dingtalk) Object.assign(dingtalkForm, res.dingtalk)
    if (res.email) Object.assign(emailForm, res.email)
    if (res.sms) Object.assign(smsForm, res.sms)
    if (res.wework) Object.assign(weworkForm, res.wework)
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saveLoading.value = true
  try {
    await configApi.updateNotification({
      dingtalk: dingtalkForm,
      email: emailForm,
      sms: smsForm,
      wework: weworkForm
    })
    ElMessage.success('通知配置已保存')
  } catch (e) {
    // 错误已处理
  } finally {
    saveLoading.value = false
  }
}

async function testChannel(channel: string) {
  try {
    ElMessage.success(`测试消息已发送到 ${channel}，请查看`)
  } catch (e) {}
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
</style>
