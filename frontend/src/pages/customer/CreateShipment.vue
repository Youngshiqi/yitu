<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { addressesApi, type Address } from '../../api/addresses'
import { pricingApi, type QuoteView } from '../../api/pricing'
import { shipmentsApi } from '../../api/shipments'
import { paymentsApi } from '../../api/payments'
import { ElMessage } from 'element-plus'

const router = useRouter()
type Step = 'address' | 'package' | 'quote' | 'done'

const step = ref<Step>('address')
const loading = ref(false)
const addresses = ref<Address[]>([])
const senderId = ref('')
const receiverId = ref('')
const pickupMethod = ref<'DOOR_PICKUP' | 'STATION_DROPOFF'>('DOOR_PICKUP')
const deliveryMethod = ref<'HOME_DELIVERY' | 'STATION_PICKUP'>('HOME_DELIVERY')
const weight = ref(1200)
const length = ref(30)
const width = ref(20)
const height = ref(10)
const declaredValue = ref(0)
const quote = ref<QuoteView | null>(null)
const shipmentNo = ref('')

onMounted(async () => {
  try { addresses.value = await addressesApi.list() } catch {}
})

const sender = () => addresses.value.find(a => a.id === senderId.value)
const receiver = () => addresses.value.find(a => a.id === receiverId.value)

async function createQuote() {
  const s = sender(); const r = receiver()
  if (!s || !r) return
  loading.value = true
  try {
    quote.value = await pricingApi.createQuote({
      origin_district_code: s.district_code,
      destination_district_code: r.district_code,
      pickup_method: pickupMethod.value,
      delivery_method: deliveryMethod.value,
      actual_weight_grams: weight.value,
      length_cm: length.value,
      width_cm: width.value,
      height_cm: height.value,
      declared_value_cents: declaredValue.value,
    })
    step.value = 'quote'
  } catch (err: any) { ElMessage.error(err.message) }
  finally { loading.value = false }
}

