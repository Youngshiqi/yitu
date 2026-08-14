<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Box, DocumentChecked, Key, List, Refresh, Setting, Upload } from '@element-plus/icons-vue'
import {
  acceptDropoff,
  arriveDestination,
  confirmOriginArrival,
  dispatchLinehaul,
  getShipment,
  issuePickupCredential,
  listCourierTasks,
  listShipments,
  verifyStationPickup,
  type CourierTask,
  type Shipment,
  type ShipmentDetail,
} from './api'

const props = defineProps<{ user: { display_name: string; role: string; station_id?: string | null } }>()
const emit = defineEmits<{ logout: [] }>()

const view = ref<'tasks' | 'shipments' | 'dropoff' | 'pickup'>('tasks')
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

const nav = [
  { id: 'tasks', label: 'Station Tasks', icon: List },
  { id: 'shipments', label: 'Shipments', icon: Box },
  { id: 'dropoff', label: 'Dropoff', icon: Upload },
  { id: 'pickup', label: 'Pickup', icon: Key },
] as const

const tasksInStation = computed(() => tasks.value.filter((t) => t.status !== 'COMPLETED' && t.status !== 'CANCELLED'))
const shipmentsForStation = computed(() =>
  shipments.value.filter((s) => !query.value || s.shipment_no.includes(query.value) || s.id.includes(query.value)),
)

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
  } catch {
    ElMessage.error('Station data load failed')
  } finally {
    loading.value = false
  }
}

async function handleAcceptDropoff(shipment: Shipment) {
  try {
    await acceptDropoff(shipment.id)
    ElMessage.success('Dropoff accepted')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Dropoff cannot be accepted')
  }
}

async function handleConfirmOriginArrival(shipment: Shipment) {
  try {
    await confirmOriginArrival(shipment.id)
    ElMessage.success('Origin arrival confirmed')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Origin arrival cannot be confirmed')
  }
}

async function handleDispatchLinehaul(shipment: Shipment) {
  try {
    await dispatchLinehaul(shipment.id)
    ElMessage.success('Linehaul dispatched')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Linehaul cannot be dispatched')
  }
}

async function handleArriveDestination(shipment: Shipment) {
  try {
    await arriveDestination(shipment.id)
    ElMessage.success('Destination arrival confirmed')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Destination arrival cannot be confirmed')
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
    issuedCode.value = result.code || '(demo code: 123456)'
    ElMessage.success('Pickup code created')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Pickup code creation failed')
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
    ElMessage.success('Pickup verified')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Pickup code invalid')
  }
}

