<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Box, Check, CircleCheck, Clock, Connection, Refresh, Setting, Van, Warning } from '@element-plus/icons-vue'
import { acceptCourierTask, confirmCourierDelivery, confirmCourierPickup, confirmPickupWithReweigh, listCourierTasks, reportException, startCourierDelivery, type CourierTask } from './api'

defineProps<{ user: { display_name: string; role: string; station_id?: string | null } }>()
defineEmits<{ logout: [] }>()

const tasks = ref<CourierTask[]>([])
const loading = ref(false)
const activeTab = ref('active')
const search = ref('')
const signerDialog = ref(false)
const exceptionDialog = ref(false)
const selectedTask = ref<CourierTask | null>(null)
const signerName = ref('')
const exceptionForm = ref({ case_type: 'PICKUP_FAILED', description: '' })
const reweighDialog = ref(false)
const reweighForm = ref({ actual_weight_grams: 1000, actual_length_cm: 30, actual_width_cm: 20, actual_height_cm: 20, remark: '' })
const taskPage = ref(1)
const taskPageSize = 5

const filteredTasks = computed(() => tasks.value.filter((task) => {
  const tabMatch = activeTab.value === 'all' || (activeTab.value === 'completed' ? task.status === 'COMPLETED' : task.status !== 'COMPLETED' && task.status !== 'CANCELLED')
  return tabMatch && (!search.value || task.shipment_id.toLowerCase().includes(search.value.toLowerCase()))
}))
const availableCount = computed(() => tasks.value.filter(task => task.status === 'AVAILABLE').length)
const acceptedCount = computed(() => tasks.value.filter(task => task.status === 'ACCEPTED').length)
const completedCount = computed(() => tasks.value.filter(task => task.status === 'COMPLETED').length)
const pagedTasks = computed(() => filteredTasks.value.slice((taskPage.value - 1) * taskPageSize, taskPage.value * taskPageSize))
const currentTasks = computed(() => pagedTasks.value)

async function loadTasks() {
  loading.value = true
  try { tasks.value = await listCourierTasks(); taskPage.value = 1 } catch { ElMessage.error('任务加载失败，请确认快递员所属网点') } finally { loading.value = false }
}
async function execute(task: CourierTask) {
  try {
    if (task.status === 'AVAILABLE') await acceptCourierTask(task.id)
    else if (task.task_type === 'PICKUP') { selectedTask.value = task; reweighDialog.value = true; return }
    else await startCourierDelivery(task.shipment_id)
    ElMessage.success(task.status === 'AVAILABLE' ? '接单成功' : task.task_type === 'PICKUP' ? '取件已确认' : '已开始派送')
    await loadTasks()
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '任务状态已变化，请刷新后重试') }
}
async function submitReweigh() {
  if (!selectedTask.value) return
  try { await confirmPickupWithReweigh(selectedTask.value.id, reweighForm.value); reweighDialog.value = false; ElMessage.success('复重并揽收已确认'); await loadTasks() } catch (error: any) { ElMessage.error(error.response?.data?.message || '复重提交失败') }
}
function openSigner(task: CourierTask) { selectedTask.value = task; signerName.value = ''; signerDialog.value = true }
async function submitSigner() {
  if (!selectedTask.value || !signerName.value.trim()) return
  try { await confirmCourierDelivery(selectedTask.value.shipment_id, signerName.value.trim()); signerDialog.value = false; ElMessage.success('签收已确认'); await loadTasks() } catch (error: any) { ElMessage.error(error.response?.data?.message || '签收确认失败') }
}
function openException(task: CourierTask) { selectedTask.value = task; exceptionForm.value = { case_type: task.task_type === 'PICKUP' ? 'PICKUP_FAILED' : 'RECIPIENT_UNREACHABLE', description: '' }; exceptionDialog.value = true }
async function submitException() {
  if (!selectedTask.value || !exceptionForm.value.description.trim()) return
  try { await reportException({ shipment_id: selectedTask.value.shipment_id, case_type: exceptionForm.value.case_type, description: exceptionForm.value.description.trim(), evidence_summary: { task_id: selectedTask.value.id, source: 'COURIER_APP' } }); exceptionDialog.value = false; ElMessage.success('异常已上报') } catch (error: any) { ElMessage.error(error.response?.data?.message || '异常上报失败') }
}
function taskTitle(task: CourierTask) { return task.task_type === 'PICKUP' ? '上门取件' : '末端派送' }
function primaryText(task: CourierTask) { if (task.status === 'AVAILABLE') return '接下任务'; return task.task_type === 'PICKUP' ? '确认取件' : '开始派送' }
onMounted(loadTasks)
</script>

