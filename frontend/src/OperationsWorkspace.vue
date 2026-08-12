<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Box, Check, Clock, Connection, DataAnalysis, DocumentChecked, Refresh, Setting, TrendCharts, Warning } from '@element-plus/icons-vue'
import { applyExceptionAction, arriveDestination, listCourierTasks, listExceptions, listShipments, listSlaInstances, resolveException, type CourierTask, type ExceptionCase, type Shipment } from './api'

defineProps<{ user: { display_name: string; role: string } }>()
defineEmits<{ logout: [] }>()

const view = ref('overview')
const loading = ref(false)
const shipments = ref<Shipment[]>([])
const tasks = ref<CourierTask[]>([])
const cases = ref<ExceptionCase[]>([])
const totalShipments = ref(0)
const query = ref('')
const exceptionTab = ref('active')
const selected = ref<ExceptionCase | null>(null)
const actionDialog = ref(false)
const actionMode = ref<'start-processing' | 'wait-for-customer' | 'resume-processing' | 'resolve' | 'close'>('start-processing')
const actionReason = ref('')
const resolutionCode = ref('INFORMATION_CORRECTED')
const slaDialog = ref(false)
const slaRows = ref<any[]>([])

const nav = [{ id: 'overview', label: '运营概览', icon: DataAnalysis }, { id: 'exceptions', label: '异常工单', icon: Warning }, { id: 'fulfillment', label: '履约调度', icon: Connection }, { id: 'sla', label: 'SLA 监控', icon: TrendCharts }]
const activeCases = computed(() => cases.value.filter(item => !['RESOLVED', 'CLOSED'].includes(item.status)))
const visibleCases = computed(() => (exceptionTab.value === 'all' ? cases.value : activeCases.value).filter(item => !query.value || item.shipment_id.includes(query.value) || item.description.includes(query.value)))
const tasksInTransit = computed(() => tasks.value.filter(task => task.status === 'ACCEPTED').length)

async function loadData() {
  loading.value = true
  try { const [shipmentResult, taskResult, caseResult] = await Promise.all([listShipments({ limit: 50, offset: 0 }), listCourierTasks(), listExceptions({ limit: 100, offset: 0 })]); shipments.value = shipmentResult.items || []; totalShipments.value = shipmentResult.total || 0; tasks.value = taskResult; cases.value = caseResult.items } catch { ElMessage.error('运营数据加载失败，请确认后端服务已启动') } finally { loading.value = false }
}
function openAction(item: ExceptionCase, mode: typeof actionMode.value) { selected.value = item; actionMode.value = mode; actionReason.value = ''; resolutionCode.value = 'INFORMATION_CORRECTED'; actionDialog.value = true }
async function submitAction() {
  if (!selected.value) return
  if (actionMode.value === 'resolve' && !actionReason.value.trim()) { ElMessage.warning('请填写解决说明'); return }
  try { if (actionMode.value === 'resolve') await resolveException(selected.value.id, resolutionCode.value, actionReason.value.trim()); else await applyExceptionAction(selected.value.id, actionMode.value, actionReason.value.trim()); actionDialog.value = false; ElMessage.success('工单状态已更新'); await loadData() } catch (error: any) { ElMessage.error(error.response?.data?.message || '工单状态无法推进') }
}
async function confirmArrival(shipment: Shipment) { try { await arriveDestination(shipment.id); ElMessage.success('已确认目的地到达'); await loadData() } catch (error: any) { ElMessage.error(error.response?.data?.message || '该运单暂不能确认到达') } }
async function showSla(shipment: Shipment) { try { slaRows.value = await listSlaInstances(shipment.id); slaDialog.value = true } catch { ElMessage.error('该运单暂无可查看的 SLA 实例') } }
function severityType(severity: string) { return severity === 'CRITICAL' || severity === 'HIGH' ? 'danger' : severity === 'MEDIUM' ? 'warning' : 'info' }
onMounted(loadData)
</script>

