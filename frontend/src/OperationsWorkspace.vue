<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Connection, DataAnalysis, Delete, Edit, OfficeBuilding, Plus, Refresh, Setting, TrendCharts, Warning } from '@element-plus/icons-vue'
import { applyExceptionAction, arriveDestination, createAdminStation, deleteAdminStation, listAdminStations, listCourierTasks, listExceptions, listRegions, listShipments, listSlaInstances, resolveException, setAdminStationEnabled, updateAdminStation, type AdminStation, type CourierTask, type ExceptionCase, type ServiceType, type Shipment } from './api'

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
const stations = ref<AdminStation[]>([])
const stationTotal = ref(0)
const stationPage = ref(1)
const stationQuery = ref('')
const stationDialog = ref(false)
const editingStationId = ref<string | null>(null)
type ServiceAreaForm = { region_path: string[]; service_types: ServiceType[] }
const emptyStationForm = () => ({ code: '', name: '', location_path: [] as string[], service_areas: [] as ServiceAreaForm[] })
const stationForm = ref(emptyStationForm())

const nav = [{ id: 'overview', label: '运营概览', icon: DataAnalysis }, { id: 'exceptions', label: '异常工单', icon: Warning }, { id: 'fulfillment', label: '履约调度', icon: Connection }, { id: 'stations', label: '网点管理', icon: OfficeBuilding }, { id: 'sla', label: 'SLA 监控', icon: TrendCharts }]
const serviceTypeOptions = [
  { label: '上门取件', value: 'HOME_PICKUP' },
  { label: '送货上门', value: 'HOME_DELIVERY' },
] as const
const enabledServiceTypes: ServiceType[] = serviceTypeOptions.map(item => item.value)
const regionCascaderProps = {
  lazy: true,
  emitPath: true,
  async lazyLoad(node: any, resolve: (nodes: any[]) => void) {
    try {
      const result = node.level === 0 ? await listRegions({ level: 'PROVINCE' }) : await listRegions({ parent_id: node.value })
      resolve(result.items.map(item => ({ value: item.id, label: item.name, leaf: item.level === 'DISTRICT' })))
    } catch { ElMessage.error('行政区划加载失败'); resolve([]) }
  },
}
const activeCases = computed(() => cases.value.filter(item => !['RESOLVED', 'CLOSED'].includes(item.status)))
const visibleCases = computed(() => (exceptionTab.value === 'all' ? cases.value : activeCases.value).filter(item => !query.value || item.shipment_id.includes(query.value) || item.description.includes(query.value)))
const tasksInTransit = computed(() => tasks.value.filter(task => task.status === 'ACCEPTED').length)

