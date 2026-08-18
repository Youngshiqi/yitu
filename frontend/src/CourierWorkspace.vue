<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Box, Check, CircleCheck, Connection, Refresh, Setting, Van, View, Warning } from '@element-plus/icons-vue'
import {
  acceptCourierTask,
  confirmCourierDelivery,
  confirmPickupWithReweigh,
  getShipment,
  listCourierTasks,
  listStations,
  reportException,
  startCourierDelivery,
  type CourierTask,
  type ShipmentDetail,
} from './api'
import {
  loadReadTaskMessageIds,
  saveReadTaskMessageIds,
  taskMessageReadStorageKey,
} from './taskMessageRead'

const props = defineProps<{ user: { display_name: string; role: string; station_id?: string | null } }>()
defineEmits<{ logout: [] }>()

const tasks = ref<CourierTask[]>([])
const loading = ref(false)
const activeTab = ref<'active' | 'completed' | 'all'>('active')
const view = ref<'tasks' | 'messages'>('tasks')
const search = ref('')
const stationDisplayName = ref('')
const taskMessageReadKey = taskMessageReadStorageKey(props.user.role, props.user.display_name, props.user.station_id)
const readTaskMessageIds = ref(loadReadTaskMessageIds(taskMessageReadKey))

const signerDialog = ref(false)
const exceptionDialog = ref(false)
const reweighDialog = ref(false)

const selectedTask = ref<CourierTask | null>(null)
const signerName = ref('')
const exceptionForm = ref({ case_type: 'PICKUP_FAILED', description: '' })
const reweighForm = ref({
  actual_weight_grams: 1000,
  actual_length_cm: 30,
  actual_width_cm: 20,
  actual_height_cm: 20,
  remark: '',
})

const detailDialog = ref(false)
const detailLoading = ref(false)
const detail = ref<ShipmentDetail | null>(null)

const taskPage = ref(1)
const taskPageSize = 5

const filteredTasks = computed(() => tasks.value.filter((task) => {
  const tabMatch = activeTab.value === 'all'
    || (activeTab.value === 'completed'
      ? task.status === 'COMPLETED'
      : task.status !== 'COMPLETED' && task.status !== 'CANCELLED')
  return tabMatch && (!search.value || task.shipment_id.toLowerCase().includes(search.value.toLowerCase()))
}))

const availableCount = computed(() => tasks.value.filter((task) => task.status === 'AVAILABLE').length)
const acceptedCount = computed(() => tasks.value.filter((task) => task.status === 'ACCEPTED').length)
const completedCount = computed(() => tasks.value.filter((task) => task.status === 'COMPLETED').length)
const pagedTasks = computed(() => filteredTasks.value.slice((taskPage.value - 1) * taskPageSize, taskPage.value * taskPageSize))

const taskMessages = computed(() => tasks.value.map((task) => ({
  id: task.id,
  shipmentId: task.shipment_id,
  title: task.task_type === 'PICKUP' ? '揽收任务' : '派送任务',
  summary: task.status === 'AVAILABLE'
    ? '等待快递员接单。'
    : task.status === 'ACCEPTED'
      ? '任务进行中。'
      : task.status === 'COMPLETED'
        ? '任务已完成。'
        : '任务已取消。',
  status: task.status,
  read: readTaskMessageIds.value.includes(task.id),
})))
const unreadTaskMessageCount = computed(() => taskMessages.value.filter((message) => !message.read).length)

function markTaskMessageRead(taskId: string) {
  if (readTaskMessageIds.value.includes(taskId)) return
  readTaskMessageIds.value = [...readTaskMessageIds.value, taskId]
  saveReadTaskMessageIds(taskMessageReadKey, readTaskMessageIds.value)
}

function markAllTaskMessagesRead() {
  readTaskMessageIds.value = [...new Set([...readTaskMessageIds.value, ...taskMessages.value.map((message) => message.id)])]
  saveReadTaskMessageIds(taskMessageReadKey, readTaskMessageIds.value)
}