<template>
  <div class="app-shell courier-shell">
    <aside class="sidebar"><div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div><div class="workspace-label">快递员工作区</div><nav><button class="active"><Van /><span>今日任务</span><b v-if="acceptedCount">{{ acceptedCount }}</b></button><button><Bell /><span>任务消息</span></button></nav><div class="courier-shift"><small>当前班次</small><strong>服务中</strong><span><i></i> 网点任务已同步</span></div><div class="sidebar-foot"><el-button text @click="$emit('logout')"><Setting /> 退出登录</el-button></div></aside>
    <main class="main"><header class="topbar"><div><div class="crumb">履约中心 <span>/</span> 今日任务</div><h1>今日任务</h1></div><div class="top-actions"><el-input v-model="search" placeholder="搜索运单 UUID" clearable /><el-button circle :icon="Refresh" @click="loadTasks" /><el-avatar :size="34">{{ user.display_name.slice(0, 1) }}</el-avatar><span class="user-name">{{ user.display_name }}</span></div></header>
      <section v-loading="loading" class="content"><div class="page-block">
        <div class="courier-hero"><div><p class="section-kicker">FIELD OPERATIONS</p><h2>稳妥交付每一票</h2><p>按任务顺序完成接单、取件、派送和签收。</p></div><div class="route-emblem"><Van /></div></div>
        <div class="stat-strip courier-stats"><div><small>等待接单</small><strong>{{ availableCount }}</strong></div><div><small>执行中</small><strong>{{ acceptedCount }}</strong></div><div><small>今日完成</small><strong>{{ completedCount }}</strong></div></div>
        <div class="task-toolbar"><el-segmented v-model="activeTab" :options="[{ label: '进行中', value: 'active' }, { label: '已完成', value: 'completed' }, { label: '全部', value: 'all' }]" @change="taskPage = 1" /><span>{{ filteredTasks.length }} 项任务</span></div>
        <div class="courier-task-list"><article v-for="task in pagedTasks" :key="task.id" class="courier-task"><div class="task-sequence"><span>{{ task.task_type === 'PICKUP' ? 'P' : 'D' }}</span><i></i></div><div class="task-copy"><div class="task-heading"><div><small>{{ task.task_type === 'PICKUP' ? 'PICKUP TASK' : 'DELIVERY TASK' }}</small><h3>{{ taskTitle(task) }}</h3></div><el-tag :type="task.status === 'COMPLETED' ? 'success' : task.status === 'AVAILABLE' ? 'warning' : 'primary'">{{ task.status === 'AVAILABLE' ? '待接单' : task.status === 'ACCEPTED' ? '执行中' : task.status === 'COMPLETED' ? '已完成' : '已取消' }}</el-tag></div><div class="task-meta"><span><Box /> {{ task.shipment_id }}</span><span><Connection /> {{ task.assignee_id ? '已分配给当前快递员' : '网点公共任务' }}</span></div></div><div class="task-actions"><el-button v-if="task.status !== 'COMPLETED' && task.status !== 'CANCELLED'" type="primary" @click="execute(task)">{{ primaryText(task) }}</el-button><el-button v-if="task.task_type === 'DELIVERY' && task.status === 'ACCEPTED'" @click="openSigner(task)"><CircleCheck /> 确认签收</el-button><el-button v-if="task.status !== 'COMPLETED'" text type="danger" @click="openException(task)"><Warning /> 上报异常</el-button><span v-else class="task-complete"><Check /> 已闭环</span></div></article><el-empty v-if="!filteredTasks.length" description="当前没有任务" /></div><el-pagination v-if="filteredTasks.length > taskPageSize" v-model:current-page="taskPage" :page-size="taskPageSize" layout="prev, pager, next" :total="filteredTasks.length" class="list-pagination" />
      </div></section>
    </main>
    <el-dialog v-model="signerDialog" title="确认签收" width="430px"><p class="dialog-tip">请确认包裹已经交给收件人，再填写签收人姓名。</p><el-form label-position="top"><el-form-item label="签收人"><el-input v-model="signerName" placeholder="请输入签收人姓名" /></el-form-item></el-form><template #footer><el-button @click="signerDialog = false">取消</el-button><el-button type="primary" @click="submitSigner">确认签收</el-button></template></el-dialog>
    <el-dialog v-model="exceptionDialog" title="上报履约异常" width="480px"><el-form label-position="top"><el-form-item label="异常类型"><el-select v-model="exceptionForm.case_type"><el-option label="取件失败" value="PICKUP_FAILED" /><el-option label="地址错误" value="ADDRESS_ERROR" /><el-option label="无法联系收件人" value="RECIPIENT_UNREACHABLE" /><el-option label="拒收" value="REFUSED" /><el-option label="包裹破损" value="DAMAGE" /></el-select></el-form-item><el-form-item label="现场说明"><el-input v-model="exceptionForm.description" type="textarea" :rows="4" placeholder="说明现场情况和已采取的措施" /></el-form-item></el-form><template #footer><el-button @click="exceptionDialog = false">取消</el-button><el-button type="danger" @click="submitException">提交异常</el-button></template></el-dialog>
    <el-dialog v-model="reweighDialog" title="填写实际复重" width="480px"><el-form label-position="top"><el-form-item label="实际重量（克）"><el-input-number v-model="reweighForm.actual_weight_grams" :min="1" /></el-form-item><div class="form-grid"><el-form-item label="长（厘米）"><el-input-number v-model="reweighForm.actual_length_cm" :min="1" /></el-form-item><el-form-item label="宽（厘米）"><el-input-number v-model="reweighForm.actual_width_cm" :min="1" /></el-form-item><el-form-item label="高（厘米）"><el-input-number v-model="reweighForm.actual_height_cm" :min="1" /></el-form-item></div><el-form-item label="现场备注"><el-input v-model="reweighForm.remark" type="textarea" /></el-form-item></el-form><template #footer><el-button @click="reweighDialog = false">取消</el-button><el-button type="primary" @click="submitReweigh">提交复重并完成揽收</el-button></template></el-dialog>
  </div>
</template>
