<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { addressesApi, type Address } from '../api/addresses';
import { pricingApi, type QuoteView } from '../api/pricing';
import { shipmentsApi } from '../api/shipments';
import { paymentsApi } from '../api/payments';
import EmptyState from '../components/EmptyState.vue';
const router = useRouter();
type Step = 'address' | 'package' | 'quote' | 'pay';
const step = ref<Step>('address');
const addresses = ref<Address[]>([]);
const loading = ref(false);
const senderId = ref(''); const receiverId = ref('');
const pickupMethod = ref<'DOOR_PICKUP' | 'STATION_DROPOFF'>('DOOR_PICKUP');
const deliveryMethod = ref<'HOME_DELIVERY' | 'STATION_PICKUP'>('HOME_DELIVERY');
const weight = ref(1200); const length = ref(30); const width = ref(20); const height = ref(10);
const declaredValue = ref(0);
const quote = ref<QuoteView | null>(null);
const shipmentNo = ref('');
onMounted(async () => { try { addresses.value = await addressesApi.list(); } catch {} });
const sender = addresses.value.find((a: Address) => a.id === senderId.value);
const receiver = addresses.value.find((a: Address) => a.id === receiverId.value);

async function createQuote() {
  if (!sender || !receiver) return;
  loading.value = true;
  try {
    quote.value = await pricingApi.createQuote({
      origin_district_code: sender.district_code, destination_district_code: receiver.district_code,
      pickup_method: pickupMethod.value, delivery_method: deliveryMethod.value,
      actual_weight_grams: weight.value, length_cm: length.value, width_cm: width.value, height_cm: height.value,
      declared_value_cents: declaredValue.value,
    });
    step.value = 'quote';
  } catch (err: any) { alert(err.message); }
  finally { loading.value = false; }
}

