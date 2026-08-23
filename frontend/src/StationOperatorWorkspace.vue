<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Box, DocumentChecked, Key, List, Refresh, Setting, Upload } from '@element-plus/icons-vue'
import {
  acceptDropoff,
  arriveDestination,
  confirmOriginArrival,
  dispatchLinehaul,
  getShipment,
  issuePickupCredential,
  listCourierTasks,
  listStations,
  listShipments,
  verifyStationPickup,
  type StationLite,
  type CourierTask,
  type Shipment,
  type ShipmentDetail,
} from './api'
import {
  loadReadTaskMessageIds,
  saveReadTaskMessageIds,
  taskMessageReadStorageKey,
} from './taskMessageRead'

const props = defineProps<{ user: { display_name: string; role: string; station_id?: string | null } }>()
const emit = defineEmits<{ logout: [] }>()

const view = ref<'tasks' | 'shipments' | 'dropoff' | 'pickup' | 'messages'>('tasks')
const loading = ref(false)
const shipments = ref<Shipment[]>([])
const tasks = ref<CourierTask[]>([])
const totalShipments = ref(0)
const query = ref('')

const pickupCodeDialog = ref(false)
const pickupCodeInput = ref('')
const selectedShipment = ref<Shipment | null>(null)
const issuedCode = ref('')

const detailDialog = ref(false)
const detailLoading = ref(false)
const shipmentDetail = ref<ShipmentDetail | null>(null)
const stationDisplayName = ref('')
const taskMessageReadKey = taskMessageReadStorageKey(props.user.role, props.user.display_name, props.user.station_id)
const readTaskMessageIds = ref(loadReadTaskMessageIds(taskMessageReadKey))

const nav = [
  { id: 'tasks', label: '网点任务', icon: List },
  { id: 'shipments', label: '运单管理', icon: Box },
  { id: 'dropoff', label: '自寄验收', icon: Upload },
  { id: 'pickup', label: '自取核销', icon: Key },
  { id: 'messages', label: '任务消息', icon: Bell },
] as const

const tasksInStation = computed(() => tasks.value.filter((t) => t.status !== 'COMPLETED' && t.status !== 'CANCELLED'))
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
const shipmentsForStation = computed(() =>
  shipments.value.filter((s) => !query.value || s.shipment_no.includes(query.value) || s.id.includes(query.value)),
)

function markTaskMessageRead(taskId: string) {
  if (readTaskMessageIds.value.includes(taskId)) return
  readTaskMessageIds.value = [...readTaskMessageIds.value, taskId]
  saveReadTaskMessageIds(taskMessageReadKey, readTaskMessageIds.value)
}

function markAllTaskMessagesRead() {
  readTaskMessageIds.value = [...new Set([...readTaskMessageIds.value, ...taskMessages.value.map((message) => message.id)])]
  saveReadTaskMessageIds(taskMessageReadKey, readTaskMessageIds.value)
}

async function loadData() {
  loading.value = true
  try {
    const [shipmentResult, taskResult, stations] = await Promise.all([
      listShipments({ limit: 50, offset: 0 }),
      listCourierTasks(),
      listStations().catch(() => [] as StationLite[]),
    ])
    shipments.value = shipmentResult.items || []
    totalShipments.value = shipmentResult.total || 0
    tasks.value = taskResult
    stationDisplayName.value = stations.find((item) => item.id === props.user.station_id)?.name || ''
  } catch {
    ElMessage.error('网点数据加载失败')
  } finally {
    loading.value = false
  }
}

async function handleAcceptDropoff(shipment: Shipment) {
  try {
    await acceptDropoff(shipment.id)
    ElMessage.success('已接收客户自寄包裹')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '该运单暂不能接收自寄')
  }
}

async function handleConfirmOriginArrival(shipment: Shipment) {
  try {
    await confirmOriginArrival(shipment.id)
    ElMessage.success('已确认包裹入站')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '该运单暂不能确认入站')
  }
}

