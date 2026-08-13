<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Box, Check, Clock, Connection, DocumentChecked, Key, List, Refresh, Setting, Upload, Van } from '@element-plus/icons-vue'
import { acceptDropoff, arriveDestination, confirmOriginArrival, dispatchLinehaul, issuePickupCredential, listCourierTasks, listShipments, verifyStationPickup, type CourierTask, type Shipment } from './api'

const props = defineProps<{ user: { display_name: string; role: string; station_id?: string | null } }>()
const emit = defineEmits<{ logout: [] }>()

const view = ref('tasks')
const loading = ref(false)
const shipments = ref<Shipment[]>([])
const tasks = ref<CourierTask[]>([])
const totalShipments = ref(0)
const query = ref('')
const pickupCodeDialog = ref(false)
const pickupCodeInput = ref('')
const selectedShipment = ref<Shipment | null>(null)
const issuedCode = ref('')

const nav = [
  { id: 'tasks', label: '网点任务', icon: List },
  { id: 'shipments', label: '运单管理', icon: Box },
  { id: 'dropoff', label: '自寄验收', icon: Upload },
  { id: 'pickup', label: '自取核销', icon: Key },
]

const tasksInStation = computed(() => tasks.value.filter(t => t.status !== 'COMPLETED' && t.status !== 'CANCELLED'))
const shipmentsForStation = computed(() => shipments.value.filter(s => !query.value || s.shipment_no.includes(query.value) || s.id.includes(query.value)))

async function loadData() {
  loading.value = true
  try {
    const [shipmentResult, taskResult] = await Promise.all([
      listShipments({ limit: 50, offset: 0 }),
      listCourierTasks(),
    ])
    shipments.value = shipmentResult.items || []
    totalShipments.value = shipmentResult.total || 0
    tasks.value = taskResult
  } catch { ElMessage.error('网点数据加载失败，请确认后端服务已启动') } finally { loading.value = false }
}

async function handleAcceptDropoff(shipment: Shipment) {
  try {
    await acceptDropoff(shipment.id)
    ElMessage.success('已接收客户自寄包裹')
    await loadData()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '该运单暂不能接收自寄') }
}

async function handleConfirmOriginArrival(shipment: Shipment) {
  try {
    await confirmOriginArrival(shipment.id)
    ElMessage.success('已确认包裹入站')
    await loadData()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '该运单暂不能确认入站') }
}

async function handleDispatchLinehaul(shipment: Shipment) {
  try {
    await dispatchLinehaul(shipment.id)
    ElMessage.success('干线已发出')
    await loadData()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '该运单暂不能发出干线') }
}

async function handleArriveDestination(shipment: Shipment) {
  try {
    await arriveDestination(shipment.id)
    ElMessage.success('已确认目的地到达')
    await loadData()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '该运单暂不能确认到达') }
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
    issuedCode.value = result.code || '(演示环境，取件码: 123456)'
    ElMessage.success('自取码已生成')
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '无法生成自取码') }
}

function openVerifyPickup(shipment: Shipment) {
  selectedShipment.value = shipment
  pickupCodeInput.value = ''
  pickupCodeDialog.value = true
}

async function handleVerifyPickup() {
  if (!selectedShipment.value || !pickupCodeInput.value.trim()) return
  try {
    await verifyStationPickup(selectedShipment.value.id, pickupCodeInput.value.trim())
    pickupCodeDialog.value = false
    ElMessage.success('自取核销成功，包裹已签收')
    await loadData()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '取件码错误或已失效') }
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    PENDING_PAYMENT: '待支付', PENDING_PICKUP: '待揽收', PICKUP_ASSIGNED: '已分配揽收',
    WAITING_FOR_DROPOFF: '等待客户自寄', PICKED_UP: '已揽收', AT_ORIGIN_STATION: '已到始发网点',
    IN_LINEHAUL: '干线运输中', AT_DESTINATION_STATION: '已到目标网点',
    DELIVERY_ASSIGNED: '已分配派送', OUT_FOR_DELIVERY: '派送中',
    WAITING_FOR_RECIPIENT_PICKUP: '等待客户自取', DELIVERED: '已签收',
    CANCELLED: '已取消',
  }
  return map[status] || status
}