async function payAndCreate() {
  if (!quote.value) return;
  loading.value = true;
  try {
    const s = await shipmentsApi.create({ draft: { sender_address_id: senderId.value || null, receiver_address_id: receiverId.value || null, origin_station_id: null, destination_station_id: null, pickup_method: pickupMethod.value, delivery_method: deliveryMethod.value }, status: 'PENDING_PAYMENT' });
    await paymentsApi.pay(quote.value.id, s.id, quote.value.total_cents);
    await shipmentsApi.confirmPayment(s.id);
    shipmentNo.value = s.shipment_no;
    step.value = 'pay';
  } catch (err: any) { alert(err.message); }
  finally { loading.value = false; }
}
</script>
<template>
  <div class="page-container">
    <h1 class="page-title">创建运单</h1>
    <div style="display: flex; gap: var(--space-xl); margin-bottom: var(--space-xl); padding-bottom: var(--space-lg); border-bottom: 1px solid rgba(0,0,0,0.06);">
      <span v-for="s in [{k:'address',l:'1. 寄收信息'},{k:'package',l:'2. 包裹信息'},{k:'quote',l:'3. 确认报价'},{k:'pay',l:'4. 完成'}]" :key="s.k"
        :style="{ fontSize: '0.8125rem', fontWeight: step === s.k ? 700 : 500, color: step === s.k ? 'var(--color-primary-800)' : 'var(--color-text-muted)' }">{{ s.l }}</span>
    </div>

    <!-- 步骤 1 -->
    <div v-if="step === 'address'" class="card" style="padding: var(--space-xl);">
      <EmptyState v-if="addresses.length === 0" icon="📍" title="暂无地址" description="请先在地址簿中添加地址" />
      <template v-else>
        <div class="form-group" style="margin-bottom: var(--space-lg);">
          <label class="form-label">寄件地址</label>
          <select class="form-input" v-model="senderId"><option value="">请选择</option><option v-for="a in addresses" :key="a.id" :value="a.id">{{ a.label }} — {{ a.recipient_name }} ({{ a.district_code }})</option></select>
        </div>
        <div class="form-group" style="margin-bottom: var(--space-lg);">
          <label class="form-label">收件地址</label>
          <select class="form-input" v-model="receiverId"><option value="">请选择</option><option v-for="a in addresses" :key="a.id" :value="a.id">{{ a.label }} — {{ a.recipient_name }} ({{ a.district_code }})</option></select>
        </div>
        <div style="display: flex; gap: var(--space-lg); margin-bottom: var(--space-lg);">
          <div class="form-group" style="flex:1;"><label class="form-label">寄件方式</label><select class="form-input" v-model="pickupMethod"><option value="DOOR_PICKUP">上门揽收</option><option value="STATION_DROPOFF">网点自寄</option></select></div>
          <div class="form-group" style="flex:1;"><label class="form-label">收件方式</label><select class="form-input" v-model="deliveryMethod"><option value="HOME_DELIVERY">送货上门</option><option value="STATION_PICKUP">网点自取</option></select></div>
        </div>
        <button class="btn btn-primary btn-lg" @click="step = 'package'" :disabled="!senderId || !receiverId">下一步 →</button>
      </template>
    </div>

    <!-- 步骤 2 -->
    <div v-if="step === 'package'" class="card" style="padding: var(--space-xl);">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-lg); margin-bottom: var(--space-lg);">
        <div class="form-group"><label class="form-label">重量 (克)</label><input class="form-input" type="number" v-model="weight" /></div>
        <div class="form-group"><label class="form-label">保价 (分)</label><input class="form-input" type="number" v-model="declaredValue" /></div>
        <div class="form-group"><label class="form-label">长 (cm)</label><input class="form-input" type="number" v-model="length" /></div>
        <div class="form-group"><label class="form-label">宽 (cm)</label><input class="form-input" type="number" v-model="width" /></div>
        <div class="form-group"><label class="form-label">高 (cm)</label><input class="form-input" type="number" v-model="height" /></div>
      </div>
      <div style="display: flex; gap: var(--space-sm);">
        <button class="btn btn-ghost" @click="step = 'address'">← 返回</button>
        <button class="btn btn-primary btn-lg" @click="createQuote" :disabled="loading">{{ loading ? '报价中...' : '生成报价' }}</button>
      </div>
    </div>

    <!-- 步骤 3 -->
    <div v-if="step === 'quote' && quote" class="card" style="padding: var(--space-xl);">
      <div style="margin-bottom: var(--space-lg);">
        <div style="font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 4px;">总费用</div>
        <div class="mono" style="font-size: 1.5rem; font-weight: 700; color: var(--color-primary-800);">¥{{ (quote.total_cents / 100).toFixed(2) }}</div>
        <div style="font-size: 0.75rem; color: var(--color-text-muted); margin-top: 4px;">计费重量 {{ quote.chargeable_weight_grams }}g · {{ quote.rule_version }}</div>
      </div>
      <div style="margin-bottom: var(--space-lg);">
        <h4 style="font-size: 0.8125rem; font-weight: 600; margin-bottom: var(--space-sm);">费用明细</h4>
        <div v-for="(item, i) in quote.line_items" :key="i" style="display: flex; justify-content: space-between; padding: var(--space-xs) 0; font-size: 0.8125rem; border-bottom: 1px solid rgba(0,0,0,0.04);">
          <span>{{ item.label }}</span><span class="mono">¥{{ (item.amount_cents / 100).toFixed(2) }}</span>
        </div>
      </div>
      <div style="display: flex; gap: var(--space-sm);">
        <button class="btn btn-ghost" @click="step = 'package'">← 返回修改</button>
        <button class="btn btn-amber btn-lg" @click="payAndCreate" :disabled="loading">{{ loading ? '支付中...' : `💳 确认支付 ¥${(quote.total_cents / 100).toFixed(2)}` }}</button>
      </div>
    </div>

    <!-- 步骤 4 -->
    <div v-if="step === 'pay'" class="card" style="padding: var(--space-3xl); text-align: center;">
      <div style="font-size: 3rem; margin-bottom: var(--space-lg);">✅</div>
      <h2 style="font-size: 1.25rem; margin-bottom: var(--space-sm);">运单创建成功</h2>
      <div class="mono" style="font-size: 1.125rem; color: var(--color-primary-800); font-weight: 600; margin-bottom: var(--space-xl);">{{ shipmentNo }}</div>
      <div style="display: flex; gap: var(--space-sm); justify-content: center;">
        <button class="btn btn-primary" @click="router.push('/shipments')">查看运单列表</button>
        <button class="btn btn-amber" @click="step = 'address'; quote = null; shipmentNo = '';">再创建一单</button>
      </div>
    </div>
  </div>
</template>