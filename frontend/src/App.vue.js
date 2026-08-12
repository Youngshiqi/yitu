import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { ArrowRight, Bell, Box, ChatDotRound, Location, Plus, Search, Setting } from '@element-plus/icons-vue';
import { consumeAgentGrant, createAddress, createConversation, createShipment, getAgentDraft, getShipment, issueAgentGrant, listAddresses, listConversations, listMessages, listNotifications, listShipments, listStations, login, markNotificationRead, me, sendAgentMessage, tracking, validateAgentDraft } from './api';
import CourierWorkspace from './CourierWorkspace.vue';
import OperationsWorkspace from './OperationsWorkspace.vue';
import SystemAdminWorkspace from './SystemAdminWorkspace.vue';
const loggedIn = ref(Boolean(localStorage.getItem('yitu_token')));
const user = ref(null);
const view = ref('shipments');
const loading = ref(false);
const shipments = ref([]);
const total = ref(0);
const addresses = ref([]);
const stations = ref([]);
const notifications = ref([]);
const selected = ref(null);
const timeline = ref([]);
const page = ref(1);
const query = ref('');
const loginForm = ref({ login_name: 'customer.demo', password: 'YituDemo2026!' });
// 演示环境身份列表；正式用户名密码登录接入后可替换为后端用户搜索。
const loginAccounts = [
    { login_name: 'customer.demo', label: '客户 · customer.demo', role: 'CUSTOMER' },
    { login_name: 'courier.bijing.demo', label: '北京快递员 · courier.bijing.demo', role: 'COURIER' },
    { login_name: 'courier.shanghai.demo', label: '上海快递员 · courier.shanghai.demo', role: 'COURIER' },
    { login_name: 'operations.demo', label: '运营管理员 · operations.demo', role: 'OPERATIONS_ADMIN' },
    { login_name: 'system.demo', label: '系统管理员 · system.demo', role: 'SYSTEM_ADMIN' },
];
const addressDialog = ref(false);
const addressForm = ref({ label: '常用地址', recipient_name: '', phone: '', district_code: '', detail: '' });
const shipmentForm = ref({ sender_address_id: '', receiver_address_id: '', pickup_method: 'DOOR_PICKUP', delivery_method: 'HOME_DELIVERY' });
const conversations = ref([]);
const activeConversation = ref(null);
const agentMessages = ref([]);
const agentDraft = ref(null);
const agentInput = ref('');
const agentSending = ref(false);
const statusMap = { PENDING_PAYMENT: '待支付', CREATED: '已创建', IN_TRANSIT: '运输中', OUT_FOR_DELIVERY: '派送中', DELIVERED: '已签收', AT_DESTINATION_STATION: '已到达网点' };
const nav = computed(() => [
    { id: 'shipments', label: '我的运单', icon: Box },
    { id: 'create', label: '我要寄件', icon: Plus },
    { id: 'agent', label: 'AI 寄件助手', icon: ChatDotRound },
    { id: 'addresses', label: '地址簿', icon: Location },
    { id: 'notifications', label: '消息中心', icon: Bell, badge: notifications.value.filter(n => n.status !== 'READ').length },
]);
async function loadData() {
    if (!loggedIn.value)
        return;
    loading.value = true;
    try {
        const [ship, addr, station, notice, chats] = await Promise.all([listShipments({ limit: 20, offset: (page.value - 1) * 20 }), listAddresses(), listStations(), listNotifications(), listConversations()]);
        shipments.value = ship.items ?? [];
        total.value = ship.total ?? 0;
        addresses.value = addr;
        stations.value = station;
        notifications.value = notice;
        conversations.value = chats;
    }
    catch {
        ElMessage.error('数据加载失败，请确认后端服务已启动');
    }
    finally {
        loading.value = false;
    }
}
async function doLogin() { try {
    await login(loginForm.value.login_name, loginForm.value.password);
    loggedIn.value = true;
    user.value = await me();
    if (user.value?.role === 'CUSTOMER')
        await loadData();
}
catch {
    ElMessage.error('账号或密码错误');
} }
function logout() { localStorage.removeItem('yitu_token'); loggedIn.value = false; user.value = null; }
async function openShipment(item) { selected.value = await getShipment(item.id); timeline.value = await tracking(item.id); view.value = 'detail'; }
async function saveAddress() { try {
    await createAddress(addressForm.value);
    addressDialog.value = false;
    await loadData();
    ElMessage.success('地址已保存');
}
catch {
    ElMessage.error('地址保存失败');
} }
async function submitShipment() { try {
    await createShipment({ draft: shipmentForm.value, status: 'PENDING_PAYMENT' });
    ElMessage.success('运单已创建');
    view.value = 'shipments';
    await loadData();
}
catch {
    ElMessage.error('请完善寄件信息');
} }
async function openConversation(conversation) { try {
    activeConversation.value = conversation ?? await createConversation('智能寄件');
    agentMessages.value = await listMessages(activeConversation.value.id);
    agentDraft.value = await getAgentDraft(activeConversation.value.id);
}
catch {
    ElMessage.error('AI 助手暂时不可用');
} }
async function sendMessage() { const content = agentInput.value.trim(); if (!content || !activeConversation.value || agentSending.value)
    return; agentInput.value = ''; agentSending.value = true; try {
    const turn = await sendAgentMessage(activeConversation.value.id, content);
    agentMessages.value.push(turn.user_message, turn.assistant_message);
    agentDraft.value = await getAgentDraft(activeConversation.value.id);
}
catch {
    ElMessage.error('消息发送失败，请稍后重试');
}
finally {
    agentSending.value = false;
} }
async function validateDraft() { if (!activeConversation.value)
    return; try {
    const result = await validateAgentDraft(activeConversation.value.id);
    agentDraft.value = result.draft;
    ElMessage.success(`报价已生成：${(result.quote.total_cents / 100).toFixed(2)} 元`);
}
catch {
    ElMessage.warning('请先在对话中补充寄件信息');
} }
async function confirmAgentShipment() { if (!activeConversation.value)
    return; try {
    const grant = await issueAgentGrant(activeConversation.value.id);
    await consumeAgentGrant(grant.id);
    ElMessage.success('运单已创建');
    await loadData();
    view.value = 'shipments';
}
catch {
    ElMessage.error('草稿尚未准备好，请重新确认报价');
} }
async function readNotice(item) { if (item.status !== 'READ') {
    await markNotificationRead(item.id);
    item.status = 'READ';
} }
onMounted(async () => { if (loggedIn.value) {
    try {
        user.value = await me();
        if (user.value?.role === 'CUSTOMER')
            await loadData();
    }
    catch {
        logout();
    }
} });
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
if (!__VLS_ctx.loggedIn) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "login-page" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "login-art" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "eyebrow" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.br, __VLS_intrinsicElements.br)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "route-line" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    const __VLS_0 = {}.ArrowRight;
    /** @type {[typeof __VLS_components.ArrowRight, ]} */ ;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent(__VLS_0, new __VLS_0({}));
    const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    const __VLS_4 = {}.ElCard;
    /** @type {[typeof __VLS_components.ElCard, typeof __VLS_components.elCard, typeof __VLS_components.ElCard, typeof __VLS_components.elCard, ]} */ ;
    // @ts-ignore
    const __VLS_5 = __VLS_asFunctionalComponent(__VLS_4, new __VLS_4({
        ...{ class: "login-card" },
        shadow: "never",
    }));
    const __VLS_6 = __VLS_5({
        ...{ class: "login-card" },
        shadow: "never",
    }, ...__VLS_functionalComponentArgsRest(__VLS_5));
    __VLS_7.slots.default;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "brand-mark" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "muted" },
    });
    const __VLS_8 = {}.ElForm;
    /** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
    // @ts-ignore
    const __VLS_9 = __VLS_asFunctionalComponent(__VLS_8, new __VLS_8({
        ...{ 'onSubmit': {} },
        ...{ 'onKeyup': {} },
    }));
    const __VLS_10 = __VLS_9({
        ...{ 'onSubmit': {} },
        ...{ 'onKeyup': {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_9));
    let __VLS_12;
    let __VLS_13;
    let __VLS_14;
    const __VLS_15 = {
        onSubmit: (__VLS_ctx.doLogin)
    };
    const __VLS_16 = {
        onKeyup: (__VLS_ctx.doLogin)
    };
    __VLS_11.slots.default;
    const __VLS_17 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_18 = __VLS_asFunctionalComponent(__VLS_17, new __VLS_17({
        label: "登录身份",
    }));
    const __VLS_19 = __VLS_18({
        label: "登录身份",
    }, ...__VLS_functionalComponentArgsRest(__VLS_18));
    __VLS_20.slots.default;
    const __VLS_21 = {}.ElSelect;
    /** @type {[typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, ]} */ ;
    // @ts-ignore
    const __VLS_22 = __VLS_asFunctionalComponent(__VLS_21, new __VLS_21({
        modelValue: (__VLS_ctx.loginForm.login_name),
        size: "large",
        ...{ class: "full-input" },
        filterable: true,
    }));
    const __VLS_23 = __VLS_22({
        modelValue: (__VLS_ctx.loginForm.login_name),
        size: "large",
        ...{ class: "full-input" },
        filterable: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_22));
    __VLS_24.slots.default;
    for (const [account] of __VLS_getVForSourceType((__VLS_ctx.loginAccounts))) {
        const __VLS_25 = {}.ElOption;
        /** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
        // @ts-ignore
        const __VLS_26 = __VLS_asFunctionalComponent(__VLS_25, new __VLS_25({
            key: (account.login_name),
            label: (account.label),
            value: (account.login_name),
        }));
        const __VLS_27 = __VLS_26({
            key: (account.login_name),
            label: (account.label),
            value: (account.login_name),
        }, ...__VLS_functionalComponentArgsRest(__VLS_26));
        __VLS_28.slots.default;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "login-option" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (account.label);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (account.role);
        var __VLS_28;
    }
    var __VLS_24;
    var __VLS_20;
    const __VLS_29 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_30 = __VLS_asFunctionalComponent(__VLS_29, new __VLS_29({
        label: "密码",
    }));
    const __VLS_31 = __VLS_30({
        label: "密码",
    }, ...__VLS_functionalComponentArgsRest(__VLS_30));
    __VLS_32.slots.default;
    const __VLS_33 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_34 = __VLS_asFunctionalComponent(__VLS_33, new __VLS_33({
        modelValue: (__VLS_ctx.loginForm.password),
        type: "password",
        showPassword: true,
        size: "large",
    }));
    const __VLS_35 = __VLS_34({
        modelValue: (__VLS_ctx.loginForm.password),
        type: "password",
        showPassword: true,
        size: "large",
    }, ...__VLS_functionalComponentArgsRest(__VLS_34));
    var __VLS_32;
    const __VLS_37 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_38 = __VLS_asFunctionalComponent(__VLS_37, new __VLS_37({
        ...{ 'onClick': {} },
        type: "primary",
        size: "large",
        ...{ class: "full-btn" },
    }));
    const __VLS_39 = __VLS_38({
        ...{ 'onClick': {} },
        type: "primary",
        size: "large",
        ...{ class: "full-btn" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_38));
    let __VLS_41;
    let __VLS_42;
    let __VLS_43;
    const __VLS_44 = {
        onClick: (__VLS_ctx.doLogin)
    };
    __VLS_40.slots.default;
    const __VLS_45 = {}.ArrowRight;
    /** @type {[typeof __VLS_components.ArrowRight, ]} */ ;
    // @ts-ignore
    const __VLS_46 = __VLS_asFunctionalComponent(__VLS_45, new __VLS_45({}));
    const __VLS_47 = __VLS_46({}, ...__VLS_functionalComponentArgsRest(__VLS_46));
    var __VLS_40;
    var __VLS_11;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "login-note" },
    });
    var __VLS_7;
}
else if (__VLS_ctx.user?.role === 'COURIER') {
    /** @type {[typeof CourierWorkspace, ]} */ ;
    // @ts-ignore
    const __VLS_49 = __VLS_asFunctionalComponent(CourierWorkspace, new CourierWorkspace({
        ...{ 'onLogout': {} },
        user: (__VLS_ctx.user),
    }));
    const __VLS_50 = __VLS_49({
        ...{ 'onLogout': {} },
        user: (__VLS_ctx.user),
    }, ...__VLS_functionalComponentArgsRest(__VLS_49));
    let __VLS_52;
    let __VLS_53;
    let __VLS_54;
    const __VLS_55 = {
        onLogout: (__VLS_ctx.logout)
    };
    var __VLS_56 = {};
    var __VLS_51;
}
else if (__VLS_ctx.user?.role === 'OPERATIONS_ADMIN') {
    /** @type {[typeof OperationsWorkspace, ]} */ ;
    // @ts-ignore
    const __VLS_57 = __VLS_asFunctionalComponent(OperationsWorkspace, new OperationsWorkspace({
        ...{ 'onLogout': {} },
        user: (__VLS_ctx.user),
    }));
    const __VLS_58 = __VLS_57({
        ...{ 'onLogout': {} },
        user: (__VLS_ctx.user),
    }, ...__VLS_functionalComponentArgsRest(__VLS_57));
    let __VLS_60;
    let __VLS_61;
    let __VLS_62;
    const __VLS_63 = {
        onLogout: (__VLS_ctx.logout)
    };
    var __VLS_64 = {};
    var __VLS_59;
}
else if (__VLS_ctx.user?.role === 'SYSTEM_ADMIN') {
    /** @type {[typeof SystemAdminWorkspace, ]} */ ;
    // @ts-ignore
    const __VLS_65 = __VLS_asFunctionalComponent(SystemAdminWorkspace, new SystemAdminWorkspace({
        ...{ 'onLogout': {} },
        user: (__VLS_ctx.user),
    }));
    const __VLS_66 = __VLS_65({
        ...{ 'onLogout': {} },
        user: (__VLS_ctx.user),
    }, ...__VLS_functionalComponentArgsRest(__VLS_65));
    let __VLS_68;
    let __VLS_69;
    let __VLS_70;
    const __VLS_71 = {
        onLogout: (__VLS_ctx.logout)
    };
    var __VLS_72 = {};
    var __VLS_67;
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "app-shell" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
        ...{ class: "sidebar" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "logo" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "workspace-label" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({});
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.nav))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.loggedIn))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'COURIER'))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                        return;
                    __VLS_ctx.view = item.id;
                } },
            key: (item.id),
            ...{ class: ({ active: __VLS_ctx.view === item.id }) },
        });
        const __VLS_73 = ((item.icon));
        // @ts-ignore
        const __VLS_74 = __VLS_asFunctionalComponent(__VLS_73, new __VLS_73({}));
        const __VLS_75 = __VLS_74({}, ...__VLS_functionalComponentArgsRest(__VLS_74));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (item.label);
        if (item.badge) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (item.badge);
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "sidebar-foot" },
    });
    const __VLS_77 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_78 = __VLS_asFunctionalComponent(__VLS_77, new __VLS_77({
        ...{ 'onClick': {} },
        text: true,
    }));
    const __VLS_79 = __VLS_78({
        ...{ 'onClick': {} },
        text: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_78));
    let __VLS_81;
    let __VLS_82;
    let __VLS_83;
    const __VLS_84 = {
        onClick: (__VLS_ctx.logout)
    };
    __VLS_80.slots.default;
    const __VLS_85 = {}.Setting;
    /** @type {[typeof __VLS_components.Setting, ]} */ ;
    // @ts-ignore
    const __VLS_86 = __VLS_asFunctionalComponent(__VLS_85, new __VLS_85({}));
    const __VLS_87 = __VLS_86({}, ...__VLS_functionalComponentArgsRest(__VLS_86));
    var __VLS_80;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
        ...{ class: "main" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({
        ...{ class: "topbar" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "crumb" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.nav.find(n => n.id === __VLS_ctx.view)?.label ?? '运单详情');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
    (__VLS_ctx.view === 'detail' ? '运单详情' : __VLS_ctx.nav.find(n => n.id === __VLS_ctx.view)?.label);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "top-actions" },
    });
    const __VLS_89 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_90 = __VLS_asFunctionalComponent(__VLS_89, new __VLS_89({
        modelValue: (__VLS_ctx.query),
        placeholder: "搜索运单号",
        prefixIcon: (__VLS_ctx.Search),
        clearable: true,
    }));
    const __VLS_91 = __VLS_90({
        modelValue: (__VLS_ctx.query),
        placeholder: "搜索运单号",
        prefixIcon: (__VLS_ctx.Search),
        clearable: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_90));
    const __VLS_93 = {}.ElAvatar;
    /** @type {[typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, ]} */ ;
    // @ts-ignore
    const __VLS_94 = __VLS_asFunctionalComponent(__VLS_93, new __VLS_93({
        size: (34),
    }));
    const __VLS_95 = __VLS_94({
        size: (34),
    }, ...__VLS_functionalComponentArgsRest(__VLS_94));
    __VLS_96.slots.default;
    (__VLS_ctx.user?.display_name?.slice(0, 1));
    var __VLS_96;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "user-name" },
    });
    (__VLS_ctx.user?.display_name || '演示客户');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "content" },
    });
    __VLS_asFunctionalDirective(__VLS_directives.vLoading)(null, { ...__VLS_directiveBindingRestFields, value: (__VLS_ctx.loading) }, null, null);
    if (__VLS_ctx.view === 'shipments') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "page-block" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        const __VLS_97 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_98 = __VLS_asFunctionalComponent(__VLS_97, new __VLS_97({
            ...{ 'onClick': {} },
            type: "primary",
        }));
        const __VLS_99 = __VLS_98({
            ...{ 'onClick': {} },
            type: "primary",
        }, ...__VLS_functionalComponentArgsRest(__VLS_98));
        let __VLS_101;
        let __VLS_102;
        let __VLS_103;
        const __VLS_104 = {
            onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.loggedIn))
                    return;
                if (!!(__VLS_ctx.user?.role === 'COURIER'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                    return;
                if (!(__VLS_ctx.view === 'shipments'))
                    return;
                __VLS_ctx.view = 'create';
            }
        };
        __VLS_100.slots.default;
        const __VLS_105 = {}.Plus;
        /** @type {[typeof __VLS_components.Plus, ]} */ ;
        // @ts-ignore
        const __VLS_106 = __VLS_asFunctionalComponent(__VLS_105, new __VLS_105({}));
        const __VLS_107 = __VLS_106({}, ...__VLS_functionalComponentArgsRest(__VLS_106));
        var __VLS_100;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "stat-strip" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.total);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.shipments.filter(s => s.status === 'IN_TRANSIT').length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.shipments.filter(s => s.status === 'PENDING_PAYMENT').length);
        const __VLS_109 = {}.ElTable;
        /** @type {[typeof __VLS_components.ElTable, typeof __VLS_components.elTable, typeof __VLS_components.ElTable, typeof __VLS_components.elTable, ]} */ ;
        // @ts-ignore
        const __VLS_110 = __VLS_asFunctionalComponent(__VLS_109, new __VLS_109({
            ...{ 'onRowClick': {} },
            data: (__VLS_ctx.shipments.filter(s => !__VLS_ctx.query || s.shipment_no.includes(__VLS_ctx.query))),
            ...{ class: "shipment-table" },
        }));
        const __VLS_111 = __VLS_110({
            ...{ 'onRowClick': {} },
            data: (__VLS_ctx.shipments.filter(s => !__VLS_ctx.query || s.shipment_no.includes(__VLS_ctx.query))),
            ...{ class: "shipment-table" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_110));
        let __VLS_113;
        let __VLS_114;
        let __VLS_115;
        const __VLS_116 = {
            onRowClick: (__VLS_ctx.openShipment)
        };
        __VLS_112.slots.default;
        const __VLS_117 = {}.ElTableColumn;
        /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
        // @ts-ignore
        const __VLS_118 = __VLS_asFunctionalComponent(__VLS_117, new __VLS_117({
            prop: "shipment_no",
            label: "运单号",
            minWidth: "190",
        }));
        const __VLS_119 = __VLS_118({
            prop: "shipment_no",
            label: "运单号",
            minWidth: "190",
        }, ...__VLS_functionalComponentArgsRest(__VLS_118));
        __VLS_120.slots.default;
        {
            const { default: __VLS_thisSlot } = __VLS_120.slots;
            const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "shipment-no" },
            });
            (row.shipment_no);
        }
        var __VLS_120;
        const __VLS_121 = {}.ElTableColumn;
        /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
        // @ts-ignore
        const __VLS_122 = __VLS_asFunctionalComponent(__VLS_121, new __VLS_121({
            prop: "status",
            label: "状态",
        }));
        const __VLS_123 = __VLS_122({
            prop: "status",
            label: "状态",
        }, ...__VLS_functionalComponentArgsRest(__VLS_122));
        __VLS_124.slots.default;
        {
            const { default: __VLS_thisSlot } = __VLS_124.slots;
            const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
            const __VLS_125 = {}.ElTag;
            /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
            // @ts-ignore
            const __VLS_126 = __VLS_asFunctionalComponent(__VLS_125, new __VLS_125({
                type: (row.status === 'DELIVERED' ? 'success' : row.status === 'PENDING_PAYMENT' ? 'warning' : 'primary'),
                effect: "light",
            }));
            const __VLS_127 = __VLS_126({
                type: (row.status === 'DELIVERED' ? 'success' : row.status === 'PENDING_PAYMENT' ? 'warning' : 'primary'),
                effect: "light",
            }, ...__VLS_functionalComponentArgsRest(__VLS_126));
            __VLS_128.slots.default;
            (__VLS_ctx.statusMap[row.status] || row.status);
            var __VLS_128;
        }
        var __VLS_124;
        const __VLS_129 = {}.ElTableColumn;
        /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
        // @ts-ignore
        const __VLS_130 = __VLS_asFunctionalComponent(__VLS_129, new __VLS_129({
            label: "操作",
            width: "100",
        }));
        const __VLS_131 = __VLS_130({
            label: "操作",
            width: "100",
        }, ...__VLS_functionalComponentArgsRest(__VLS_130));
        __VLS_132.slots.default;
        {
            const { default: __VLS_thisSlot } = __VLS_132.slots;
            const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
            const __VLS_133 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_134 = __VLS_asFunctionalComponent(__VLS_133, new __VLS_133({
                ...{ 'onClick': {} },
                text: true,
                type: "primary",
            }));
            const __VLS_135 = __VLS_134({
                ...{ 'onClick': {} },
                text: true,
                type: "primary",
            }, ...__VLS_functionalComponentArgsRest(__VLS_134));
            let __VLS_137;
            let __VLS_138;
            let __VLS_139;
            const __VLS_140 = {
                onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.loggedIn))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'COURIER'))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                        return;
                    if (!(__VLS_ctx.view === 'shipments'))
                        return;
                    __VLS_ctx.openShipment(row);
                }
            };
            __VLS_136.slots.default;
            const __VLS_141 = {}.ArrowRight;
            /** @type {[typeof __VLS_components.ArrowRight, ]} */ ;
            // @ts-ignore
            const __VLS_142 = __VLS_asFunctionalComponent(__VLS_141, new __VLS_141({}));
            const __VLS_143 = __VLS_142({}, ...__VLS_functionalComponentArgsRest(__VLS_142));
            var __VLS_136;
        }
        var __VLS_132;
        var __VLS_112;
        if (__VLS_ctx.total > 20) {
            const __VLS_145 = {}.ElPagination;
            /** @type {[typeof __VLS_components.ElPagination, typeof __VLS_components.elPagination, ]} */ ;
            // @ts-ignore
            const __VLS_146 = __VLS_asFunctionalComponent(__VLS_145, new __VLS_145({
                ...{ 'onCurrentChange': {} },
                currentPage: (__VLS_ctx.page),
                layout: "prev, pager, next",
                total: (__VLS_ctx.total),
            }));
            const __VLS_147 = __VLS_146({
                ...{ 'onCurrentChange': {} },
                currentPage: (__VLS_ctx.page),
                layout: "prev, pager, next",
                total: (__VLS_ctx.total),
            }, ...__VLS_functionalComponentArgsRest(__VLS_146));
            let __VLS_149;
            let __VLS_150;
            let __VLS_151;
            const __VLS_152 = {
                onCurrentChange: (__VLS_ctx.loadData)
            };
            var __VLS_148;
        }
    }
    else if (__VLS_ctx.view === 'create') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "page-block narrow" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        const __VLS_153 = {}.ElCard;
        /** @type {[typeof __VLS_components.ElCard, typeof __VLS_components.elCard, typeof __VLS_components.ElCard, typeof __VLS_components.elCard, ]} */ ;
        // @ts-ignore
        const __VLS_154 = __VLS_asFunctionalComponent(__VLS_153, new __VLS_153({
            shadow: "never",
            ...{ class: "form-card" },
        }));
        const __VLS_155 = __VLS_154({
            shadow: "never",
            ...{ class: "form-card" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_154));
        __VLS_156.slots.default;
        const __VLS_157 = {}.ElForm;
        /** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
        // @ts-ignore
        const __VLS_158 = __VLS_asFunctionalComponent(__VLS_157, new __VLS_157({
            labelPosition: "top",
        }));
        const __VLS_159 = __VLS_158({
            labelPosition: "top",
        }, ...__VLS_functionalComponentArgsRest(__VLS_158));
        __VLS_160.slots.default;
        const __VLS_161 = {}.ElFormItem;
        /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
        // @ts-ignore
        const __VLS_162 = __VLS_asFunctionalComponent(__VLS_161, new __VLS_161({
            label: "寄件地址",
        }));
        const __VLS_163 = __VLS_162({
            label: "寄件地址",
        }, ...__VLS_functionalComponentArgsRest(__VLS_162));
        __VLS_164.slots.default;
        const __VLS_165 = {}.ElSelect;
        /** @type {[typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, ]} */ ;
        // @ts-ignore
        const __VLS_166 = __VLS_asFunctionalComponent(__VLS_165, new __VLS_165({
            modelValue: (__VLS_ctx.shipmentForm.sender_address_id),
            placeholder: "选择寄件地址",
            filterable: true,
        }));
        const __VLS_167 = __VLS_166({
            modelValue: (__VLS_ctx.shipmentForm.sender_address_id),
            placeholder: "选择寄件地址",
            filterable: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_166));
        __VLS_168.slots.default;
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.addresses))) {
            const __VLS_169 = {}.ElOption;
            /** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
            // @ts-ignore
            const __VLS_170 = __VLS_asFunctionalComponent(__VLS_169, new __VLS_169({
                key: (a.id),
                label: (`${a.recipient_name} · ${a.detail}`),
                value: (a.id),
            }));
            const __VLS_171 = __VLS_170({
                key: (a.id),
                label: (`${a.recipient_name} · ${a.detail}`),
                value: (a.id),
            }, ...__VLS_functionalComponentArgsRest(__VLS_170));
        }
        var __VLS_168;
        var __VLS_164;
        const __VLS_173 = {}.ElFormItem;
        /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
        // @ts-ignore
        const __VLS_174 = __VLS_asFunctionalComponent(__VLS_173, new __VLS_173({
            label: "收件地址",
        }));
        const __VLS_175 = __VLS_174({
            label: "收件地址",
        }, ...__VLS_functionalComponentArgsRest(__VLS_174));
        __VLS_176.slots.default;
        const __VLS_177 = {}.ElSelect;
        /** @type {[typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, ]} */ ;
        // @ts-ignore
        const __VLS_178 = __VLS_asFunctionalComponent(__VLS_177, new __VLS_177({
            modelValue: (__VLS_ctx.shipmentForm.receiver_address_id),
            placeholder: "选择收件地址",
            filterable: true,
        }));
        const __VLS_179 = __VLS_178({
            modelValue: (__VLS_ctx.shipmentForm.receiver_address_id),
            placeholder: "选择收件地址",
            filterable: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_178));
        __VLS_180.slots.default;
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.addresses))) {
            const __VLS_181 = {}.ElOption;
            /** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
            // @ts-ignore
            const __VLS_182 = __VLS_asFunctionalComponent(__VLS_181, new __VLS_181({
                key: (a.id),
                label: (`${a.recipient_name} · ${a.detail}`),
                value: (a.id),
            }));
            const __VLS_183 = __VLS_182({
                key: (a.id),
                label: (`${a.recipient_name} · ${a.detail}`),
                value: (a.id),
            }, ...__VLS_functionalComponentArgsRest(__VLS_182));
        }
        var __VLS_180;
        var __VLS_176;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "form-grid" },
        });
        const __VLS_185 = {}.ElFormItem;
        /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
        // @ts-ignore
        const __VLS_186 = __VLS_asFunctionalComponent(__VLS_185, new __VLS_185({
            label: "寄件方式",
        }));
        const __VLS_187 = __VLS_186({
            label: "寄件方式",
        }, ...__VLS_functionalComponentArgsRest(__VLS_186));
        __VLS_188.slots.default;
        const __VLS_189 = {}.ElRadioGroup;
        /** @type {[typeof __VLS_components.ElRadioGroup, typeof __VLS_components.elRadioGroup, typeof __VLS_components.ElRadioGroup, typeof __VLS_components.elRadioGroup, ]} */ ;
        // @ts-ignore
        const __VLS_190 = __VLS_asFunctionalComponent(__VLS_189, new __VLS_189({
            modelValue: (__VLS_ctx.shipmentForm.pickup_method),
        }));
        const __VLS_191 = __VLS_190({
            modelValue: (__VLS_ctx.shipmentForm.pickup_method),
        }, ...__VLS_functionalComponentArgsRest(__VLS_190));
        __VLS_192.slots.default;
        const __VLS_193 = {}.ElRadioButton;
        /** @type {[typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, ]} */ ;
        // @ts-ignore
        const __VLS_194 = __VLS_asFunctionalComponent(__VLS_193, new __VLS_193({
            value: "DOOR_PICKUP",
        }));
        const __VLS_195 = __VLS_194({
            value: "DOOR_PICKUP",
        }, ...__VLS_functionalComponentArgsRest(__VLS_194));
        __VLS_196.slots.default;
        var __VLS_196;
        const __VLS_197 = {}.ElRadioButton;
        /** @type {[typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, ]} */ ;
        // @ts-ignore
        const __VLS_198 = __VLS_asFunctionalComponent(__VLS_197, new __VLS_197({
            value: "STATION_DROPOFF",
        }));
        const __VLS_199 = __VLS_198({
            value: "STATION_DROPOFF",
        }, ...__VLS_functionalComponentArgsRest(__VLS_198));
        __VLS_200.slots.default;
        var __VLS_200;
        var __VLS_192;
        var __VLS_188;
        const __VLS_201 = {}.ElFormItem;
        /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
        // @ts-ignore
        const __VLS_202 = __VLS_asFunctionalComponent(__VLS_201, new __VLS_201({
            label: "派送方式",
        }));
        const __VLS_203 = __VLS_202({
            label: "派送方式",
        }, ...__VLS_functionalComponentArgsRest(__VLS_202));
        __VLS_204.slots.default;
        const __VLS_205 = {}.ElRadioGroup;
        /** @type {[typeof __VLS_components.ElRadioGroup, typeof __VLS_components.elRadioGroup, typeof __VLS_components.ElRadioGroup, typeof __VLS_components.elRadioGroup, ]} */ ;
        // @ts-ignore
        const __VLS_206 = __VLS_asFunctionalComponent(__VLS_205, new __VLS_205({
            modelValue: (__VLS_ctx.shipmentForm.delivery_method),
        }));
        const __VLS_207 = __VLS_206({
            modelValue: (__VLS_ctx.shipmentForm.delivery_method),
        }, ...__VLS_functionalComponentArgsRest(__VLS_206));
        __VLS_208.slots.default;
        const __VLS_209 = {}.ElRadioButton;
        /** @type {[typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, ]} */ ;
        // @ts-ignore
        const __VLS_210 = __VLS_asFunctionalComponent(__VLS_209, new __VLS_209({
            value: "HOME_DELIVERY",
        }));
        const __VLS_211 = __VLS_210({
            value: "HOME_DELIVERY",
        }, ...__VLS_functionalComponentArgsRest(__VLS_210));
        __VLS_212.slots.default;
        var __VLS_212;
        const __VLS_213 = {}.ElRadioButton;
        /** @type {[typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, typeof __VLS_components.ElRadioButton, typeof __VLS_components.elRadioButton, ]} */ ;
        // @ts-ignore
        const __VLS_214 = __VLS_asFunctionalComponent(__VLS_213, new __VLS_213({
            value: "STATION_PICKUP",
        }));
        const __VLS_215 = __VLS_214({
            value: "STATION_PICKUP",
        }, ...__VLS_functionalComponentArgsRest(__VLS_214));
        __VLS_216.slots.default;
        var __VLS_216;
        var __VLS_208;
        var __VLS_204;
        const __VLS_217 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_218 = __VLS_asFunctionalComponent(__VLS_217, new __VLS_217({
            ...{ 'onClick': {} },
            type: "primary",
            size: "large",
        }));
        const __VLS_219 = __VLS_218({
            ...{ 'onClick': {} },
            type: "primary",
            size: "large",
        }, ...__VLS_functionalComponentArgsRest(__VLS_218));
        let __VLS_221;
        let __VLS_222;
        let __VLS_223;
        const __VLS_224 = {
            onClick: (__VLS_ctx.submitShipment)
        };
        __VLS_220.slots.default;
        const __VLS_225 = {}.ArrowRight;
        /** @type {[typeof __VLS_components.ArrowRight, ]} */ ;
        // @ts-ignore
        const __VLS_226 = __VLS_asFunctionalComponent(__VLS_225, new __VLS_225({}));
        const __VLS_227 = __VLS_226({}, ...__VLS_functionalComponentArgsRest(__VLS_226));
        var __VLS_220;
        var __VLS_160;
        var __VLS_156;
    }
    else if (__VLS_ctx.view === 'agent') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "agent-page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
            ...{ class: "chat-list" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        const __VLS_229 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_230 = __VLS_asFunctionalComponent(__VLS_229, new __VLS_229({
            ...{ 'onClick': {} },
            circle: true,
            type: "primary",
            icon: (__VLS_ctx.Plus),
        }));
        const __VLS_231 = __VLS_230({
            ...{ 'onClick': {} },
            circle: true,
            type: "primary",
            icon: (__VLS_ctx.Plus),
        }, ...__VLS_functionalComponentArgsRest(__VLS_230));
        let __VLS_233;
        let __VLS_234;
        let __VLS_235;
        const __VLS_236 = {
            onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.loggedIn))
                    return;
                if (!!(__VLS_ctx.user?.role === 'COURIER'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                    return;
                if (!!(__VLS_ctx.view === 'shipments'))
                    return;
                if (!!(__VLS_ctx.view === 'create'))
                    return;
                if (!(__VLS_ctx.view === 'agent'))
                    return;
                __VLS_ctx.openConversation();
            }
        };
        var __VLS_232;
        for (const [chat] of __VLS_getVForSourceType((__VLS_ctx.conversations))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.loggedIn))
                            return;
                        if (!!(__VLS_ctx.user?.role === 'COURIER'))
                            return;
                        if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                            return;
                        if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                            return;
                        if (!!(__VLS_ctx.view === 'shipments'))
                            return;
                        if (!!(__VLS_ctx.view === 'create'))
                            return;
                        if (!(__VLS_ctx.view === 'agent'))
                            return;
                        __VLS_ctx.openConversation(chat);
                    } },
                key: (chat.id),
                ...{ class: (['chat-item', { active: __VLS_ctx.activeConversation?.id === chat.id }]) },
            });
            const __VLS_237 = {}.ChatDotRound;
            /** @type {[typeof __VLS_components.ChatDotRound, ]} */ ;
            // @ts-ignore
            const __VLS_238 = __VLS_asFunctionalComponent(__VLS_237, new __VLS_237({}));
            const __VLS_239 = __VLS_238({}, ...__VLS_functionalComponentArgsRest(__VLS_238));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (chat.title || '未命名会话');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (new Date(chat.updated_at).toLocaleDateString('zh-CN'));
        }
        if (!__VLS_ctx.conversations.length) {
            const __VLS_241 = {}.ElEmpty;
            /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
            // @ts-ignore
            const __VLS_242 = __VLS_asFunctionalComponent(__VLS_241, new __VLS_241({
                description: "开始一次智能寄件",
            }));
            const __VLS_243 = __VLS_242({
                description: "开始一次智能寄件",
            }, ...__VLS_functionalComponentArgsRest(__VLS_242));
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "chat-window" },
        });
        if (__VLS_ctx.activeConversation) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "chat-body" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "chat-intro" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "agent-orb" },
            });
            const __VLS_245 = {}.ChatDotRound;
            /** @type {[typeof __VLS_components.ChatDotRound, ]} */ ;
            // @ts-ignore
            const __VLS_246 = __VLS_asFunctionalComponent(__VLS_245, new __VLS_245({}));
            const __VLS_247 = __VLS_246({}, ...__VLS_functionalComponentArgsRest(__VLS_246));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "messages" },
            });
            for (const [message] of __VLS_getVForSourceType((__VLS_ctx.agentMessages))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (message.id),
                    ...{ class: (['message', message.role]) },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "message-bubble" },
                });
                (message.content);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "chat-composer" },
            });
            const __VLS_249 = {}.ElInput;
            /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
            // @ts-ignore
            const __VLS_250 = __VLS_asFunctionalComponent(__VLS_249, new __VLS_249({
                ...{ 'onKeydown': {} },
                modelValue: (__VLS_ctx.agentInput),
                type: "textarea",
                rows: (2),
                resize: "none",
                placeholder: "例如：帮我从广州寄一箱衣服到上海",
            }));
            const __VLS_251 = __VLS_250({
                ...{ 'onKeydown': {} },
                modelValue: (__VLS_ctx.agentInput),
                type: "textarea",
                rows: (2),
                resize: "none",
                placeholder: "例如：帮我从广州寄一箱衣服到上海",
            }, ...__VLS_functionalComponentArgsRest(__VLS_250));
            let __VLS_253;
            let __VLS_254;
            let __VLS_255;
            const __VLS_256 = {
                onKeydown: (__VLS_ctx.sendMessage)
            };
            var __VLS_252;
            const __VLS_257 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_258 = __VLS_asFunctionalComponent(__VLS_257, new __VLS_257({
                ...{ 'onClick': {} },
                type: "primary",
                loading: (__VLS_ctx.agentSending),
                icon: (__VLS_ctx.ArrowRight),
            }));
            const __VLS_259 = __VLS_258({
                ...{ 'onClick': {} },
                type: "primary",
                loading: (__VLS_ctx.agentSending),
                icon: (__VLS_ctx.ArrowRight),
            }, ...__VLS_functionalComponentArgsRest(__VLS_258));
            let __VLS_261;
            let __VLS_262;
            let __VLS_263;
            const __VLS_264 = {
                onClick: (__VLS_ctx.sendMessage)
            };
            var __VLS_260;
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "chat-empty" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "agent-orb" },
            });
            const __VLS_265 = {}.ChatDotRound;
            /** @type {[typeof __VLS_components.ChatDotRound, ]} */ ;
            // @ts-ignore
            const __VLS_266 = __VLS_asFunctionalComponent(__VLS_265, new __VLS_265({}));
            const __VLS_267 = __VLS_266({}, ...__VLS_functionalComponentArgsRest(__VLS_266));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            const __VLS_269 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_270 = __VLS_asFunctionalComponent(__VLS_269, new __VLS_269({
                ...{ 'onClick': {} },
                type: "primary",
            }));
            const __VLS_271 = __VLS_270({
                ...{ 'onClick': {} },
                type: "primary",
            }, ...__VLS_functionalComponentArgsRest(__VLS_270));
            let __VLS_273;
            let __VLS_274;
            let __VLS_275;
            const __VLS_276 = {
                onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.loggedIn))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'COURIER'))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                        return;
                    if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                        return;
                    if (!!(__VLS_ctx.view === 'shipments'))
                        return;
                    if (!!(__VLS_ctx.view === 'create'))
                        return;
                    if (!(__VLS_ctx.view === 'agent'))
                        return;
                    if (!!(__VLS_ctx.activeConversation))
                        return;
                    __VLS_ctx.openConversation();
                }
            };
            __VLS_272.slots.default;
            var __VLS_272;
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
            ...{ class: "draft-panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        if (__VLS_ctx.agentDraft) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-content" },
            });
            const __VLS_277 = {}.ElTag;
            /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
            // @ts-ignore
            const __VLS_278 = __VLS_asFunctionalComponent(__VLS_277, new __VLS_277({
                type: (__VLS_ctx.agentDraft.status === 'READY_FOR_CONFIRMATION' ? 'success' : 'warning'),
            }));
            const __VLS_279 = __VLS_278({
                type: (__VLS_ctx.agentDraft.status === 'READY_FOR_CONFIRMATION' ? 'success' : 'warning'),
            }, ...__VLS_functionalComponentArgsRest(__VLS_278));
            __VLS_280.slots.default;
            (__VLS_ctx.agentDraft.status === 'READY_FOR_CONFIRMATION' ? '待确认' : '信息补充中');
            var __VLS_280;
            __VLS_asFunctionalElement(__VLS_intrinsicElements.dl, __VLS_intrinsicElements.dl)({});
            for (const [value, key] of __VLS_getVForSourceType((__VLS_ctx.agentDraft.payload))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (key),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
                (key);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
                (value);
            }
            if (__VLS_ctx.agentDraft.status !== 'READY_FOR_CONFIRMATION') {
                const __VLS_281 = {}.ElButton;
                /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
                // @ts-ignore
                const __VLS_282 = __VLS_asFunctionalComponent(__VLS_281, new __VLS_281({
                    ...{ 'onClick': {} },
                    ...{ class: "full-btn" },
                }));
                const __VLS_283 = __VLS_282({
                    ...{ 'onClick': {} },
                    ...{ class: "full-btn" },
                }, ...__VLS_functionalComponentArgsRest(__VLS_282));
                let __VLS_285;
                let __VLS_286;
                let __VLS_287;
                const __VLS_288 = {
                    onClick: (__VLS_ctx.validateDraft)
                };
                __VLS_284.slots.default;
                var __VLS_284;
            }
            else {
                const __VLS_289 = {}.ElButton;
                /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
                // @ts-ignore
                const __VLS_290 = __VLS_asFunctionalComponent(__VLS_289, new __VLS_289({
                    ...{ 'onClick': {} },
                    type: "primary",
                    ...{ class: "full-btn" },
                }));
                const __VLS_291 = __VLS_290({
                    ...{ 'onClick': {} },
                    type: "primary",
                    ...{ class: "full-btn" },
                }, ...__VLS_functionalComponentArgsRest(__VLS_290));
                let __VLS_293;
                let __VLS_294;
                let __VLS_295;
                const __VLS_296 = {
                    onClick: (__VLS_ctx.confirmAgentShipment)
                };
                __VLS_292.slots.default;
                var __VLS_292;
            }
        }
        else {
            const __VLS_297 = {}.ElEmpty;
            /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
            // @ts-ignore
            const __VLS_298 = __VLS_asFunctionalComponent(__VLS_297, new __VLS_297({
                description: "对话后自动生成",
            }));
            const __VLS_299 = __VLS_298({
                description: "对话后自动生成",
            }, ...__VLS_functionalComponentArgsRest(__VLS_298));
        }
    }
    else if (__VLS_ctx.view === 'addresses') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "page-block" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        const __VLS_301 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_302 = __VLS_asFunctionalComponent(__VLS_301, new __VLS_301({
            ...{ 'onClick': {} },
            type: "primary",
        }));
        const __VLS_303 = __VLS_302({
            ...{ 'onClick': {} },
            type: "primary",
        }, ...__VLS_functionalComponentArgsRest(__VLS_302));
        let __VLS_305;
        let __VLS_306;
        let __VLS_307;
        const __VLS_308 = {
            onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.loggedIn))
                    return;
                if (!!(__VLS_ctx.user?.role === 'COURIER'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                    return;
                if (!!(__VLS_ctx.view === 'shipments'))
                    return;
                if (!!(__VLS_ctx.view === 'create'))
                    return;
                if (!!(__VLS_ctx.view === 'agent'))
                    return;
                if (!(__VLS_ctx.view === 'addresses'))
                    return;
                __VLS_ctx.addressDialog = true;
            }
        };
        __VLS_304.slots.default;
        const __VLS_309 = {}.Plus;
        /** @type {[typeof __VLS_components.Plus, ]} */ ;
        // @ts-ignore
        const __VLS_310 = __VLS_asFunctionalComponent(__VLS_309, new __VLS_309({}));
        const __VLS_311 = __VLS_310({}, ...__VLS_functionalComponentArgsRest(__VLS_310));
        var __VLS_304;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "address-grid" },
        });
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.addresses))) {
            const __VLS_313 = {}.ElCard;
            /** @type {[typeof __VLS_components.ElCard, typeof __VLS_components.elCard, typeof __VLS_components.ElCard, typeof __VLS_components.elCard, ]} */ ;
            // @ts-ignore
            const __VLS_314 = __VLS_asFunctionalComponent(__VLS_313, new __VLS_313({
                key: (a.id),
                shadow: "never",
                ...{ class: "address-card" },
            }));
            const __VLS_315 = __VLS_314({
                key: (a.id),
                shadow: "never",
                ...{ class: "address-card" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_314));
            __VLS_316.slots.default;
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "address-label" },
            });
            (a.label || '常用地址');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (a.recipient_name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (a.phone);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (a.detail);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (a.district_code);
            var __VLS_316;
        }
    }
    else if (__VLS_ctx.view === 'notifications') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "page-block" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "notice-list" },
        });
        for (const [n] of __VLS_getVForSourceType((__VLS_ctx.notifications))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.loggedIn))
                            return;
                        if (!!(__VLS_ctx.user?.role === 'COURIER'))
                            return;
                        if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                            return;
                        if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                            return;
                        if (!!(__VLS_ctx.view === 'shipments'))
                            return;
                        if (!!(__VLS_ctx.view === 'create'))
                            return;
                        if (!!(__VLS_ctx.view === 'agent'))
                            return;
                        if (!!(__VLS_ctx.view === 'addresses'))
                            return;
                        if (!(__VLS_ctx.view === 'notifications'))
                            return;
                        __VLS_ctx.readNotice(n);
                    } },
                key: (n.id),
                ...{ class: (['notice', { unread: n.status !== 'READ' }]) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "notice-dot" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (n.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (n.content);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.time, __VLS_intrinsicElements.time)({});
            (new Date(n.created_at).toLocaleString('zh-CN'));
        }
        if (!__VLS_ctx.notifications.length) {
            const __VLS_317 = {}.ElEmpty;
            /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
            // @ts-ignore
            const __VLS_318 = __VLS_asFunctionalComponent(__VLS_317, new __VLS_317({
                description: "暂无消息",
            }));
            const __VLS_319 = __VLS_318({
                description: "暂无消息",
            }, ...__VLS_functionalComponentArgsRest(__VLS_318));
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "page-block" },
        });
        const __VLS_321 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_322 = __VLS_asFunctionalComponent(__VLS_321, new __VLS_321({
            ...{ 'onClick': {} },
            text: true,
        }));
        const __VLS_323 = __VLS_322({
            ...{ 'onClick': {} },
            text: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_322));
        let __VLS_325;
        let __VLS_326;
        let __VLS_327;
        const __VLS_328 = {
            onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.loggedIn))
                    return;
                if (!!(__VLS_ctx.user?.role === 'COURIER'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                    return;
                if (!!(__VLS_ctx.view === 'shipments'))
                    return;
                if (!!(__VLS_ctx.view === 'create'))
                    return;
                if (!!(__VLS_ctx.view === 'agent'))
                    return;
                if (!!(__VLS_ctx.view === 'addresses'))
                    return;
                if (!!(__VLS_ctx.view === 'notifications'))
                    return;
                __VLS_ctx.view = 'shipments';
            }
        };
        __VLS_324.slots.default;
        var __VLS_324;
        if (__VLS_ctx.selected) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "detail-layout" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "detail-main" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "section-kicker" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.selected.shipment?.shipment_no || __VLS_ctx.selected.shipment_no);
            const __VLS_329 = {}.ElTag;
            /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
            // @ts-ignore
            const __VLS_330 = __VLS_asFunctionalComponent(__VLS_329, new __VLS_329({
                type: "primary",
            }));
            const __VLS_331 = __VLS_330({
                type: "primary",
            }, ...__VLS_functionalComponentArgsRest(__VLS_330));
            __VLS_332.slots.default;
            (__VLS_ctx.statusMap[__VLS_ctx.selected.shipment?.status || __VLS_ctx.selected.status] || __VLS_ctx.selected.shipment?.status);
            var __VLS_332;
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "timeline" },
            });
            for (const [event] of __VLS_getVForSourceType((__VLS_ctx.timeline))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (event.id),
                    ...{ class: "timeline-item" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "timeline-dot" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (event.message);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.time, __VLS_intrinsicElements.time)({});
                (new Date(event.occurred_at).toLocaleString('zh-CN'));
            }
            if (!__VLS_ctx.timeline.length) {
                const __VLS_333 = {}.ElEmpty;
                /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
                // @ts-ignore
                const __VLS_334 = __VLS_asFunctionalComponent(__VLS_333, new __VLS_333({
                    description: "暂无轨迹",
                }));
                const __VLS_335 = __VLS_334({
                    description: "暂无轨迹",
                }, ...__VLS_functionalComponentArgsRest(__VLS_334));
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
                ...{ class: "detail-side" },
            });
            const __VLS_337 = {}.ElCard;
            /** @type {[typeof __VLS_components.ElCard, typeof __VLS_components.elCard, typeof __VLS_components.ElCard, typeof __VLS_components.elCard, ]} */ ;
            // @ts-ignore
            const __VLS_338 = __VLS_asFunctionalComponent(__VLS_337, new __VLS_337({
                shadow: "never",
            }));
            const __VLS_339 = __VLS_338({
                shadow: "never",
            }, ...__VLS_functionalComponentArgsRest(__VLS_338));
            __VLS_340.slots.default;
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            (__VLS_ctx.statusMap[__VLS_ctx.selected.shipment?.status || __VLS_ctx.selected.status] || '处理中');
            const __VLS_341 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_342 = __VLS_asFunctionalComponent(__VLS_341, new __VLS_341({
                type: "primary",
                ...{ class: "full-btn" },
            }));
            const __VLS_343 = __VLS_342({
                type: "primary",
                ...{ class: "full-btn" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_342));
            __VLS_344.slots.default;
            var __VLS_344;
            var __VLS_340;
        }
    }
    const __VLS_345 = {}.ElDialog;
    /** @type {[typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, ]} */ ;
    // @ts-ignore
    const __VLS_346 = __VLS_asFunctionalComponent(__VLS_345, new __VLS_345({
        modelValue: (__VLS_ctx.addressDialog),
        title: "新增地址",
        width: "480px",
    }));
    const __VLS_347 = __VLS_346({
        modelValue: (__VLS_ctx.addressDialog),
        title: "新增地址",
        width: "480px",
    }, ...__VLS_functionalComponentArgsRest(__VLS_346));
    __VLS_348.slots.default;
    const __VLS_349 = {}.ElForm;
    /** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
    // @ts-ignore
    const __VLS_350 = __VLS_asFunctionalComponent(__VLS_349, new __VLS_349({
        labelPosition: "top",
    }));
    const __VLS_351 = __VLS_350({
        labelPosition: "top",
    }, ...__VLS_functionalComponentArgsRest(__VLS_350));
    __VLS_352.slots.default;
    const __VLS_353 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_354 = __VLS_asFunctionalComponent(__VLS_353, new __VLS_353({
        label: "标签",
    }));
    const __VLS_355 = __VLS_354({
        label: "标签",
    }, ...__VLS_functionalComponentArgsRest(__VLS_354));
    __VLS_356.slots.default;
    const __VLS_357 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_358 = __VLS_asFunctionalComponent(__VLS_357, new __VLS_357({
        modelValue: (__VLS_ctx.addressForm.label),
    }));
    const __VLS_359 = __VLS_358({
        modelValue: (__VLS_ctx.addressForm.label),
    }, ...__VLS_functionalComponentArgsRest(__VLS_358));
    var __VLS_356;
    const __VLS_361 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_362 = __VLS_asFunctionalComponent(__VLS_361, new __VLS_361({
        label: "收件人",
    }));
    const __VLS_363 = __VLS_362({
        label: "收件人",
    }, ...__VLS_functionalComponentArgsRest(__VLS_362));
    __VLS_364.slots.default;
    const __VLS_365 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_366 = __VLS_asFunctionalComponent(__VLS_365, new __VLS_365({
        modelValue: (__VLS_ctx.addressForm.recipient_name),
    }));
    const __VLS_367 = __VLS_366({
        modelValue: (__VLS_ctx.addressForm.recipient_name),
    }, ...__VLS_functionalComponentArgsRest(__VLS_366));
    var __VLS_364;
    const __VLS_369 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_370 = __VLS_asFunctionalComponent(__VLS_369, new __VLS_369({
        label: "手机号",
    }));
    const __VLS_371 = __VLS_370({
        label: "手机号",
    }, ...__VLS_functionalComponentArgsRest(__VLS_370));
    __VLS_372.slots.default;
    const __VLS_373 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_374 = __VLS_asFunctionalComponent(__VLS_373, new __VLS_373({
        modelValue: (__VLS_ctx.addressForm.phone),
    }));
    const __VLS_375 = __VLS_374({
        modelValue: (__VLS_ctx.addressForm.phone),
    }, ...__VLS_functionalComponentArgsRest(__VLS_374));
    var __VLS_372;
    const __VLS_377 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_378 = __VLS_asFunctionalComponent(__VLS_377, new __VLS_377({
        label: "行政区编码",
    }));
    const __VLS_379 = __VLS_378({
        label: "行政区编码",
    }, ...__VLS_functionalComponentArgsRest(__VLS_378));
    __VLS_380.slots.default;
    const __VLS_381 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_382 = __VLS_asFunctionalComponent(__VLS_381, new __VLS_381({
        modelValue: (__VLS_ctx.addressForm.district_code),
    }));
    const __VLS_383 = __VLS_382({
        modelValue: (__VLS_ctx.addressForm.district_code),
    }, ...__VLS_functionalComponentArgsRest(__VLS_382));
    var __VLS_380;
    const __VLS_385 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_386 = __VLS_asFunctionalComponent(__VLS_385, new __VLS_385({
        label: "详细地址",
    }));
    const __VLS_387 = __VLS_386({
        label: "详细地址",
    }, ...__VLS_functionalComponentArgsRest(__VLS_386));
    __VLS_388.slots.default;
    const __VLS_389 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_390 = __VLS_asFunctionalComponent(__VLS_389, new __VLS_389({
        modelValue: (__VLS_ctx.addressForm.detail),
    }));
    const __VLS_391 = __VLS_390({
        modelValue: (__VLS_ctx.addressForm.detail),
    }, ...__VLS_functionalComponentArgsRest(__VLS_390));
    var __VLS_388;
    var __VLS_352;
    {
        const { footer: __VLS_thisSlot } = __VLS_348.slots;
        const __VLS_393 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_394 = __VLS_asFunctionalComponent(__VLS_393, new __VLS_393({
            ...{ 'onClick': {} },
        }));
        const __VLS_395 = __VLS_394({
            ...{ 'onClick': {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_394));
        let __VLS_397;
        let __VLS_398;
        let __VLS_399;
        const __VLS_400 = {
            onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.loggedIn))
                    return;
                if (!!(__VLS_ctx.user?.role === 'COURIER'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'OPERATIONS_ADMIN'))
                    return;
                if (!!(__VLS_ctx.user?.role === 'SYSTEM_ADMIN'))
                    return;
                __VLS_ctx.addressDialog = false;
            }
        };
        __VLS_396.slots.default;
        var __VLS_396;
        const __VLS_401 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_402 = __VLS_asFunctionalComponent(__VLS_401, new __VLS_401({
            ...{ 'onClick': {} },
            type: "primary",
        }));
        const __VLS_403 = __VLS_402({
            ...{ 'onClick': {} },
            type: "primary",
        }, ...__VLS_functionalComponentArgsRest(__VLS_402));
        let __VLS_405;
        let __VLS_406;
        let __VLS_407;
        const __VLS_408 = {
            onClick: (__VLS_ctx.saveAddress)
        };
        __VLS_404.slots.default;
        var __VLS_404;
    }
    var __VLS_348;
}
/** @type {__VLS_StyleScopedClasses['login-page']} */ ;
/** @type {__VLS_StyleScopedClasses['login-art']} */ ;
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
/** @type {__VLS_StyleScopedClasses['route-line']} */ ;
/** @type {__VLS_StyleScopedClasses['login-card']} */ ;
/** @type {__VLS_StyleScopedClasses['brand-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['muted']} */ ;
/** @type {__VLS_StyleScopedClasses['full-input']} */ ;
/** @type {__VLS_StyleScopedClasses['login-option']} */ ;
/** @type {__VLS_StyleScopedClasses['full-btn']} */ ;
/** @type {__VLS_StyleScopedClasses['login-note']} */ ;
/** @type {__VLS_StyleScopedClasses['app-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar']} */ ;
/** @type {__VLS_StyleScopedClasses['logo']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-label']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar-foot']} */ ;
/** @type {__VLS_StyleScopedClasses['main']} */ ;
/** @type {__VLS_StyleScopedClasses['topbar']} */ ;
/** @type {__VLS_StyleScopedClasses['crumb']} */ ;
/** @type {__VLS_StyleScopedClasses['top-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['user-name']} */ ;
/** @type {__VLS_StyleScopedClasses['content']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['stat-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['shipment-table']} */ ;
/** @type {__VLS_StyleScopedClasses['shipment-no']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['narrow']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['form-card']} */ ;
/** @type {__VLS_StyleScopedClasses['form-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['agent-page']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-list']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-item']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-window']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-body']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-intro']} */ ;
/** @type {__VLS_StyleScopedClasses['agent-orb']} */ ;
/** @type {__VLS_StyleScopedClasses['messages']} */ ;
/** @type {__VLS_StyleScopedClasses['message']} */ ;
/** @type {__VLS_StyleScopedClasses['message-bubble']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-composer']} */ ;
/** @type {__VLS_StyleScopedClasses['chat-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['agent-orb']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-content']} */ ;
/** @type {__VLS_StyleScopedClasses['full-btn']} */ ;
/** @type {__VLS_StyleScopedClasses['full-btn']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['address-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['address-card']} */ ;
/** @type {__VLS_StyleScopedClasses['address-label']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['notice-list']} */ ;
/** @type {__VLS_StyleScopedClasses['unread']} */ ;
/** @type {__VLS_StyleScopedClasses['notice']} */ ;
/** @type {__VLS_StyleScopedClasses['notice-dot']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['detail-layout']} */ ;
/** @type {__VLS_StyleScopedClasses['detail-main']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['timeline']} */ ;
/** @type {__VLS_StyleScopedClasses['timeline-item']} */ ;
/** @type {__VLS_StyleScopedClasses['timeline-dot']} */ ;
/** @type {__VLS_StyleScopedClasses['detail-side']} */ ;
/** @type {__VLS_StyleScopedClasses['full-btn']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            ArrowRight: ArrowRight,
            ChatDotRound: ChatDotRound,
            Plus: Plus,
            Search: Search,
            Setting: Setting,
            CourierWorkspace: CourierWorkspace,
            OperationsWorkspace: OperationsWorkspace,
            SystemAdminWorkspace: SystemAdminWorkspace,
            loggedIn: loggedIn,
            user: user,
            view: view,
            loading: loading,
            shipments: shipments,
            total: total,
            addresses: addresses,
            notifications: notifications,
            selected: selected,
            timeline: timeline,
            page: page,
            query: query,
            loginForm: loginForm,
            loginAccounts: loginAccounts,
            addressDialog: addressDialog,
            addressForm: addressForm,
            shipmentForm: shipmentForm,
            conversations: conversations,
            activeConversation: activeConversation,
            agentMessages: agentMessages,
            agentDraft: agentDraft,
            agentInput: agentInput,
            agentSending: agentSending,
            statusMap: statusMap,
            nav: nav,
            loadData: loadData,
            doLogin: doLogin,
            logout: logout,
            openShipment: openShipment,
            saveAddress: saveAddress,
            submitShipment: submitShipment,
            openConversation: openConversation,
            sendMessage: sendMessage,
            validateDraft: validateDraft,
            confirmAgentShipment: confirmAgentShipment,
            readNotice: readNotice,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