async function handleDispatchLinehaul(shipment: Shipment) {
  try {
    await dispatchLinehaul(shipment.id)
    ElMessage.success('干线已发出')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '该运单暂不能发出干线')
  }
}

async function handleArriveDestination(shipment: Shipment) {
  try {
    await arriveDestination(shipment.id)
    ElMessage.success('已确认到达目的网点')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '该运单暂不能确认到站')
  }
}

function openIssueCredential(shipment: Shipment) {
  selectedShipment.value = shipment
  issuedCode.value = ''
  pickupCodeDialog.value = true
}

async function handleIssueCredential() {
  if (!selectedShipment.value) return
  try {
    const result = await issuePickupCredential(selectedShipment.value.id)
    issuedCode.value = result.code || '(演示环境取件码: 123456)'
    ElMessage.success('自取码已生成')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '无法生成自取码')
  }
}

function openVerifyPickup(shipment: Shipment) {
  selectedShipment.value = shipment
  pickupCodeInput.value = ''
  issuedCode.value = ''
  pickupCodeDialog.value = true
}

async function handleVerifyPickup() {
  if (!selectedShipment.value || !pickupCodeInput.value.trim()) return
  try {
    await verifyStationPickup(selectedShipment.value.id, pickupCodeInput.value.trim())
    pickupCodeDialog.value = false
    ElMessage.success('自取核销成功，包裹已签收')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '取件码错误或已失效')
  }
}

async function openShipmentDetail(shipment: Shipment) {
  detailDialog.value = true
  detailLoading.value = true
  shipmentDetail.value = null
  try {
    shipmentDetail.value = await getShipment(shipment.id)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '运单详情加载失败')
    detailDialog.value = false
  } finally {
    detailLoading.value = false
  }
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    PENDING_PAYMENT: '待支付',
    PENDING_PICKUP: '待揽收',
    PICKUP_ASSIGNED: '已分配揽收',
    WAITING_FOR_DROPOFF: '等待客户自寄',
    PICKED_UP: '已揽收',
    AT_ORIGIN_STATION: '已到始发网点',
    IN_LINEHAUL: '干线运输中',
    AT_DESTINATION_STATION: '已到目的网点',
    DELIVERY_ASSIGNED: '已分配派送',
    OUT_FOR_DELIVERY: '派送中',
    WAITING_FOR_RECIPIENT_PICKUP: '等待客户自取',
    DELIVERED: '已签收',
    CANCELLED: '已取消',
  }
  return map[status] || status
}

function statusTagType(status: string): 'success' | 'danger' | 'warning' | 'primary' {
  if (status === 'DELIVERED') return 'success'
  if (status === 'CANCELLED') return 'danger'
  if (status === 'PENDING_PAYMENT') return 'warning'
  return 'primary'
}

function availableActions(shipment: Shipment): string[] {
  const actions: string[] = []
  const status = shipment.status
  if (status === 'WAITING_FOR_DROPOFF') actions.push('dropoff')
  if (status === 'PICKED_UP') actions.push('origin_arrival')
  if (status === 'AT_ORIGIN_STATION') actions.push('linehaul')
  if (status === 'IN_LINEHAUL') actions.push('destination_arrival')
  if (shipment.delivery_method === 'STATION_PICKUP' && status === 'AT_DESTINATION_STATION') actions.push('issue_code', 'verify_pickup')
  if (shipment.delivery_method === 'STATION_PICKUP' && status === 'WAITING_FOR_RECIPIENT_PICKUP') actions.push('verify_pickup')
  return actions
}

function formatMoney(amountCents?: number | null): string {
  return 'CNY ' + (((amountCents ?? 0) as number) / 100).toFixed(2)
}

function trackingText(message: string): string {
  return message.split('_').join(' ')
}

onMounted(loadData)
</script>