async function loadTasks() {
  loading.value = true
  try {
    const [taskResult, stations] = await Promise.all([
      listCourierTasks(),
      listStations().catch(() => []),
    ])
    tasks.value = taskResult
    stationDisplayName.value = stations.find((station) => station.id === props.user.station_id)?.name || ''
    taskPage.value = 1
  } catch {
    ElMessage.error('快递员任务加载失败')
  } finally {
    loading.value = false
  }
}

async function execute(task: CourierTask) {
  try {
    if (task.status === 'AVAILABLE') {
      await acceptCourierTask(task.id)
    } else if (task.task_type === 'PICKUP') {
      selectedTask.value = task
      reweighDialog.value = true
      return
    } else {
      await startCourierDelivery(task.shipment_id)
    }
    ElMessage.success(task.status === 'AVAILABLE' ? '已接单' : task.task_type === 'PICKUP' ? '已确认揽收' : '已开始派送')
    await loadTasks()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '任务状态已变化，请刷新后重试')
  }
}

async function submitReweigh() {
  if (!selectedTask.value) return
  try {
    await confirmPickupWithReweigh(selectedTask.value.id, reweighForm.value)
    reweighDialog.value = false
    ElMessage.success('揽收和复称信息已提交')
    await loadTasks()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '复称提交失败')
  }
}

async function openDetail(task: CourierTask) {
  selectedTask.value = task
  detail.value = null
  detailDialog.value = true
  detailLoading.value = true
  try {
    detail.value = await getShipment(task.shipment_id)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '运单详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function formatWeight(grams?: number | null): string {
  if (grams == null) return '—'
  return grams >= 1000 ? `${(grams / 1000).toFixed(2)} kg` : `${grams} g`
}

function packageDimensions(pkg: ShipmentDetail['package']): string {
  if (!pkg) return '—'
  const l = pkg.actual_length_cm ?? pkg.estimated_length_cm
  const w = pkg.actual_width_cm ?? pkg.estimated_width_cm
  const h = pkg.actual_height_cm ?? pkg.estimated_height_cm
  if (l == null && w == null && h == null) return '—'
  return `${l ?? '—'} × ${w ?? '—'} × ${h ?? '—'} cm`
}

function openSigner(task: CourierTask) {
  selectedTask.value = task
  signerName.value = ''
  signerDialog.value = true
}

async function submitSigner() {
  if (!selectedTask.value || !signerName.value.trim()) return
  try {
    await confirmCourierDelivery(selectedTask.value.shipment_id, signerName.value.trim())
    signerDialog.value = false
    ElMessage.success('签收已确认')
    await loadTasks()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '签收确认失败')
  }
}

function openException(task: CourierTask) {
  selectedTask.value = task
  exceptionForm.value = {
    case_type: task.task_type === 'PICKUP' ? 'PICKUP_FAILED' : 'RECIPIENT_UNREACHABLE',
    description: '',
  }
  exceptionDialog.value = true
}

async function submitException() {
  if (!selectedTask.value || !exceptionForm.value.description.trim()) return
  try {
    await reportException({
      shipment_id: selectedTask.value.shipment_id,
      case_type: exceptionForm.value.case_type,
      description: exceptionForm.value.description.trim(),
      evidence_summary: { task_id: selectedTask.value.id, source: 'COURIER_APP' },
    })
    exceptionDialog.value = false
    ElMessage.success('异常已提交')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '异常提交失败')
  }
}

function taskTitle(task: CourierTask) {
  return task.task_type === 'PICKUP' ? '上门揽收' : '末端派送'
}

function primaryText(task: CourierTask) {
  if (task.status === 'AVAILABLE') return '接单'
  return task.task_type === 'PICKUP' ? '确认揽收' : '开始派送'
}

function statusText(status: CourierTask['status']) {
  return {
    AVAILABLE: '待接单',
    ACCEPTED: '进行中',
    COMPLETED: '已完成',
    CANCELLED: '已取消',
  }[status]
}

