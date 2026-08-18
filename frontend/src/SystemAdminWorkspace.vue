<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, Connection, DataBoard, Files, FolderOpened, Refresh, Search, Setting, UploadFilled, View } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import { deleteKnowledgeDocument, getKnowledgeContent, getKnowledgeFile, knowledgeAction, listKnowledgeDocuments, reviewKnowledgeDocument, searchKnowledge, uploadKnowledgeDocument, type KnowledgeDocument } from './api'

const props = defineProps<{ user: { display_name: string; role: string }; embedded?: boolean; initialView?: string }>()
defineEmits<{ logout: [] }>()

const view = ref('overview')
watch(() => props.initialView, (next) => { if (next) view.value = next }, { immediate: true })
const loading = ref(false)
const documents = ref<KnowledgeDocument[]>([])
const searchText = ref('')
const evidence = ref<any[]>([])
const uploadRef = ref<any>()
const reviewDialog = ref(false)
const selectedDocument = ref<KnowledgeDocument | null>(null)
const reviewForm = ref({ category: '', effective_from: '', effective_to: '' })
const nav = [{ id: 'overview', label: '系统概览', icon: DataBoard }, { id: 'knowledge', label: '知识库文档', icon: Files }, { id: 'retrieval', label: '检索验证', icon: Search }]
const publishedDocuments = computed(() => documents.value.filter(item => item.status === 'PUBLISHED').length)