<template>
  <div class="app-shell station-shell">
    <aside class="sidebar">
      <div class="logo">
        <span>Y</span>
        <div>Yitu<small>物流工作台</small></div>
      </div>
      <div class="workspace-label">网点工作区</div>
      <nav>
        <button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id">
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="station-shift">
        <small>当前网点</small>
        <strong>{{ stationDisplayName || props.user.station_id || '未绑定网点' }}</strong>
        <span><i></i> 任务已同步</span>
      </div>
      <div class="sidebar-foot">
        <el-button text @click="emit('logout')"><Setting /> 退出登录</el-button>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <div class="crumb">网点中心 <span>/</span> {{ nav.find((item) => item.id === view)?.label }}</div>
          <h1>{{ nav.find((item) => item.id === view)?.label }}</h1>
        </div>
        <div class="top-actions">
          <el-input v-if="view === 'shipments'" v-model="query" placeholder="搜索运单号" clearable />
          <el-button circle :icon="Refresh" @click="loadData" />
          <el-avatar :size="34">{{ props.user.display_name.slice(0, 1) }}</el-avatar>
          <span class="user-name">{{ props.user.display_name }}</span>
        </div>
      </header>

      <section v-loading="loading" class="content">
        <div class="page-block">
          <template v-if="view === 'tasks'">
            <div class="station-hero">
              <div>
                <p class="section-kicker">STATION OPERATIONS</p>
                <h2>按节点完成交接</h2>
                <p>处理入站、干线发运、到站确认和自提核销。</p>
              </div>
              <div class="station-emblem"><DocumentChecked /></div>
            </div>

            <div class="stat-strip station-stats">
              <div><small>待处理运单</small><strong>{{ shipments.filter((s) => !['DELIVERED', 'CANCELLED'].includes(s.status)).length }}</strong></div>
              <div><small>网点任务</small><strong>{{ tasksInStation.length }}</strong></div>
              <div><small>今日完成</small><strong>{{ tasks.filter((t) => t.status === 'COMPLETED').length }}</strong></div>
            </div>

            <div class="section-head compact">
              <div><p class="section-kicker">ACTION QUEUE</p><h2>待处理运单</h2></div>
            </div>

            <div class="station-action-list">
              <article v-for="shipment in shipments.filter((s) => !['DELIVERED', 'CANCELLED'].includes(s.status)).slice(0, 10)" :key="shipment.id">
                <div class="action-mark"><Box /></div>
                <div>
                  <div class="action-title">
                    <strong>{{ shipment.shipment_no }}</strong>
                    <el-tag :type="statusTagType(shipment.status)" size="small">{{ statusText(shipment.status) }}</el-tag>
                  </div>
                  <small>{{ shipment.id }}</small>
                </div>
                <div class="action-btns">
                  <el-button size="small" @click="openShipmentDetail(shipment)">查看详情</el-button>
                  <el-button v-if="availableActions(shipment).includes('dropoff')" type="primary" size="small" @click="handleAcceptDropoff(shipment)">自寄验收</el-button>
                  <el-button v-if="availableActions(shipment).includes('origin_arrival')" type="primary" size="small" @click="handleConfirmOriginArrival(shipment)">确认入站</el-button>
                  <el-button v-if="availableActions(shipment).includes('linehaul')" type="primary" size="small" @click="handleDispatchLinehaul(shipment)">发出干线</el-button>
                  <el-button v-if="availableActions(shipment).includes('destination_arrival')" type="success" size="small" @click="handleArriveDestination(shipment)">确认到站</el-button>
                  <el-button v-if="availableActions(shipment).includes('issue_code')" size="small" @click="openIssueCredential(shipment)">生成自取码</el-button>
                  <el-button v-if="availableActions(shipment).includes('verify_pickup')" type="warning" size="small" @click="openVerifyPickup(shipment)">核销自取</el-button>
                </div>
              </article>
              <el-empty v-if="shipments.filter((s) => !['DELIVERED', 'CANCELLED'].includes(s.status)).length === 0" description="当前没有待处理运单" />
            </div>
          </template>

          <template v-else-if="view === 'shipments'">
            <div class="section-head">
              <div><p class="section-kicker">SHIPMENT MANAGEMENT</p><h2>运单管理</h2></div>
              <span class="mono-caption">{{ totalShipments }} 条记录</span>
            </div>

            <el-table :data="shipmentsForStation" class="shipment-table">
              <el-table-column prop="shipment_no" label="运单号" min-width="180">
                <template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template>
              </el-table-column>
              <el-table-column prop="status" label="状态">
                <template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ statusText(row.status) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="320">
                <template #default="{ row }">
                  <div class="table-actions">
                    <el-button size="small" @click="openShipmentDetail(row)">查看详情</el-button>
                    <el-button v-if="availableActions(row).includes('dropoff')" type="primary" size="small" @click="handleAcceptDropoff(row)">自寄验收</el-button>
                    <el-button v-if="availableActions(row).includes('origin_arrival')" type="primary" size="small" @click="handleConfirmOriginArrival(row)">确认入站</el-button>
                    <el-button v-if="availableActions(row).includes('linehaul')" type="primary" size="small" @click="handleDispatchLinehaul(row)">发出干线</el-button>
                    <el-button v-if="availableActions(row).includes('destination_arrival')" type="success" size="small" @click="handleArriveDestination(row)">确认到站</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template v-else-if="view === 'dropoff'">
            <div class="section-head">
              <div><p class="section-kicker">DROPOFF ACCEPTANCE</p><h2>自寄验收</h2></div>
            </div>
            <p class="section-desc">接收客户到店自寄包裹，并推进到始发网点流程。</p>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter((s) => s.status === 'WAITING_FOR_DROPOFF')" :key="shipment.id">
                <div class="action-mark"><Upload /></div>
                <div>
                  <div class="action-title"><strong>{{ shipment.shipment_no }}</strong><el-tag type="warning" size="small">等待自寄</el-tag></div>
                  <small>{{ shipment.id }}</small>
                </div>
                <el-button type="primary" @click="handleAcceptDropoff(shipment)">接收包裹</el-button>
              </article>
              <el-empty v-if="!shipments.filter((s) => s.status === 'WAITING_FOR_DROPOFF').length" description="当前没有等待自寄的运单" />
            </div>
          </template>

          <template v-else-if="view === 'pickup'">
            <div class="section-head">
              <div><p class="section-kicker">PICKUP VERIFICATION</p><h2>自取核销</h2></div>
            </div>
            <p class="section-desc">客户到网点自取时，核验身份与取件码后完成签收。</p>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter((s) => s.delivery_method === 'STATION_PICKUP' && ['AT_DESTINATION_STATION', 'WAITING_FOR_RECIPIENT_PICKUP'].includes(s.status))" :key="shipment.id">
                <div class="action-mark"><Key /></div>
                <div>
                  <div class="action-title">
                    <strong>{{ shipment.shipment_no }}</strong>
                    <el-tag :type="shipment.status === 'WAITING_FOR_RECIPIENT_PICKUP' ? 'warning' : 'primary'" size="small">{{ statusText(shipment.status) }}</el-tag>
                  </div>
                  <small>{{ shipment.id }}</small>
                </div>
                <div class="action-btns">
                  <el-button v-if="shipment.status === 'AT_DESTINATION_STATION'" size="small" @click="openIssueCredential(shipment)">生成自取码</el-button>
                  <el-button type="warning" @click="openVerifyPickup(shipment)">核销自取</el-button>
                </div>
              </article>
              <el-empty v-if="!shipments.filter((s) => s.delivery_method === 'STATION_PICKUP' && ['AT_DESTINATION_STATION', 'WAITING_FOR_RECIPIENT_PICKUP'].includes(s.status)).length" description="当前没有可自取的运单" />
            </div>
          </template>

          <template v-else>
            <div class="section-head">
              <div><p class="section-kicker">TASK MESSAGES</p><h2>任务消息</h2></div>
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
                      {{ item.status === 'AVAILABLE' ? '待接单' : item.status === 'ACCEPTED' ? '进行中' : item.status === 'COMPLETED' ? '已完成' : '已取消' }}
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
          </template>
        </div>
      </section>
    </main>

    <el-dialog v-model="pickupCodeDialog" :title="issuedCode ? '自取码已生成' : '自取操作'" width="450px">
      <template v-if="issuedCode">
        <div class="code-display">
          <p class="dialog-tip">请将取件码告知收件人，核销后自动失效。</p>
          <div class="code-value">{{ issuedCode }}</div>
        </div>
      </template>
      <template v-else>
        <p class="dialog-tip">请输入客户出示的 6 位取件码。</p>
        <el-form label-position="top">
          <el-form-item label="运单号">
            <span class="shipment-no">{{ selectedShipment?.shipment_no }}</span>
          </el-form-item>
          <el-form-item label="取件码">
            <el-input v-model="pickupCodeInput" placeholder="请输入 6 位取件码" maxlength="6" />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="pickupCodeDialog = false">关闭</el-button>
        <el-button v-if="!issuedCode" type="primary" @click="handleVerifyPickup">确认核销</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialog" title="运单详情" width="760px">
      <div v-loading="detailLoading">
        <template v-if="shipmentDetail">
          <div class="detail-head">
            <div>
              <div class="shipment-no">{{ shipmentDetail.shipment.shipment_no }}</div>
              <div class="detail-route">
                <span>{{ shipmentDetail.sender_address?.full_address || '暂无寄件地址' }}</span>
                <span>-></span>
                <span>{{ shipmentDetail.receiver_address?.full_address || '暂无收件地址' }}</span>
              </div>
            </div>
            <el-tag :type="statusTagType(shipmentDetail.shipment.status)" size="large">{{ statusText(shipmentDetail.shipment.status) }}</el-tag>
          </div>
          <div class="detail-grid">
            <el-card shadow="never">
              <template #header>寄收信息</template>
              <div class="detail-pair">
                <div><small>寄件人</small><strong>{{ shipmentDetail.sender_address?.recipient_name || '未提供' }}</strong><p>{{ shipmentDetail.sender_address?.full_address || '暂无' }}</p></div>
                <div><small>收件人</small><strong>{{ shipmentDetail.receiver_address?.recipient_name || '未提供' }}</strong><p>{{ shipmentDetail.receiver_address?.full_address || '暂无' }}</p></div>
              </div>
            </el-card>
            <el-card shadow="never">
              <template #header>包裹与费用</template>
              <div class="detail-pair">
                <div><small>包裹</small><strong>{{ shipmentDetail.package?.description || '暂无' }}</strong><p>{{ shipmentDetail.package?.category || '未分类' }}</p></div>
                <div><small>运费合计</small><strong>{{ formatMoney(shipmentDetail.quote?.total_cents) }}</strong><p>已支付：{{ formatMoney(shipmentDetail.paid_total_cents) }}</p></div>
              </div>
              <div v-if="shipmentDetail.quote?.fee_items?.length" class="fee-items">
                <span v-for="item in shipmentDetail.quote.fee_items" :key="item.code">{{ item.code }} {{ formatMoney(item.amount_cents) }}</span>
              </div>
            </el-card>
          </div>
          <el-card shadow="never" class="tracking-card">
            <template #header>运单轨迹</template>
            <div v-if="shipmentDetail.tracking.length" class="tracking-list">
              <div v-for="item in shipmentDetail.tracking" :key="item.id" class="tracking-item">
                <strong>{{ trackingText(item.message) }}</strong>
                <span>{{ new Date(item.occurred_at).toLocaleString('zh-CN') }}</span>
              </div>
            </div>
            <el-empty v-else description="暂无轨迹" />
          </el-card>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.detail-route {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.detail-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.detail-pair small,
.tracking-item span,
.fee-items {
  color: var(--el-text-color-secondary);
}

.detail-pair strong,
.tracking-item strong {
  display: block;
  margin: 6px 0;
}

.detail-pair p {
  margin: 0;
  line-height: 1.6;
}

.fee-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.tracking-card {
  margin-top: 12px;
}

.tracking-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tracking-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.tracking-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

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

.message-card-head,
.message-page-actions,
.message-actions,
.message-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.message-card-head {
  justify-content: space-between;
  margin-bottom: 8px;
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
</style>