async function loadData() {
  loading.value = true
  try { const [shipmentResult, taskResult, caseResult] = await Promise.all([listShipments({ limit: 50, offset: 0 }), listCourierTasks(), listExceptions({ limit: 100, offset: 0 })]); shipments.value = shipmentResult.items || []; totalShipments.value = shipmentResult.total || 0; tasks.value = taskResult; cases.value = caseResult.items } catch { ElMessage.error('运营数据加载失败，请确认后端服务已启动') } finally { loading.value = false }
}
async function loadStations() {
  loading.value = true
  try { const result = await listAdminStations({ query: stationQuery.value || undefined, limit: 10, offset: (stationPage.value - 1) * 10 }); stations.value = result.items; stationTotal.value = result.total } catch (error: any) { ElMessage.error(error.response?.data?.message || '网点列表加载失败') } finally { loading.value = false }
}
function changeView(next: string) { view.value = next; if (next === 'stations') loadStations() }
function openCreateStation() { editingStationId.value = null; stationForm.value = emptyStationForm(); stationDialog.value = true }
function openEditStation(item: AdminStation) {
  editingStationId.value = item.id
  stationForm.value = {
    code: item.code,
    name: item.name,
    location_path: [item.province_region_id, item.city_region_id, item.district_region_id],
    service_areas: item.service_areas.map(area => ({ region_path: [area.province_region_id, area.city_region_id, area.district_region_id], service_types: area.service_types.filter(type => enabledServiceTypes.includes(type)) })),
  }
  stationDialog.value = true
}
function addServiceArea() { stationForm.value.service_areas.push({ region_path: [], service_types: [] }) }
function removeServiceArea(index: number) { stationForm.value.service_areas.splice(index, 1) }
async function saveStation() {
  const form = stationForm.value
  if (!form.code.trim() || !form.name.trim() || form.location_path.length !== 3) { ElMessage.warning('请完整填写网点编码、名称和所在地'); return }
  if (form.service_areas.some(area => area.region_path.length !== 3 || !area.service_types.length)) { ElMessage.warning('请完整配置每条服务区及服务类型'); return }
  const payload = { code: form.code.trim(), name: form.name.trim(), district_region_id: form.location_path[2], service_areas: form.service_areas.map(area => ({ district_region_id: area.region_path[2], service_types: area.service_types.filter(type => enabledServiceTypes.includes(type)) })) }
  try {
    if (editingStationId.value) await updateAdminStation(editingStationId.value, payload)
    else await createAdminStation(payload)
    stationDialog.value = false; ElMessage.success(editingStationId.value ? '网点已更新' : '网点已创建'); await loadStations()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '网点保存失败') }
}
async function toggleStation(item: AdminStation) {
  try { await setAdminStationEnabled(item.id, !item.enabled); ElMessage.success(item.enabled ? '网点已停用' : '网点已启用'); await loadStations() } catch (error: any) { ElMessage.error(error.response?.data?.message || '网点状态更新失败') }
}
async function removeStation(item: AdminStation) {
  try { await ElMessageBox.confirm(`确定删除网点“${item.name}”吗？已被业务引用的网点只能停用。`, '删除网点', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }); await deleteAdminStation(item.id); ElMessage.success('网点已删除'); await loadStations() } catch (error: any) { if (error === 'cancel' || error === 'close') return; ElMessage.error(error.response?.data?.message || '网点删除失败') }
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
  <div class="app-shell operations-shell"><aside class="sidebar"><div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div><div class="workspace-label">运营管理工作区</div><nav><button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="changeView(item.id)"><component :is="item.icon" /><span>{{ item.label }}</span><b v-if="item.id === 'exceptions' && activeCases.length">{{ activeCases.length }}</b></button></nav><div class="ops-status"><small>全网状态</small><strong>运行稳定</strong><span><i></i> 事件队列已同步</span></div><div class="sidebar-foot"><el-button text @click="$emit('logout')"><Setting /> 退出登录</el-button></div></aside>
    <main class="main"><header class="topbar"><div><div class="crumb">运营中心 <span>/</span> {{ nav.find(item => item.id === view)?.label }}</div><h1>{{ nav.find(item => item.id === view)?.label }}</h1></div><div class="top-actions"><el-input v-model="query" placeholder="搜索运单或异常说明" clearable /><el-button circle :icon="Refresh" @click="loadData" /><el-avatar :size="34">{{ user.display_name.slice(0, 1) }}</el-avatar><span class="user-name">{{ user.display_name }}</span></div></header>
      <section v-loading="loading" class="content"><div class="page-block">
        <template v-if="view === 'overview'"><div class="ops-hero"><div><p class="section-kicker">NETWORK CONTROL</p><h2>全网履约，一屏掌控</h2><p>聚合全局运单、执行任务与异常阻断信号。</p></div><div class="control-glyph"><DataAnalysis /></div></div><div class="ops-kpi-grid"><div><small>全网运单</small><strong>{{ totalShipments }}</strong><span>当前可见范围</span></div><div><small>执行中任务</small><strong>{{ tasksInTransit }}</strong><span>待揽收或派送</span></div><div><small>待处理异常</small><strong>{{ activeCases.length }}</strong><span>需要运营跟进</span></div><div><small>履约阻断</small><strong>{{ activeCases.filter(item => item.blocks_fulfillment).length }}</strong><span>受异常冻结</span></div></div><div class="section-head compact"><div><p class="section-kicker">ATTENTION QUEUE</p><h2>优先处理</h2></div><el-button text type="primary" @click="view = 'exceptions'">查看全部工单</el-button></div><div class="attention-list"><article v-for="item in activeCases.slice(0, 4)" :key="item.id"><div class="attention-mark"><Warning /></div><div><div class="attention-title"><strong>{{ item.case_type }}</strong><el-tag size="small" :type="severityType(item.severity)">{{ item.severity }}</el-tag></div><p>{{ item.description }}</p><small>{{ item.shipment_id }} · {{ new Date(item.opened_at).toLocaleString('zh-CN') }}</small></div><el-button @click="openAction(item, item.status === 'OPEN' || item.status === 'ASSIGNED' ? 'start-processing' : 'resolve')">处理</el-button></article><el-empty v-if="!activeCases.length" description="当前无待处理异常" /></div></template>
        <template v-else-if="view === 'exceptions'"><div class="section-head"><div><p class="section-kicker">EXCEPTION CONTROL</p><h2>异常工单</h2></div><el-segmented v-model="exceptionTab" :options="[{ label: '待处理', value: 'active' }, { label: '全部', value: 'all' }]" /></div><div class="exception-grid"><article v-for="item in visibleCases" :key="item.id" class="exception-card"><div class="exception-card-head"><span>{{ item.case_type }}</span><el-tag :type="severityType(item.severity)">{{ item.severity }}</el-tag></div><h3>{{ item.description }}</h3><p>{{ item.shipment_id }}</p><div class="case-footer"><div><small>状态</small><strong>{{ item.status }}</strong></div><div><small>履约</small><strong>{{ item.blocks_fulfillment ? '已阻断' : '未阻断' }}</strong></div></div><div class="case-actions"><el-button v-if="['OPEN', 'ASSIGNED'].includes(item.status)" type="primary" @click="openAction(item, 'start-processing')">开始处理</el-button><el-button v-if="item.status === 'PROCESSING'" @click="openAction(item, 'wait-for-customer')">等待客户</el-button><el-button v-if="item.status === 'WAITING_FOR_CUSTOMER'" @click="openAction(item, 'resume-processing')">恢复处理</el-button><el-button v-if="['PROCESSING', 'WAITING_FOR_CUSTOMER'].includes(item.status)" type="success" @click="openAction(item, 'resolve')">解决工单</el-button><el-button v-if="item.status === 'RESOLVED'" @click="openAction(item, 'close')">关闭工单</el-button></div></article><el-empty v-if="!visibleCases.length" description="没有匹配的异常工单" /></div></template>
        <template v-else-if="view === 'fulfillment'"><div class="section-head"><div><p class="section-kicker">FULFILLMENT CONTROL</p><h2>履约调度</h2></div></div><el-table :data="shipments.filter(item => !query || item.shipment_no.includes(query) || item.id.includes(query))" class="shipment-table"><el-table-column prop="shipment_no" label="运单号" min-width="180"><template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template></el-table-column><el-table-column prop="status" label="当前状态" /><el-table-column label="SLA" width="120"><template #default="{ row }"><el-button text @click="showSla(row)">查看 SLA</el-button></template></el-table-column><el-table-column label="运营动作" width="180"><template #default="{ row }"><el-button type="primary" plain size="small" @click="confirmArrival(row)">确认目的地到达</el-button></template></el-table-column></el-table></template>
        <template v-else-if="view === 'stations'"><div class="section-head"><div><p class="section-kicker">STATION NETWORK</p><h2>网点管理</h2></div><el-button type="primary" :icon="Plus" @click="openCreateStation">新增网点</el-button></div><div class="station-manage-toolbar"><el-input v-model="stationQuery" placeholder="搜索网点名称或编码" clearable @keyup.enter="stationPage = 1; loadStations()" /><el-button :icon="Refresh" @click="stationPage = 1; loadStations()">查询</el-button></div><el-table :data="stations" class="shipment-table"><el-table-column prop="code" label="网点编码" width="130"><template #default="{ row }"><span class="shipment-no">{{ row.code }}</span></template></el-table-column><el-table-column prop="name" label="网点名称" min-width="150" /><el-table-column label="所在地" min-width="180"><template #default="{ row }">{{ row.province_name }}{{ row.city_name === row.province_name ? '' : row.city_name }}{{ row.district_name }}</template></el-table-column><el-table-column label="服务区" width="90"><template #default="{ row }">{{ row.service_areas.length }}</template></el-table-column><el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column label="操作" width="270" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="Edit" @click="openEditStation(row)">编辑</el-button><el-button text :type="row.enabled ? 'warning' : 'success'" @click="toggleStation(row)">{{ row.enabled ? '停用' : '启用' }}</el-button><el-button text type="danger" :icon="Delete" @click="removeStation(row)">删除</el-button></template></el-table-column></el-table><el-pagination v-if="stationTotal > 10" v-model:current-page="stationPage" class="list-pagination" layout="prev, pager, next" :page-size="10" :total="stationTotal" @current-change="loadStations" /></template>
        <template v-else><div class="section-head"><div><p class="section-kicker">SLA WATCH</p><h2>SLA 监控</h2></div></div><div class="sla-empty"><Clock /><h3>按运单查看 SLA</h3><p>在履约调度中选择运单，即可查看承诺送达时间、预计到达时间和违约状态。</p><el-button type="primary" @click="changeView('fulfillment')">进入履约调度</el-button></div></template>
      </div></section>
    </main>
    <el-dialog v-model="actionDialog" :title="actionMode === 'resolve' ? '解决异常工单' : '更新工单状态'" width="470px"><el-form label-position="top"><el-form-item v-if="actionMode === 'resolve'" label="解决方式"><el-select v-model="resolutionCode"><el-option label="信息已更正" value="INFORMATION_CORRECTED" /><el-option label="无需后续动作" value="NO_FURTHER_ACTION" /></el-select></el-form-item><el-form-item label="处理说明"><el-input v-model="actionReason" type="textarea" :rows="4" :placeholder="actionMode === 'resolve' ? '说明解决措施' : '可选：补充本次处理原因'" /></el-form-item></el-form><template #footer><el-button @click="actionDialog = false">取消</el-button><el-button type="primary" @click="submitAction">确认操作</el-button></template></el-dialog>
    <el-dialog v-model="slaDialog" title="运单 SLA" width="620px"><el-table :data="slaRows"><el-table-column prop="stage" label="阶段" /><el-table-column prop="status" label="状态" /><el-table-column prop="promised_delivery_at" label="承诺时间" /><el-table-column prop="eta_at" label="预计时间" /><el-table-column prop="breached" label="已违约"><template #default="{ row }"><el-tag :type="row.breached ? 'danger' : 'success'">{{ row.breached ? '是' : '否' }}</el-tag></template></el-table-column></el-table><el-empty v-if="!slaRows.length" description="该运单没有 SLA 实例" /></el-dialog>
    <el-dialog v-model="stationDialog" :title="editingStationId ? '编辑网点' : '新增网点'" width="760px"><el-form label-position="top"><div class="station-base-grid"><el-form-item label="网点编码"><el-input v-model="stationForm.code" placeholder="例如：CSY-001" /></el-form-item><el-form-item label="网点名称"><el-input v-model="stationForm.name" placeholder="例如：长沙岳麓网点" /></el-form-item></div><el-form-item label="网点所在地"><el-cascader v-model="stationForm.location_path" :props="regionCascaderProps" placeholder="请选择省 / 市 / 区县" filterable clearable class="full-input" /></el-form-item><div class="service-area-head"><div><strong>服务区域</strong><small>配置该网点可以提供服务的区县及类型</small></div><el-button :icon="Plus" @click="addServiceArea">添加服务区</el-button></div><div class="service-area-editor"><div v-for="(area, index) in stationForm.service_areas" :key="index" class="service-area-row"><el-cascader v-model="area.region_path" :props="regionCascaderProps" placeholder="省 / 市 / 区县" filterable clearable /><el-select v-model="area.service_types" multiple collapse-tags collapse-tags-tooltip placeholder="选择服务类型"><el-option v-for="option in serviceTypeOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select><el-button circle text type="danger" :icon="Delete" @click="removeServiceArea(index)" /></div><el-empty v-if="!stationForm.service_areas.length" description="尚未配置服务区，可先创建后再补充" :image-size="52" /></div></el-form><template #footer><el-button @click="stationDialog = false">取消</el-button><el-button type="primary" @click="saveStation">{{ editingStationId ? '保存修改' : '创建网点' }}</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.station-manage-toolbar{display:flex;gap:10px;max-width:520px;margin-bottom:18px}.station-base-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.service-area-head{display:flex;justify-content:space-between;align-items:center;margin:18px 0 10px}.service-area-head small{display:block;color:#87928c;font-size:11px;margin-top:4px}.service-area-editor{display:grid;gap:9px;max-height:300px;overflow:auto}.service-area-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(260px,1.3fr) 34px;gap:9px;align-items:center;padding:10px;background:#eef2ed;border:1px solid #dce3de}.service-area-row .el-cascader,.service-area-row .el-select{width:100%}@media(max-width:700px){.station-base-grid,.service-area-row{grid-template-columns:1fr}.service-area-row .el-button{justify-self:end}}
</style>