async function payAndCreate() {
  if (!quote.value) return
  loading.value = true
  try {
    const s = await shipmentsApi.create({
      draft: {
        sender_address_id: senderId.value || null,
        receiver_address_id: receiverId.value || null,
        origin_station_id: null,
        destination_station_id: null,
        pickup_method: pickupMethod.value,
        delivery_method: deliveryMethod.value,
      },
      status: 'PENDING_PAYMENT',
    })
    await paymentsApi.pay(quote.value.id, s.id, quote.value.total_cents)
    await shipmentsApi.confirmPayment(s.id)
    shipmentNo.value = s.shipment_no
    step.value = 'done'
  } catch (err: any) { ElMessage.error(err.message) }
  finally { loading.value = false }
}
</script>
<template>
  <div class="page-wrap">
    <h1 class="page-title" style="margin-bottom: 24px;">创建运单</h1>

    <!-- 步骤条 -->
    <el-steps :active="['address','package','quote','done'].indexOf(step)" align-center style="margin-bottom: 32px;">
      <el-step title="寄收信息" />
      <el-step title="包裹信息" />
      <el-step title="确认报价" />
      <el-step title="完成" />
    </el-steps>

    <!-- 第一步：地址 -->
    <el-card v-if="step === 'address'" shadow="never">
      <div v-if="addresses.length === 0" class="empty-wrap">
        <div class="empty-icon">📍</div>
        <div class="empty-title">暂无地址</div>
        <div class="empty-desc">请先在地址簿中添加寄收件地址</div>
        <el-button type="primary" style="margin-top: 12px;" @click="router.push('/addresses')">前往地址簿</el-button>
      </div>
      <template v-else>
        <el-form label-width="80px">
          <el-form-item label="寄件地址">
            <el-select v-model="senderId" placeholder="请选择寄件地址" style="width: 100%;">
              <el-option v-for="a in addresses" :key="a.id" :value="a.id" :label="`${a.label} — ${a.recipient_name} (${a.district_code})`" />
            </el-select>
          </el-form-item>
          <el-form-item label="收件地址">
            <el-select v-model="receiverId" placeholder="请选择收件地址" style="width: 100%;">
              <el-option v-for="a in addresses" :key="a.id" :value="a.id" :label="`${a.label} — ${a.recipient_name} (${a.district_code})`" />
            </el-select>
          </el-form-item>
          <el-form-item label="寄件方式">
            <el-radio-group v-model="pickupMethod">
              <el-radio value="DOOR_PICKUP">上门揽收</el-radio>
              <el-radio value="STATION_DROPOFF">网点自寄</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="收件方式">
            <el-radio-group v-model="deliveryMethod">
              <el-radio value="HOME_DELIVERY">送货上门</el-radio>
              <el-radio value="STATION_PICKUP">网点自取</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <div style="text-align: right; margin-top: 16px;">
          <el-button type="primary" :disabled="!senderId || !receiverId" @click="step = 'package'">下一步</el-button>
        </div>
      </template>
    </el-card>

    <!-- 第二步：包裹 -->
    <el-card v-if="step === 'package'" shadow="never">
      <el-form label-width="100px">
        <el-form-item label="重量 (克)">
          <el-input-number v-model="weight" :min="1" :max="50000" />
        </el-form-item>
        <el-form-item label="尺寸 (cm)">
          <div style="display: flex; gap: 12px;">
            <el-input-number v-model="length" :min="1" placeholder="长" controls-position="right" />
            <el-input-number v-model="width" :min="1" placeholder="宽" controls-position="right" />
            <el-input-number v-model="height" :min="1" placeholder="高" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item label="保价 (分)">
          <el-input-number v-model="declaredValue" :min="0" :step="100" />
        </el-form-item>
      </el-form>
      <div style="display: flex; justify-content: space-between; margin-top: 16px;">
        <el-button @click="step = 'address'">← 返回</el-button>
        <el-button type="warning" :loading="loading" @click="createQuote">生成报价</el-button>
      </div>
    </el-card>

    <!-- 第三步：报价 -->
    <el-card v-if="step === 'quote' && quote" shadow="never">
      <div style="margin-bottom: 24px;">
        <div style="font-size: 0.8125rem; color: var(--el-text-color-secondary); margin-bottom: 8px;">总费用</div>
        <div class="mono" style="font-size: 2rem; font-weight: 700; color: var(--yitu-ink-800);">
          ¥{{ (quote.total_cents / 100).toFixed(2) }}
        </div>
        <div style="font-size: 0.75rem; color: var(--el-text-color-placeholder); margin-top: 4px;">
          计费重量 {{ quote.chargeable_weight_grams }}g · {{ quote.rule_version }}
        </div>
      </div>

      <el-divider />

      <div style="margin-bottom: 24px;">
        <h4 style="font-size: 0.875rem; font-weight: 600; margin-bottom: 12px; color: var(--el-text-color-regular);">费用明细</h4>
        <div v-for="(item, i) in quote.line_items" :key="i"
          style="display: flex; justify-content: space-between; padding: 8px 0; font-size: 0.8125rem; border-bottom: 1px solid var(--el-border-color-light);">
          <span>{{ item.label }}</span>
          <span class="mono">¥{{ (item.amount_cents / 100).toFixed(2) }}</span>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between;">
        <el-button @click="step = 'package'">← 返回修改</el-button>
        <el-button type="warning" size="large" :loading="loading" @click="payAndCreate">
          💳 确认支付 ¥{{ (quote.total_cents / 100).toFixed(2) }}
        </el-button>
      </div>
    </el-card>

    <!-- 第四步：完成 -->
    <el-card v-if="step === 'done'" shadow="never" style="text-align: center; padding: 48px 24px;">
      <div style="font-size: 3rem; margin-bottom: 16px;">✅</div>
      <h2 style="font-size: 1.25rem; margin-bottom: 8px; color: var(--yitu-ink-800);">运单创建成功</h2>
      <div class="mono" style="font-size: 1.125rem; color: var(--yitu-ink-800); font-weight: 600; margin-bottom: 24px;">
        {{ shipmentNo }}
      </div>
      <div style="display: flex; gap: 12px; justify-content: center;">
        <el-button type="primary" @click="router.push('/shipments')">查看运单列表</el-button>
        <el-button type="warning" @click="step = 'address'; quote = null; shipmentNo = '';">再创建一单</el-button>
      </div>
    </el-card>
  </div>
</template>