function statusTagType(status: string): string {
  if (status === 'DELIVERED') return 'success'
  if (status === 'CANCELLED') return 'danger'
  if (status === 'PENDING_PAYMENT') return 'warning'
  return 'primary'
}

function availableActions(shipment: Shipment): string[] {
  const actions: string[] = []
  const s = shipment.status
  if (s === 'WAITING_FOR_DROPOFF') actions.push('dropoff')
  if (s === 'PICKED_UP') actions.push('origin_arrival')
  if (s === 'AT_ORIGIN_STATION') actions.push('linehaul')
  if (s === 'IN_LINEHAUL') actions.push('destination_arrival')
  if (s === 'AT_DESTINATION_STATION') actions.push('issue_code', 'verify_pickup')
  if (s === 'WAITING_FOR_RECIPIENT_PICKUP') actions.push('verify_pickup')
  return actions
}

onMounted(loadData)
</script>

<template>
  <div class="app-shell station-shell">
    <aside class="sidebar">
      <div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div>
      <div class="workspace-label">网点操作工作区</div>
      <nav>
        <button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id">
          <component :is="item.icon" /><span>{{ item.label }}</span>
          <b v-if="item.id === 'tasks' && tasksInStation.length">{{ tasksInStation.length }}</b>
        </button>
      </nav>
      <div class="station-shift">
        <small>当前网点</small>
        <strong>{{ props.user.station_id ? '所属网点' : '网点工作台' }}</strong>
        <span><i></i> 任务已同步</span>
      </div>
      <div class="sidebar-foot"><el-button text @click="emit('logout')"><Setting /> 退出登录</el-button></div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <div class="crumb">网点中心 <span>/</span> {{ nav.find(item => item.id === view)?.label }}</div>
          <h1>{{ nav.find(item => item.id === view)?.label }}</h1>
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

          <!-- 网点任务 -->
          <template v-if="view === 'tasks'">
            <div class="station-hero">
              <div>
                <p class="section-kicker">STATION OPERATIONS</p>
                <h2>每一件包裹，精准交接</h2>
                <p>管理网点入站、出站、干线发出和到站确认。</p>
              </div>
              <div class="station-emblem"><DocumentChecked /></div>
            </div>
            <div class="stat-strip station-stats">
              <div><small>待处理运单</small><strong>{{ shipments.filter(s => !['DELIVERED', 'CANCELLED'].includes(s.status)).length }}</strong></div>
              <div><small>网点任务</small><strong>{{ tasksInStation.length }}</strong></div>
              <div><small>今日完成</small><strong>{{ tasks.filter(t => t.status === 'COMPLETED').length }}</strong></div>
            </div>
            <div class="section-head compact">
              <div><p class="section-kicker">ACTION QUEUE</p><h2>待处理运单</h2></div>
            </div>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter(s => !['DELIVERED', 'CANCELLED'].includes(s.status)).slice(0, 10)" :key="shipment.id">
                <div class="action-mark"><Box /></div>
                <div>
                  <div class="action-title">
                    <strong>{{ shipment.shipment_no }}</strong>
                    <el-tag :type="statusTagType(shipment.status)" size="small">{{ statusText(shipment.status) }}</el-tag>
                  </div>
                  <small>{{ shipment.id }}</small>
                </div>
                <div class="action-btns">
                  <el-button v-if="availableActions(shipment).includes('dropoff')" type="primary" size="small" @click="handleAcceptDropoff(shipment)">自寄验收</el-button>
                  <el-button v-if="availableActions(shipment).includes('origin_arrival')" type="primary" size="small" @click="handleConfirmOriginArrival(shipment)">确认入站</el-button>
                  <el-button v-if="availableActions(shipment).includes('linehaul')" type="primary" size="small" @click="handleDispatchLinehaul(shipment)">发出干线</el-button>
                  <el-button v-if="availableActions(shipment).includes('destination_arrival')" type="success" size="small" @click="handleArriveDestination(shipment)">确认到站</el-button>
                  <el-button v-if="availableActions(shipment).includes('issue_code')" size="small" @click="openIssueCredential(shipment)">生成自取码</el-button>
                  <el-button v-if="availableActions(shipment).includes('verify_pickup')" type="warning" size="small" @click="openVerifyPickup(shipment)">核销自取</el-button>
                </div>
              </article>
              <el-empty v-if="shipments.filter(s => !['DELIVERED', 'CANCELLED'].includes(s.status)).length === 0" description="当前没有待处理的运单" />
            </div>
          </template>

          <!-- 运单管理 -->
          <template v-else-if="view === 'shipments'">
            <div class="section-head">
              <div><p class="section-kicker">SHIPMENT MANAGEMENT</p><h2>运单管理</h2></div>
              <span class="mono-caption">{{ totalShipments }} 条记录</span>
            </div>
            <el-table :data="shipmentsForStation" class="shipment-table">
              <el-table-column prop="shipment_no" label="运单号" min-width="180">
                <template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template>
              </el-table-column>
              <el-table-column prop="status" label="当前状态">
                <template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ statusText(row.status) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="240">
                <template #default="{ row }">
                  <el-button v-if="availableActions(row).includes('dropoff')" type="primary" size="small" @click="handleAcceptDropoff(row)">自寄验收</el-button>
                  <el-button v-if="availableActions(row).includes('origin_arrival')" type="primary" size="small" @click="handleConfirmOriginArrival(row)">确认入站</el-button>
                  <el-button v-if="availableActions(row).includes('linehaul')" type="primary" size="small" @click="handleDispatchLinehaul(row)">发出干线</el-button>
                  <el-button v-if="availableActions(row).includes('destination_arrival')" type="success" size="small" @click="handleArriveDestination(row)">确认到站</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <!-- 自寄验收 -->
          <template v-else-if="view === 'dropoff'">
            <div class="section-head">
              <div><p class="section-kicker">DROPOFF ACCEPTANCE</p><h2>自寄验收</h2></div>
            </div>
            <p class="section-desc">客户到店自寄的包裹，网点人员确认接收后进入始发入站流程。</p>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter(s => s.status === 'WAITING_FOR_DROPOFF')" :key="shipment.id">
                <div class="action-mark"><Upload /></div>
                <div>
                  <div class="action-title"><strong>{{ shipment.shipment_no }}</strong><el-tag type="warning" size="small">等待自寄</el-tag></div>
                  <small>{{ shipment.id }}</small>
                </div>
                <el-button type="primary" @click="handleAcceptDropoff(shipment)">接收包裹</el-button>
              </article>
              <el-empty v-if="!shipments.filter(s => s.status === 'WAITING_FOR_DROPOFF').length" description="当前没有等待自寄的运单" />
            </div>
          </template>

          <!-- 自取核销 -->
          <template v-else>
            <div class="section-head">
              <div><p class="section-kicker">PICKUP VERIFICATION</p><h2>自取核销</h2></div>
            </div>
            <p class="section-desc">客户到网点自取时，核验收件人身份和取件码后完成签收。</p>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter(s => ['AT_DESTINATION_STATION', 'WAITING_FOR_RECIPIENT_PICKUP'].includes(s.status))" :key="shipment.id">
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
              <el-empty v-if="!shipments.filter(s => ['AT_DESTINATION_STATION', 'WAITING_FOR_RECIPIENT_PICKUP'].includes(s.status)).length" description="当前没有可自取的运单" />
            </div>
          </template>

        </div>
      </section>
    </main>

    <!-- 自取码弹窗 -->
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
  </div>
</template>