async function loadData() { loading.value = true; try { documents.value = await listKnowledgeDocuments({ limit: 100, offset: 0 }) } catch { ElMessage.error('系统运维数据加载失败') } finally { loading.value = false } }
async function upload(request: { file: File }) { try { const document = await uploadKnowledgeDocument(request.file); documents.value = [document, ...documents.value]; ElMessage.success('文档已上传，正在进入解析队列') } catch (error: any) { ElMessage.error(error.response?.data?.message || '文档上传失败') } }
function openReview(item: KnowledgeDocument) { selectedDocument.value = item; reviewForm.value = { category: item.category || '', effective_from: '', effective_to: '' }; reviewDialog.value = true }
async function submitReview() { if (!selectedDocument.value) return; try { const updated = await reviewKnowledgeDocument(selectedDocument.value.id, { category: reviewForm.value.category || undefined, effective_from: reviewForm.value.effective_from || undefined, effective_to: reviewForm.value.effective_to || undefined }); updateDocument(updated); reviewDialog.value = false; ElMessage.success('审核信息已保存') } catch (error: any) { ElMessage.error(error.response?.data?.message || '审核保存失败') } }
async function documentAction(item: KnowledgeDocument, action: 'publish' | 'archive' | 'deactivate' | 'reparse') { try { updateDocument(await knowledgeAction(item.id, action)); ElMessage.success(action === 'publish' ? '文档已发布' : action === 'reparse' ? '已重新提交解析' : '文档状态已更新') } catch (error: any) { ElMessage.error(error.response?.data?.message || '操作失败，请检查文档当前状态') } }
function updateDocument(updated: KnowledgeDocument) { documents.value = documents.value.map(item => item.id === updated.id ? updated : item) }
async function deleteDocument(item: KnowledgeDocument) {
  try { await ElMessageBox.confirm(`确定删除「${item.filename}」？此操作会同时移除文档索引与对象存储中的原始文件，且不可恢复。`, '删除文档', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch { return }
  try { await deleteKnowledgeDocument(item.id); documents.value = documents.value.filter(d => d.id !== item.id); ElMessage.success('文档已删除') } catch (error: any) { ElMessage.error(error.response?.data?.message || '删除失败') }
}
async function runSearch() { if (!searchText.value.trim()) return; try { evidence.value = (await searchKnowledge(searchText.value.trim())).items } catch (error: any) { ElMessage.error(error.response?.data?.message || '知识检索失败') } }
function statusType(status: string) { return status === 'PUBLISHED' ? 'success' : status === 'PARSE_FAILED' ? 'danger' : status === 'REVIEW_REQUIRED' ? 'warning' : 'info' }
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
function renderMarkdown(content: string): string { return markdown.render(content) }
const previewDialog = ref(false)
const previewDocument = ref<KnowledgeDocument | null>(null)
const previewTab = ref('markdown')
const previewHtml = ref('')
const previewPdfUrl = ref('')
const previewLoading = ref(false)
function hasParsedContent(item: KnowledgeDocument | null): boolean { return !!item && ['REVIEW_REQUIRED', 'PUBLISHED', 'ARCHIVED', 'DEACTIVATED'].includes(item.status) }
async function openPreview(item: KnowledgeDocument) {
  previewDocument.value = item
  previewHtml.value = ''
  previewPdfUrl.value = ''
  previewDialog.value = true
  if (hasParsedContent(item)) { previewTab.value = 'markdown'; await loadMarkdown(item.id) }
  else { previewTab.value = 'pdf'; await loadPdf(item.id) }
}
async function loadMarkdown(id: string) {
  previewLoading.value = true
  try { const data = await getKnowledgeContent(id); previewHtml.value = renderMarkdown(data.content || '（文档尚未解析出内容）') }
  catch { previewHtml.value = '<p>正文加载失败</p>' }
  finally { previewLoading.value = false }
}
async function loadPdf(id: string) {
  previewLoading.value = true
  try { const blob = await getKnowledgeFile(id); if (previewPdfUrl.value) URL.revokeObjectURL(previewPdfUrl.value); previewPdfUrl.value = URL.createObjectURL(blob) }
  catch { ElMessage.error('原始文件加载失败') }
  finally { previewLoading.value = false }
}
function switchPreviewTab(tab: string | number | boolean) {
  const next = String(tab)
  if (next !== 'markdown' && next !== 'pdf') return
  previewTab.value = next
  if (!previewDocument.value) return
  if (next === 'markdown' && !previewHtml.value) loadMarkdown(previewDocument.value.id)
  if (next === 'pdf' && !previewPdfUrl.value) loadPdf(previewDocument.value.id)
}
function closePreview() { previewDialog.value = false; if (previewPdfUrl.value) { URL.revokeObjectURL(previewPdfUrl.value); previewPdfUrl.value = '' } }
onBeforeUnmount(() => { if (previewPdfUrl.value) URL.revokeObjectURL(previewPdfUrl.value) })
onMounted(loadData)
</script>

<template>
  <div :class="props.embedded ? 'system-embedded' : 'app-shell system-shell'"><aside v-if="!props.embedded" class="sidebar"><div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div><div class="workspace-label">系统管理工作区</div><nav><button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id"><component :is="item.icon" /><span>{{ item.label }}</span></button></nav><div class="system-health"><small>服务运行状态</small><strong><i></i> 正常</strong><span>队列与对象存储可用</span></div><div class="sidebar-foot"><el-button text @click="$emit('logout')"><Setting /> 退出登录</el-button></div></aside>
    <main class="main"><header v-if="!props.embedded" class="topbar"><div><div class="crumb">系统运维 <span>/</span> {{ nav.find(item => item.id === view)?.label }}</div><h1>{{ nav.find(item => item.id === view)?.label }}</h1></div><div class="top-actions"><el-button circle :icon="Refresh" @click="loadData" /><el-avatar :size="34">{{ user.display_name.slice(0, 1) }}</el-avatar><span class="user-name">{{ user.display_name }}</span></div></header>
      <section v-loading="loading" class="content"><div class="page-block">
        <template v-if="view === 'overview'"><div class="system-hero"><div><p class="section-kicker">SYSTEM OPERATIONS</p><h2>稳定运行，持续可追溯</h2><p>监控异步事件、知识文档和检索链路的系统状态。</p></div><div class="system-emblem"><Connection /></div></div><div class="system-kpis"><div><small>本次管理文档</small><strong>{{ documents.length }}</strong><span>当前浏览器会话</span></div><div><small>已发布文档</small><strong>{{ publishedDocuments }}</strong><span>可参与 RAG 检索</span></div></div></template>
        <template v-else-if="view === 'knowledge'"><div class="section-head"><div><p class="section-kicker">KNOWLEDGE LIFECYCLE</p><h2>知识库文档</h2></div><el-upload ref="uploadRef" :show-file-list="false" accept="application/pdf,.pdf" :http-request="upload"><el-button type="primary"><UploadFilled /> 上传 PDF</el-button></el-upload></div><div class="knowledge-note"><FolderOpened /><span>上传后文档进入 MinerU 异步解析。此列表保留本次浏览器会话中上传或操作的文档。</span></div><el-table :data="documents" class="shipment-table" empty-text="上传第一份规则文档"><el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip /><el-table-column label="状态" width="140"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column><el-table-column label="分类" width="110"><template #default="{ row }">{{ row.category || '未分类' }}</template></el-table-column><el-table-column label="大小" width="110"><template #default="{ row }">{{ (row.size_bytes / 1024).toFixed(1) }} KB</template></el-table-column><el-table-column label="页数" width="90"><template #default="{ row }">{{ row.page_count ?? '解析中' }}</template></el-table-column><el-table-column prop="mineru_task_id" label="解析任务" min-width="170" show-overflow-tooltip><template #default="{ row }">{{ row.mineru_task_id || '等待提交' }}</template></el-table-column><el-table-column prop="error_message" label="错误信息" min-width="180" show-overflow-tooltip /><el-table-column label="操作" min-width="360"><template #default="{ row }"><div class="doc-actions"><el-button size="small" :icon="View" @click="openPreview(row)">预览</el-button><el-button size="small" @click="openReview(row)">审核信息</el-button><el-button v-if="row.status === 'REVIEW_REQUIRED'" type="primary" size="small" @click="documentAction(row, 'publish')">发布</el-button><el-button v-if="['PARSE_FAILED', 'ARCHIVED', 'DEACTIVATED'].includes(row.status)" size="small" @click="documentAction(row, 'reparse')">重新解析</el-button><el-button v-if="row.status === 'PUBLISHED'" type="warning" plain size="small" @click="documentAction(row, 'archive')">归档</el-button><el-button v-if="row.status === 'PUBLISHED'" type="danger" plain size="small" @click="documentAction(row, 'deactivate')">禁用</el-button><el-button type="danger" size="small" @click="deleteDocument(row)">删除</el-button></div></template></el-table-column></el-table></template>
        <template v-else><div class="section-head"><div><p class="section-kicker">RAG RETRIEVAL CHECK</p><h2>检索验证</h2></div></div><div class="retrieval-search"><el-input v-model="searchText" size="large" placeholder="输入规则问题，例如：哪些物品禁止寄递？" @keyup.enter="runSearch" /><el-button type="primary" size="large" @click="runSearch"><Search /> 检索</el-button></div><div class="evidence-list"><article v-for="item in evidence" :key="`${item.document_id}-${item.score}`"><div class="evidence-score">{{ (item.score * 100).toFixed(0) }}</div><div><div class="evidence-head"><strong>{{ item.title || item.filename }}</strong><el-tag size="small" effect="plain">{{ item.category || '未分类' }}</el-tag></div><p>{{ item.content }}</p><small>{{ item.filename }} · {{ item.page_start ? `第 ${item.page_start}-${item.page_end || item.page_start} 页` : '无页码' }}</small></div></article><el-empty v-if="!evidence.length" description="输入问题后验证知识检索结果" /></div></template>
      </div></section>
    </main>
    <el-dialog v-model="reviewDialog" title="审核文档信息" width="480px"><el-form label-position="top"><el-form-item label="知识分类"><el-input v-model="reviewForm.category" placeholder="例如：禁寄规则" /></el-form-item><el-form-item label="生效时间"><el-date-picker v-model="reviewForm.effective_from" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" /></el-form-item><el-form-item label="失效时间"><el-date-picker v-model="reviewForm.effective_to" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" /></el-form-item></el-form><template #footer><el-button @click="reviewDialog = false">取消</el-button><el-button type="primary" @click="submitReview">保存审核</el-button></template></el-dialog>
    <el-dialog v-model="previewDialog" :title="previewDocument?.filename || '文档预览'" width="min(1320px, 96vw)" top="2vh" @closed="closePreview"><div v-loading="previewLoading" class="knowledge-preview"><div v-if="hasParsedContent(previewDocument)" class="preview-toolbar"><el-segmented v-model="previewTab" :options="[{ label: '解析内容', value: 'markdown' }, { label: '原始 PDF', value: 'pdf' }]" @change="switchPreviewTab" /></div><div v-if="previewTab === 'markdown'" class="preview-markdown" v-html="previewHtml" /><iframe v-else class="preview-pdf" :src="previewPdfUrl" /></div></el-dialog>
  </div>
</template>