onMounted(loadTasks)
</script>

<template>
  <div class="app-shell courier-shell">
    <aside class="sidebar">
      <div class="logo">
        <span>Y</span>
        <div>Yitu<small>快递员工作台</small></div>
      </div>
      <div class="workspace-label">快递员工作台</div>
      <nav>
        <button :class="{ active: view === 'tasks' }" @click="view = 'tasks'">
          <Van />
          <span>今日任务</span>
          <b v-if="acceptedCount">{{ acceptedCount }}</b>
        </button>
        <button :class="{ active: view === 'messages' }" @click="view = 'messages'">
          <Bell />
          <span>任务消息</span>
          <b v-if="unreadTaskMessageCount">{{ unreadTaskMessageCount }}</b>
        </button>
      </nav>
      <div class="courier-shift">
        <small>所属网点</small>
        <strong>{{ stationDisplayName || '未绑定网点' }}</strong>
        <span><i></i>任务已同步</span>
      </div>
      <div class="sidebar-foot">
          <el-button text @click="$emit('logout')"><Setting />退出登录</el-button>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <div class="crumb">快递员中心 <span>/</span> {{ view === 'tasks' ? '今日任务' : '任务消息' }}</div>
          <h1>{{ view === 'tasks' ? '今日任务' : '任务消息' }}</h1>
        </div>
        <div class="top-actions">
          <el-input v-model="search" placeholder="搜索运单号" clearable />
          <el-button circle :icon="Refresh" @click="loadTasks" />
          <el-avatar :size="34">{{ props.user.display_name.slice(0, 1) }}</el-avatar>
          <span class="user-name">{{ props.user.display_name }}</span>
        </div>
      </header>

      <section v-if="view === 'tasks'" v-loading="loading" class="content">
        <div class="page-block">
          <div class="courier-hero">
            <div>
              <p class="section-kicker">现场作业</p>
              <h2>按顺序完成每项任务</h2>
              <p>接收任务、确认揽收、开始派送并提交异常。</p>
            </div>
            <div class="route-emblem"><Van /></div>
          </div>

          <div class="stat-strip courier-stats">
            <div><small>待接单</small><strong>{{ availableCount }}</strong></div>
            <div><small>进行中</small><strong>{{ acceptedCount }}</strong></div>
            <div><small>已完成</small><strong>{{ completedCount }}</strong></div>
          </div>

          <div class="task-toolbar">
            <el-segmented
              v-model="activeTab"
              :options="[
                { label: '进行中', value: 'active' },
                { label: '已完成', value: 'completed' },
                { label: '全部', value: 'all' },
              ]"
              @change="taskPage = 1"
            />
            <span>{{ filteredTasks.length }} 项任务</span>
          </div>

          <div class="courier-task-list">
            <article v-for="task in pagedTasks" :key="task.id" class="courier-task">
              <div class="task-sequence" @click="openDetail(task)"><span>{{ task.task_type === 'PICKUP' ? 'P' : 'D' }}</span><i></i></div>
              <div class="task-copy" @click="openDetail(task)">
                <div class="task-heading">
                  <div>
                    <small>{{ task.task_type === 'PICKUP' ? '揽收任务' : '派送任务' }}</small>
                    <h3>{{ taskTitle(task) }}</h3>
                  </div>
                  <el-tag :type="task.status === 'COMPLETED' ? 'success' : task.status === 'AVAILABLE' ? 'warning' : 'primary'">
                    {{ statusText(task.status) }}
                  </el-tag>
                </div>
                <div class="task-meta">
                  <span><Box /> {{ task.shipment_id }}</span>
                  <span><Connection /> {{ task.assignee_id ? '已分配给当前快递员' : '网点共享任务' }}</span>
                </div>
              </div>
              <div class="task-actions">
                <el-button text type="primary" @click="openDetail(task)"><View />详情</el-button>
                <el-button v-if="task.status !== 'COMPLETED' && task.status !== 'CANCELLED'" type="primary" @click="execute(task)">
                  {{ primaryText(task) }}
                </el-button>
                  <el-button v-if="task.task_type === 'DELIVERY' && task.status === 'ACCEPTED'" @click="openSigner(task)">
                  <CircleCheck />确认签收
                </el-button>
                <el-button v-if="task.status !== 'COMPLETED'" text type="danger" @click="openException(task)">
                  <Warning />上报异常
                </el-button>
                <span v-else class="task-complete"><Check />已关闭</span>
              </div>
            </article>

            <el-empty v-if="!filteredTasks.length" description="暂无任务" />
          </div>

          <el-pagination
            v-if="filteredTasks.length > taskPageSize"
            v-model:current-page="taskPage"
            :page-size="taskPageSize"
            layout="prev, pager, next"
            :total="filteredTasks.length"
            class="list-pagination"
          />
        </div>
      </section>

    <el-dialog v-model="detailDialog" title="运单详情" width="560px" class="shipment-detail-dialog">
      <div v-loading="detailLoading" class="shipment-detail">
        <template v-if="detail">
          <div class="detail-head">
            <div>
              <small>{{ selectedTask?.task_type === 'PICKUP' ? '揽收任务' : '派送任务' }}</small>
              <h3 class="detail-no">{{ detail.shipment.shipment_no }}</h3>
            </div>
            <el-tag v-if="selectedTask" :type="selectedTask.status === 'COMPLETED' ? 'success' : selectedTask.status === 'AVAILABLE' ? 'warning' : 'primary'">
              {{ statusText(selectedTask.status) }}
            </el-tag>
          </div>

          <div class="detail-section">
            <h4>寄件信息（取件地址）</h4>
            <template v-if="detail.sender_address">
              <p class="detail-person">{{ detail.sender_address.recipient_name }} · {{ detail.sender_address.phone }}</p>
              <p class="detail-addr">{{ detail.sender_address.full_address }}</p>
            </template>
            <p v-else class="detail-empty">无寄件地址（网点寄件）</p>
          </div>

          <div class="detail-section">
            <h4>收件信息（派送地址）</h4>
            <template v-if="detail.receiver_address">
              <p class="detail-person">{{ detail.receiver_address.recipient_name }} · {{ detail.receiver_address.phone }}</p>
              <p class="detail-addr">{{ detail.receiver_address.full_address }}</p>
            </template>
            <p v-else class="detail-empty">无收件地址（网点自提）</p>
          </div>

          <div v-if="detail.package" class="detail-section">
            <h4>包裹信息</h4>
            <div class="detail-grid">
              <span>类别：{{ detail.package.category || '—' }}</span>
              <span>重量：{{ formatWeight(detail.package.actual_weight_grams ?? detail.package.estimated_weight_grams) }}</span>
              <span>尺寸：{{ packageDimensions(detail.package) }}</span>
            </div>
            <p v-if="detail.package.description" class="detail-note">描述：{{ detail.package.description }}</p>
            <p v-if="detail.package.special_instructions" class="detail-note">备注：{{ detail.package.special_instructions }}</p>
          </div>
        </template>
        <el-empty v-else-if="!detailLoading" description="暂无详情" />
      </div>
      <template #footer>
        <el-button @click="detailDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="signerDialog" title="确认签收" width="430px">
      <p class="dialog-tip">确认包裹已送达，然后填写签收人姓名。</p>
      <el-form label-position="top">
        <el-form-item label="签收人">
          <el-input v-model="signerName" placeholder="请输入签收人姓名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="signerDialog = false">取消</el-button>
        <el-button type="primary" @click="submitSigner">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="exceptionDialog" title="上报异常" width="480px">
      <el-form label-position="top">
        <el-form-item label="异常类型">
          <el-select v-model="exceptionForm.case_type">
            <el-option label="揽收失败" value="PICKUP_FAILED" />
            <el-option label="地址错误" value="ADDRESS_ERROR" />
            <el-option label="收件人无法联系" value="RECIPIENT_UNREACHABLE" />
            <el-option label="拒收" value="REFUSED" />
            <el-option label="破损" value="DAMAGE" />
          </el-select>
        </el-form-item>
        <el-form-item label="异常描述">
          <el-input v-model="exceptionForm.description" type="textarea" :rows="4" placeholder="请描述异常情况" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exceptionDialog = false">取消</el-button>
        <el-button type="danger" @click="submitException">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="reweighDialog" title="实际复称" width="480px">
      <el-form label-position="top">
        <el-form-item label="重量（克）">
          <el-input-number v-model="reweighForm.actual_weight_grams" :min="1" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="长度（厘米）"><el-input-number v-model="reweighForm.actual_length_cm" :min="1" /></el-form-item>
          <el-form-item label="宽度（厘米）"><el-input-number v-model="reweighForm.actual_width_cm" :min="1" /></el-form-item>
          <el-form-item label="高度（厘米）"><el-input-number v-model="reweighForm.actual_height_cm" :min="1" /></el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input v-model="reweighForm.remark" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reweighDialog = false">取消</el-button>
        <el-button type="primary" @click="submitReweigh">提交</el-button>
      </template>
    </el-dialog>

    <section v-if="view === 'messages'" class="content">
      <div class="page-block courier-messages-page">
        <div class="section-head">
          <div>
            <p class="section-kicker">TASK MESSAGES</p>
            <h2>任务消息</h2>
          </div>
          <div class="message-page-actions">
            <span class="mono-caption">{{ unreadTaskMessageCount }} 条未读</span>
            <el-button text type="primary" :disabled="!unreadTaskMessageCount" @click="markAllTaskMessagesRead">全部标为已读</el-button>
          </div>
        </div>
      <div class="message-list">
        <article v-for="item in taskMessages" :key="item.id" class="message-card" :class="{ unread: !item.read }">
          <div class="message-card-head">
            <div class="message-title"><i v-if="!item.read"></i><strong>{{ item.title }}</strong></div>
            <div class="message-actions">
              <el-tag :type="item.status === 'COMPLETED' ? 'success' : item.status === 'AVAILABLE' ? 'warning' : 'primary'">
                {{ statusText(item.status) }}
              </el-tag>
              <el-button v-if="!item.read" text type="primary" size="small" @click="markTaskMessageRead(item.id)">标为已读</el-button>
              <small v-else>已读</small>
            </div>
          </div>
          <p>{{ item.summary }}</p>
          <small>{{ item.shipmentId }}</small>
        </article>
        <el-empty v-if="!taskMessages.length" description="暂无任务消息" />
      </div>
      </div>
    </section>
    </main>
  </div>
</template>

<style scoped>
.message-list {
  display: grid;
  gap: 12px;
}

.message-card {
  border: 1px solid var(--el-border-color-lighter);
  padding: 14px 16px;
  background: #f7f9f8;
}

.message-card.unread {
  border-left: 3px solid var(--el-color-primary);
  background: #fff;
}

.message-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.message-page-actions,
.message-actions,
.message-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.message-title i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-primary);
}

.message-card p {
  margin: 0 0 8px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.message-card small {
  color: var(--el-text-color-placeholder);
}

.courier-task-list {
  display: grid;
  gap: 14px;
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.task-sequence,
.task-copy {
  cursor: pointer;
}

.task-copy:hover .task-heading h3 {
  color: var(--el-color-primary);
}

.shipment-detail {
  min-height: 120px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.detail-head small {
  color: var(--el-text-color-secondary);
}

.detail-no {
  margin: 2px 0 0;
  font-size: 18px;
}

.detail-section {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 0;
}

.detail-section h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.detail-person {
  margin: 0 0 4px;
  font-weight: 600;
}

.detail-addr {
  margin: 0;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.detail-empty {
  margin: 0;
  color: var(--el-text-color-placeholder);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px 16px;
}

.detail-note {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