async function openShipmentDetail(shipment: Shipment) {
  detailDialog.value = true
  detailLoading.value = true
  shipmentDetail.value = null
  try {
    shipmentDetail.value = await getShipment(shipment.id)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Shipment detail load failed')
    detailDialog.value = false
  } finally {
    detailLoading.value = false
  }
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    PENDING_PAYMENT: 'Pending payment',
    PENDING_PICKUP: 'Pending pickup',
    PICKUP_ASSIGNED: 'Pickup assigned',
    WAITING_FOR_DROPOFF: 'Waiting for dropoff',
    PICKED_UP: 'Picked up',
    AT_ORIGIN_STATION: 'At origin station',
    IN_LINEHAUL: 'In linehaul',
    AT_DESTINATION_STATION: 'At destination station',
    DELIVERY_ASSIGNED: 'Delivery assigned',
    OUT_FOR_DELIVERY: 'Out for delivery',
    WAITING_FOR_RECIPIENT_PICKUP: 'Waiting for recipient pickup',
    DELIVERED: 'Delivered',
    CANCELLED: 'Cancelled',
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
  if (status === 'AT_DESTINATION_STATION') actions.push('issue_code', 'verify_pickup')
  if (status === 'WAITING_FOR_RECIPIENT_PICKUP') actions.push('verify_pickup')
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
        <div>Yitu<small>station workspace</small></div>
      </div>
      <div class="workspace-label">Station workspace</div>
      <nav>
        <button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id">
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
          <b v-if="item.id === 'tasks' && tasksInStation.length">{{ tasksInStation.length }}</b>
        </button>
      </nav>
      <div class="station-shift">
        <small>Current station</small>
        <strong>{{ props.user.station_id || 'unbound' }}</strong>
        <span><i></i> synced</span>
      </div>
      <div class="sidebar-foot">
        <el-button text @click="emit('logout')"><Setting /> Logout</el-button>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <div class="crumb">Station center <span>/</span> {{ nav.find((item) => item.id === view)?.label }}</div>
          <h1>{{ nav.find((item) => item.id === view)?.label }}</h1>
        </div>
        <div class="top-actions">
          <el-input v-if="view === 'shipments'" v-model="query" placeholder="Search shipment no" clearable />
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
                <h2>Process shipment handoffs</h2>
                <p>Review incoming work and move shipments through station steps.</p>
              </div>
              <div class="station-emblem"><DocumentChecked /></div>
            </div>

            <div class="stat-strip station-stats">
              <div><small>Open shipments</small><strong>{{ shipments.filter((s) => !['DELIVERED', 'CANCELLED'].includes(s.status)).length }}</strong></div>
              <div><small>Tasks</small><strong>{{ tasksInStation.length }}</strong></div>
              <div><small>Done today</small><strong>{{ tasks.filter((t) => t.status === 'COMPLETED').length }}</strong></div>
            </div>

            <div class="section-head compact">
              <div><p class="section-kicker">ACTION QUEUE</p><h2>Pending shipments</h2></div>
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
                  <el-button size="small" @click="openShipmentDetail(shipment)">Detail</el-button>
                  <el-button v-if="availableActions(shipment).includes('dropoff')" type="primary" size="small" @click="handleAcceptDropoff(shipment)">Accept dropoff</el-button>
                  <el-button v-if="availableActions(shipment).includes('origin_arrival')" type="primary" size="small" @click="handleConfirmOriginArrival(shipment)">Origin arrival</el-button>
                  <el-button v-if="availableActions(shipment).includes('linehaul')" type="primary" size="small" @click="handleDispatchLinehaul(shipment)">Dispatch linehaul</el-button>
                  <el-button v-if="availableActions(shipment).includes('destination_arrival')" type="success" size="small" @click="handleArriveDestination(shipment)">Destination arrival</el-button>
                  <el-button v-if="availableActions(shipment).includes('issue_code')" size="small" @click="openIssueCredential(shipment)">Create pickup code</el-button>
                  <el-button v-if="availableActions(shipment).includes('verify_pickup')" type="warning" size="small" @click="openVerifyPickup(shipment)">Verify pickup</el-button>
                </div>
              </article>
              <el-empty v-if="shipments.filter((s) => !['DELIVERED', 'CANCELLED'].includes(s.status)).length === 0" description="No pending shipments" />
            </div>
          </template>

          <template v-else-if="view === 'shipments'">
            <div class="section-head">
              <div><p class="section-kicker">SHIPMENT MANAGEMENT</p><h2>Shipments</h2></div>
              <span class="mono-caption">{{ totalShipments }} records</span>
            </div>

            <el-table :data="shipmentsForStation" class="shipment-table">
              <el-table-column prop="shipment_no" label="Shipment no" min-width="180">
                <template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template>
              </el-table-column>
              <el-table-column prop="status" label="Status">
                <template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ statusText(row.status) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="Actions" width="320">
                <template #default="{ row }">
                  <div class="table-actions">
                    <el-button size="small" @click="openShipmentDetail(row)">Detail</el-button>
                    <el-button v-if="availableActions(row).includes('dropoff')" type="primary" size="small" @click="handleAcceptDropoff(row)">Accept dropoff</el-button>
                    <el-button v-if="availableActions(row).includes('origin_arrival')" type="primary" size="small" @click="handleConfirmOriginArrival(row)">Origin arrival</el-button>
                    <el-button v-if="availableActions(row).includes('linehaul')" type="primary" size="small" @click="handleDispatchLinehaul(row)">Dispatch linehaul</el-button>
                    <el-button v-if="availableActions(row).includes('destination_arrival')" type="success" size="small" @click="handleArriveDestination(row)">Destination arrival</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template v-else-if="view === 'dropoff'">
            <div class="section-head">
              <div><p class="section-kicker">DROPOFF ACCEPTANCE</p><h2>Dropoff</h2></div>
            </div>
            <p class="section-desc">Accept customer dropoff packages and move them into the station flow.</p>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter((s) => s.status === 'WAITING_FOR_DROPOFF')" :key="shipment.id">
                <div class="action-mark"><Upload /></div>
                <div>
                  <div class="action-title"><strong>{{ shipment.shipment_no }}</strong><el-tag type="warning" size="small">Waiting</el-tag></div>
                  <small>{{ shipment.id }}</small>
                </div>
                <el-button type="primary" @click="handleAcceptDropoff(shipment)">Accept package</el-button>
              </article>
              <el-empty v-if="!shipments.filter((s) => s.status === 'WAITING_FOR_DROPOFF').length" description="No dropoff shipments" />
            </div>
          </template>

          <template v-else>
            <div class="section-head">
              <div><p class="section-kicker">PICKUP VERIFICATION</p><h2>Pickup</h2></div>
            </div>
            <p class="section-desc">Verify recipient pickup with the one-time code.</p>
            <div class="station-action-list">
              <article v-for="shipment in shipments.filter((s) => ['AT_DESTINATION_STATION', 'WAITING_FOR_RECIPIENT_PICKUP'].includes(s.status))" :key="shipment.id">
                <div class="action-mark"><Key /></div>
                <div>
                  <div class="action-title">
                    <strong>{{ shipment.shipment_no }}</strong>
                    <el-tag :type="shipment.status === 'WAITING_FOR_RECIPIENT_PICKUP' ? 'warning' : 'primary'" size="small">{{ statusText(shipment.status) }}</el-tag>
                  </div>
                  <small>{{ shipment.id }}</small>
                </div>
                <div class="action-btns">
                  <el-button v-if="shipment.status === 'AT_DESTINATION_STATION'" size="small" @click="openIssueCredential(shipment)">Create code</el-button>
                  <el-button type="warning" @click="openVerifyPickup(shipment)">Verify pickup</el-button>
                </div>
              </article>
              <el-empty v-if="!shipments.filter((s) => ['AT_DESTINATION_STATION', 'WAITING_FOR_RECIPIENT_PICKUP'].includes(s.status)).length" description="No pickup shipments" />
            </div>
          </template>
        </div>
      </section>
    </main>

    <el-dialog v-model="pickupCodeDialog" :title="issuedCode ? 'Pickup code' : 'Pickup verify'" width="450px">
      <template v-if="issuedCode">
        <div class="code-display">
          <p class="dialog-tip">Share this code with the recipient.</p>
          <div class="code-value">{{ issuedCode }}</div>
        </div>
      </template>
      <template v-else>
        <p class="dialog-tip">Enter the 6-digit pickup code.</p>
        <el-form label-position="top">
          <el-form-item label="Shipment no">
            <span class="shipment-no">{{ selectedShipment?.shipment_no }}</span>
          </el-form-item>
          <el-form-item label="Pickup code">
            <el-input v-model="pickupCodeInput" placeholder="6-digit code" maxlength="6" />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="pickupCodeDialog = false">Close</el-button>
        <el-button v-if="!issuedCode" type="primary" @click="handleVerifyPickup">Confirm</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialog" title="Shipment detail" width="760px">
      <div v-loading="detailLoading">
        <template v-if="shipmentDetail">
          <div class="detail-head">
            <div>
              <div class="shipment-no">{{ shipmentDetail.shipment.shipment_no }}</div>
              <div class="detail-route">
                <span>{{ shipmentDetail.sender_address?.full_address || 'No sender address' }}</span>
                <span>-></span>
                <span>{{ shipmentDetail.receiver_address?.full_address || 'No receiver address' }}</span>
              </div>
            </div>
            <el-tag :type="statusTagType(shipmentDetail.shipment.status)" size="large">{{ statusText(shipmentDetail.shipment.status) }}</el-tag>
          </div>
          <div class="detail-grid">
            <el-card shadow="never">
              <template #header>Parties</template>
              <div class="detail-pair">
                <div><small>Sender</small><strong>{{ shipmentDetail.sender_address?.recipient_name || 'N/A' }}</strong><p>{{ shipmentDetail.sender_address?.full_address || 'N/A' }}</p></div>
                <div><small>Receiver</small><strong>{{ shipmentDetail.receiver_address?.recipient_name || 'N/A' }}</strong><p>{{ shipmentDetail.receiver_address?.full_address || 'N/A' }}</p></div>
              </div>
            </el-card>
            <el-card shadow="never">
              <template #header>Package and fee</template>
              <div class="detail-pair">
                <div><small>Package</small><strong>{{ shipmentDetail.package?.description || 'N/A' }}</strong><p>{{ shipmentDetail.package?.category || 'Unclassified' }}</p></div>
                <div><small>Total</small><strong>{{ formatMoney(shipmentDetail.quote?.total_cents) }}</strong><p>Paid: {{ formatMoney(shipmentDetail.paid_total_cents) }}</p></div>
              </div>
              <div v-if="shipmentDetail.quote?.fee_items?.length" class="fee-items">
                <span v-for="item in shipmentDetail.quote.fee_items" :key="item.code">{{ item.code }} {{ formatMoney(item.amount_cents) }}</span>
              </div>
            </el-card>
          </div>
          <el-card shadow="never" class="tracking-card">
            <template #header>Tracking</template>
            <div v-if="shipmentDetail.tracking.length" class="tracking-list">
              <div v-for="item in shipmentDetail.tracking" :key="item.id" class="tracking-item">
                <strong>{{ trackingText(item.message) }}</strong>
                <span>{{ new Date(item.occurred_at).toLocaleString('zh-CN') }}</span>
              </div>
            </div>
            <el-empty v-else description="No tracking yet" />
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
</style>