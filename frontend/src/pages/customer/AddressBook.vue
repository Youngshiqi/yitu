<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { addressesApi, type Address } from '../../api/addresses'
import { ElMessage, ElMessageBox } from 'element-plus'

const addresses = ref<Address[]>([])
const loading = ref(true)
const dialogVisible = ref(false)
const editing = ref<Address | null>(null)
const form = ref({ label: '', recipient_name: '', phone: '', district_code: '', detail: '' })

async function fetchData() {
  loading.value = true
  try { addresses.value = await addressesApi.list() } catch {}
  finally { loading.value = false }
}

onMounted(fetchData)

function openCreate() {
  editing.value = null
  form.value = { label: '', recipient_name: '', phone: '', district_code: '', detail: '' }
  dialogVisible.value = true
}

function openEdit(a: Address) {
  editing.value = a
  form.value = { label: a.label, recipient_name: a.recipient_name, phone: a.phone, district_code: a.district_code, detail: a.detail }
  dialogVisible.value = true
}

async function handleSave() {
  try {
    if (editing.value) {
      await addressesApi.update(editing.value.id, form.value)
      ElMessage.success('地址已更新')
    } else {
      await addressesApi.create(form.value)
      ElMessage.success('地址已添加')
    }
    dialogVisible.value = false
    await fetchData()
  } catch (err: any) { ElMessage.error(err.message) }
}

async function handleDelete(a: Address) {
  try {
    await ElMessageBox.confirm(`确定删除地址「${a.label}」？`, '删除确认', { type: 'warning' })
    await addressesApi.remove(a.id)
    ElMessage.success('地址已删除')
    await fetchData()
  } catch {}
}
</script>
<template>
  <div class="page-wrap">
    <div class="page-header">
      <h1 class="page-title">地址簿</h1>
      <el-button type="primary" @click="openCreate">➕ 新增地址</el-button>
    </div>

    <div v-if="loading" style="display: flex; justify-content: center; padding: 64px 0;">
      <el-icon class="is-loading" :size="28" />
    </div>

    <div v-else-if="addresses.length === 0" class="empty-wrap">
      <div class="empty-icon">📍</div>
      <div class="empty-title">暂无地址</div>
      <div class="empty-desc">添加地址后即可创建运单</div>
    </div>

    <el-table v-else :data="addresses" stripe style="width: 100%;">
      <el-table-column label="标签" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ row.label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="recipient_name" label="收件人" width="120" />
      <el-table-column prop="phone" label="电话" width="140" />
      <el-table-column prop="district_code" label="区划编码" width="120" />
      <el-table-column prop="detail" label="详细地址" min-width="200" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑地址' : '新增地址'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="标签">
          <el-input v-model="form.label" placeholder="如：家、公司" />
        </el-form-item>
        <el-form-item label="收件人">
          <el-input v-model="form.recipient_name" placeholder="收件人姓名" />
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="form.phone" placeholder="手机号码" />
        </el-form-item>
        <el-form-item label="区划编码">
          <el-input v-model="form.district_code" placeholder="如：110101" />
        </el-form-item>
        <el-form-item label="详细地址">
          <el-input v-model="form.detail" type="textarea" :rows="2" placeholder="详细地址" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>