<template>
  <div class="app-shell operations-shell"><aside class="sidebar"><div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div><div class="workspace-label">运营管理工作区</div><nav><button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id"><component :is="item.icon" /><span>{{ item.label }}</span><b v-if="item.id === 'exceptions' && activeCases.length">{{ activeCases.length }}</b></button></nav><div class="ops-status"><small>全网状态</small><strong>运行稳定</strong><span><i></i> 事件队列已同步</span></div><div class="sidebar-foot"><el-button text @click="$emit('logout')"><Setting /> 退出登录</el-button></div></aside>
    <main class="main"><header class="topbar"><div><div class="crumb">运营中心 <span>/</span> {{ nav.find(item => item.id === view)?.label }}</div><h1>{{ nav.find(item => item.id === view)?.label }}</h1></div><div class="top-actions"><el-input v-model="query" placeholder="搜索运单或异常说明" clearable /><el-button circle :icon="Refresh" @click="loadData" /><el-avatar :size="34">{{ user.display_name.slice(0, 1) }}</el-avatar><span class="user-name">{{ user.display_name }}</span></div></header>
      <section v-loading="loading" class="content"><div class="page-block">
        <template v-if="view === 'overview'"><div class="ops-hero"><div><p class="section-kicker">NETWORK CONTROL</p><h2>全网履约，一屏掌控</h2><p>聚合全局运单、执行任务与异常阻断信号。</p></div><div class="control-glyph"><DataAnalysis /></div></div><div class="ops-kpi-grid"><div><small>全网运单</small><strong>{{ totalShipments }}</strong><span>当前可见范围</span></div><div><small>执行中任务</small><strong>{{ tasksInTransit }}</strong><span>待揽收或派送</span></div><div><small>待处理异常</small><strong>{{ activeCases.length }}</strong><span>需要运营跟进</span></div><div><small>履约阻断</small><strong>{{ activeCases.filter(item => item.blocks_fulfillment).length }}</strong><span>受异常冻结</span></div></div><div class="section-head compact"><div><p class="section-kicker">ATTENTION QUEUE</p><h2>优先处理</h2></div><el-button text type="primary" @click="view = 'exceptions'">查看全部工单</el-button></div><div class="attention-list"><article v-for="item in activeCases.slice(0, 4)" :key="item.id"><div class="attention-mark"><Warning /></div><div><div class="attention-title"><strong>{{ item.case_type }}</strong><el-tag size="small" :type="severityType(item.severity)">{{ item.severity }}</el-tag></div><p>{{ item.description }}</p><small>{{ item.shipment_id }} · {{ new Date(item.opened_at).toLocaleString('zh-CN') }}</small></div><el-button @click="openAction(item, item.status === 'OPEN' || item.status === 'ASSIGNED' ? 'start-processing' : 'resolve')">处理</el-button></article><el-empty v-if="!activeCases.length" description="当前无待处理异常" /></div></template>
        <template v-else-if="view === 'exceptions'"><div class="section-head"><div><p class="section-kicker">EXCEPTION CONTROL</p><h2>异常工单</h2></div><el-segmented v-model="exceptionTab" :options="[{ label: '待处理', value: 'active' }, { label: '全部', value: 'all' }]" /></div><div class="exception-grid"><article v-for="item in visibleCases" :key="item.id" class="exception-card"><div class="exception-card-head"><span>{{ item.case_type }}</span><el-tag :type="severityType(item.severity)">{{ item.severity }}</el-tag></div><h3>{{ item.description }}</h3><p>{{ item.shipment_id }}</p><div class="case-footer"><div><small>状态</small><strong>{{ item.status }}</strong></div><div><small>履约</small><strong>{{ item.blocks_fulfillment ? '已阻断' : '未阻断' }}</strong></div></div><div class="case-actions"><el-button v-if="['OPEN', 'ASSIGNED'].includes(item.status)" type="primary" @click="openAction(item, 'start-processing')">开始处理</el-button><el-button v-if="item.status === 'PROCESSING'" @click="openAction(item, 'wait-for-customer')">等待客户</el-button><el-button v-if="item.status === 'WAITING_FOR_CUSTOMER'" @click="openAction(item, 'resume-processing')">恢复处理</el-button><el-button v-if="['PROCESSING', 'WAITING_FOR_CUSTOMER'].includes(item.status)" type="success" @click="openAction(item, 'resolve')">解决工单</el-button><el-button v-if="item.status === 'RESOLVED'" @click="openAction(item, 'close')">关闭工单</el-button></div></article><el-empty v-if="!visibleCases.length" description="没有匹配的异常工单" /></div></template>
        <template v-else-if="view === 'fulfillment'"><div class="section-head"><div><p class="section-kicker">FULFILLMENT CONTROL</p><h2>履约调度</h2></div></div><el-table :data="shipments.filter(item => !query || item.shipment_no.includes(query) || item.id.includes(query))" class="shipment-table"><el-table-column prop="shipment_no" label="运单号" min-width="180"><template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template></el-table-column><el-table-column prop="status" label="当前状态" /><el-table-column label="SLA" width="120"><template #default="{ row }"><el-button text @click="showSla(row)">查看 SLA</el-button></template></el-table-column><el-table-column label="运营动作" width="180"><template #default="{ row }"><el-button type="primary" plain size="small" @click="confirmArrival(row)">确认目的地到达</el-button></template></el-table-column></el-table></template>
        <template v-else><div class="section-head"><div><p class="section-kicker">SLA WATCH</p><h2>SLA 监控</h2></div></div><div class="sla-empty"><Clock /><h3>按运单查看 SLA</h3><p>在履约调度中选择运单，即可查看承诺送达时间、预计到达时间和违约状态。</p><el-button type="primary" @click="view = 'fulfillment'">进入履约调度</el-button></div></template>
      </div></section>
    </main>
    <el-dialog v-model="actionDialog" :title="actionMode === 'resolve' ? '解决异常工单' : '更新工单状态'" width="470px"><el-form label-position="top"><el-form-item v-if="actionMode === 'resolve'" label="解决方式"><el-select v-model="resolutionCode"><el-option label="信息已更正" value="INFORMATION_CORRECTED" /><el-option label="无需后续动作" value="NO_FURTHER_ACTION" /></el-select></el-form-item><el-form-item label="处理说明"><el-input v-model="actionReason" type="textarea" :rows="4" :placeholder="actionMode === 'resolve' ? '说明解决措施' : '可选：补充本次处理原因'" /></el-form-item></el-form><template #footer><el-button @click="actionDialog = false">取消</el-button><el-button type="primary" @click="submitAction">确认操作</el-button></template></el-dialog>
    <el-dialog v-model="slaDialog" title="运单 SLA" width="620px"><el-table :data="slaRows"><el-table-column prop="stage" label="阶段" /><el-table-column prop="status" label="状态" /><el-table-column prop="promised_delivery_at" label="承诺时间" /><el-table-column prop="eta_at" label="预计时间" /><el-table-column prop="breached" label="已违约"><template #default="{ row }"><el-tag :type="row.breached ? 'danger' : 'success'">{{ row.breached ? '是' : '否' }}</el-tag></template></el-table-column></el-table><el-empty v-if="!slaRows.length" description="该运单没有 SLA 实例" /></el-dialog>
  </div>
</template>
