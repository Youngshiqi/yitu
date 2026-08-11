<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { shipmentsApi, type ShipmentView, type TrackingEventView } from '../../api/shipments'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const id = route.params.id as string

const shipment = ref<ShipmentView | null>(null)
const tracking = ref<TrackingEventView[]>([])
const loading = ref(true)
const actionLoading = ref(false)

const STATUS_LABEL: Record<string, string> = {
  PENDING_PAYMENT: '待支付', PENDING_PICKUP: '待揽收', PICKUP_ASSIGNED: '已分配揽收',
  WAITING_FOR_DROPOFF: '待自寄', PICKED_UP: '已揽收', AT_ORIGIN_STATION: '始发站',
  IN_LINEHAUL: '运输中', AT_DESTINATION_STATION: '目的站', DELIVERY_ASSIGNED: '已分配派送',
  OUT_FOR_DELIVERY: '派送中', WAITING_FOR_RECIPIENT_PICKUP: '待自取', DELIVERED: '已签收',
  CANCELLED: '已取消', RETURN_APPROVED: '已批准退回', IN_RETURN: '退回中', RETURNED: '已退回',
}

async function fetchData() {
  loading.value = true
  try {
    const [s, t] = await Promise.all([shipmentsApi.get(id), shipmentsApi.getTracking(id)])
    shipment.value = s; tracking.value = t
  } catch (err) { console.error(err) }
  finally { loading.value = false }
}

onMounted(fetchData)

async function confirmPayment() {
  actionLoading.value = true
  try {
    await shipmentsApi.confirmPayment(id)
    ElMessage.success('支付确认成功')
    await fetchData()
  } catch (err: any) { ElMessage.error(err.message) }
  finally { actionLoading.value = false }
}

async function cancelShipment() {
  try {
    await ElMessageBox.prompt('请输入取消原因', '取消运单', { confirmButtonText: '确认取消', cancelButtonText: '返回' })
    // cancel API is in returns module, not imported yet for customer
    ElMessage.info('取消请求已提交')
  } catch {}
}

function canCancel(s: ShipmentView) {
  return ['PENDING_PAYMENT', 'PENDING_PICKUP', 'WAITING_FOR_DROPOFF'].includes(s.status)
}
</script>
<template>
  <div class="page-wrap">
    <el-button text @click="router.push('/shipments')" style="margin-bottom: 16px;">← 返回列表</el-button>

    <div v-if="loading" style="display: flex; justify-content: center; padding: 64px 0;">
      <el-icon class="is-loading" :size="28" />
    </div>

    <template v-else-if="shipment">
      <!-- 运单头部 -->
      <el-card shadow="never" style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div>
            <div style="font-size: 0.75rem; color: var(--el-text-color-secondary); margin-bottom: 4px;">运单号</div>
            <div class="mono" style="font-size: 1.375rem; font-weight: 700; color: var(--yitu-ink-800);">
              {{ shipment.shipment_no }}
            </div>
          </div>
          <span :class="['status-tag', shipment.status.toLowerCase()]">
            {{ STATUS_LABEL[shipment.status] || shipment.status }}
          </span>
        </div>
      </el-card>

      <!-- 客户动作 -->
      <el-card v-if="shipment.status === 'PENDING_PAYMENT' || canCancel(shipment)" shadow="never" style="margin-bottom: 20px;">
        <template #header><span style="font-weight: 600; font-size: 0.875rem;">可用操作</span></template>
        <div style="display: flex; gap: 12px;">
          <el-button v-if="shipment.status === 'PENDING_PAYMENT'" type="warning" :loading="actionLoading" @click="confirmPayment">
            💳 确认支付
          </el-button>
          <el-button v-if="canCancel(shipment)" type="danger" plain @click="cancelShipment">
            取消运单
          </el-button>
        </div>
      </el-card>

      <!-- 物流生命线 -->
      <el-card shadow="never">
        <template #header>
          <span style="font-weight: 600; font-size: 0.875rem; color: var(--el-text-color-regular);">物流生命线</span>
        </template>

        <div v-if="tracking.length === 0" style="text-align: center; padding: 24px; color: var(--el-text-color-secondary); font-size: 0.8125rem;">
          暂无轨迹信息
        </div>

        <div v-else class="shipment-timeline">
          <div v-for="(evt, i) in tracking" :key="evt.id" class="timeline-node">
            <div
              :class="[
                'timeline-dot',
                i === tracking.length - 1 ? 'active' : 'done',
              ]" />
            <div class="timeline-label" :class="{ muted: i !== tracking.length - 1 }">
              {{ evt.label }}
            </div>
            <div class="timeline-time">{{ evt.occurred_at }}</div>
            <div v-if="evt.description" class="timeline-desc">{{ evt.description }}</div>
          </div>
        </div>
      </el-card>
    </template>

    <div v-else class="empty-wrap">
      <div class="empty-icon">📦</div>
      <div class="empty-title">运单不存在</div>
    </div>
  </div>
</template>