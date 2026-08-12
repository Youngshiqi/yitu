<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { shipmentsApi, type ShipmentView, type ShipmentStatus } from '../../api/shipments'

const router = useRouter()
const shipments = ref<ShipmentView[]>([])
const total = ref(0)
const loading = ref(true)
const statusFilter = ref<ShipmentStatus | ''>('')
const offset = ref(0)
const limit = 20

const FILTERS: { label: string; value: ShipmentStatus | '' }[] = [
  { label: '全部', value: '' },
  { label: '待支付', value: 'PENDING_PAYMENT' },
  { label: '待揽收', value: 'PENDING_PICKUP' },
  { label: '运输中', value: 'IN_LINEHAUL' },
  { label: '派送中', value: 'OUT_FOR_DELIVERY' },
  { label: '已签收', value: 'DELIVERED' },
  { label: '已取消', value: 'CANCELLED' },
]

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
    const data = await shipmentsApi.list({
      status: statusFilter.value || undefined,
      limit, offset: offset.value,
    })
    shipments.value = data.items
    total.value = data.total
  } catch (err) { console.error(err) }
  finally { loading.value = false }
}

function handleFilter(s: ShipmentStatus | '') {
  statusFilter.value = s; offset.value = 0; fetchData()
}

onMounted(() => fetchData())
</script>
<template>
  <div class="page-wrap">
    <div class="page-header">
      <h1 class="page-title">我的运单</h1>
      <el-button type="warning" @click="router.push('/shipments/new')">➕ 创建运单</el-button>
    </div>

    <div style="display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;">
      <el-button
        v-for="f in FILTERS" :key="f.value"
        :type="statusFilter === f.value ? 'primary' : 'default'"
        size="small" @click="handleFilter(f.value)">
        {{ f.label }}
      </el-button>
    </div>

    <div v-if="loading" style="display: flex; justify-content: center; padding: 64px 0;">
      <el-icon class="is-loading" :size="28" />
    </div>

    <div v-else-if="shipments.length === 0" class="empty-wrap">
      <div class="empty-icon">📦</div>
      <div class="empty-title">暂无运单</div>
      <div class="empty-desc">创建你的第一个运单开始寄件</div>
    </div>

    <el-table v-else :data="shipments" stripe style="width: 100%;" @row-click="(row: ShipmentView) => router.push(`/shipments/${row.id}`)">
      <el-table-column label="运单号" width="200">
        <template #default="{ row }">
          <span class="mono" style="font-weight: 600; color: var(--yitu-ink-800);">{{ row.shipment_no }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="160">
        <template #default="{ row }">
          <span :class="['status-tag', row.status.toLowerCase()]">{{ STATUS_LABEL[row.status] || row.status }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click.stop="router.push(`/shipments/${row.id}`)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > limit" style="display: flex; justify-content: center; margin-top: 20px;">
      <el-pagination
        :current-page="Math.floor(offset / limit) + 1"
        :page-size="limit" :total="total" layout="prev, pager, next"
        @current-change="(p: number) => { offset = (p - 1) * limit; fetchData(); }" />
    </div>
  </div>
</template>