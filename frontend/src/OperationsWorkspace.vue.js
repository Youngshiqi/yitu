import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Clock, Connection, DataAnalysis, Refresh, Setting, TrendCharts, Warning } from '@element-plus/icons-vue';
import { applyExceptionAction, arriveDestination, listCourierTasks, listExceptions, listShipments, listSlaInstances, resolveException } from './api';
const __VLS_props = defineProps();
const __VLS_emit = defineEmits();
const view = ref('overview');
const loading = ref(false);
const shipments = ref([]);
const tasks = ref([]);
const cases = ref([]);
const totalShipments = ref(0);
const query = ref('');
const exceptionTab = ref('active');
const selected = ref(null);
const actionDialog = ref(false);
const actionMode = ref('start-processing');
const actionReason = ref('');
const resolutionCode = ref('INFORMATION_CORRECTED');
const slaDialog = ref(false);
const slaRows = ref([]);
const nav = [{ id: 'overview', label: '运营概览', icon: DataAnalysis }, { id: 'exceptions', label: '异常工单', icon: Warning }, { id: 'fulfillment', label: '履约调度', icon: Connection }, { id: 'sla', label: 'SLA 监控', icon: TrendCharts }];
const activeCases = computed(() => cases.value.filter(item => !['RESOLVED', 'CLOSED'].includes(item.status)));
const visibleCases = computed(() => (exceptionTab.value === 'all' ? cases.value : activeCases.value).filter(item => !query.value || item.shipment_id.includes(query.value) || item.description.includes(query.value)));
const tasksInTransit = computed(() => tasks.value.filter(task => task.status === 'ACCEPTED').length);
async function loadData() {
    loading.value = true;
    try {
        const [shipmentResult, taskResult, caseResult] = await Promise.all([listShipments({ limit: 50, offset: 0 }), listCourierTasks(), listExceptions({ limit: 100, offset: 0 })]);
        shipments.value = shipmentResult.items || [];
        totalShipments.value = shipmentResult.total || 0;
        tasks.value = taskResult;
        cases.value = caseResult.items;
    }
    catch {
        ElMessage.error('运营数据加载失败，请确认后端服务已启动');
    }
    finally {
        loading.value = false;
    }
}
function openAction(item, mode) { selected.value = item; actionMode.value = mode; actionReason.value = ''; resolutionCode.value = 'INFORMATION_CORRECTED'; actionDialog.value = true; }
async function submitAction() {
    if (!selected.value)
        return;
    if (actionMode.value === 'resolve' && !actionReason.value.trim()) {
        ElMessage.warning('请填写解决说明');
        return;
    }
    try {
        if (actionMode.value === 'resolve')
            await resolveException(selected.value.id, resolutionCode.value, actionReason.value.trim());
        else
            await applyExceptionAction(selected.value.id, actionMode.value, actionReason.value.trim());
        actionDialog.value = false;
        ElMessage.success('工单状态已更新');
        await loadData();
    }
    catch (error) {
        ElMessage.error(error.response?.data?.message || '工单状态无法推进');
    }
}
async function confirmArrival(shipment) { try {
    await arriveDestination(shipment.id);
    ElMessage.success('已确认目的地到达');
    await loadData();
}
catch (error) {
    ElMessage.error(error.response?.data?.message || '该运单暂不能确认到达');
} }
async function showSla(shipment) { try {
    slaRows.value = await listSlaInstances(shipment.id);
    slaDialog.value = true;
}
catch {
    ElMessage.error('该运单暂无可查看的 SLA 实例');
} }
function severityType(severity) { return severity === 'CRITICAL' || severity === 'HIGH' ? 'danger' : severity === 'MEDIUM' ? 'warning' : 'info'; }
onMounted(loadData);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "app-shell operations-shell" },
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
                __VLS_ctx.view = item.id;
            } },
        key: (item.id),
        ...{ class: ({ active: __VLS_ctx.view === item.id }) },
    });
    const __VLS_0 = ((item.icon));
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent(__VLS_0, new __VLS_0({}));
    const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (item.label);
    if (item.id === 'exceptions' && __VLS_ctx.activeCases.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.activeCases.length);
    }
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "ops-status" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "sidebar-foot" },
});
const __VLS_4 = {}.ElButton;
/** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
// @ts-ignore
const __VLS_5 = __VLS_asFunctionalComponent(__VLS_4, new __VLS_4({
    ...{ 'onClick': {} },
    text: true,
}));
const __VLS_6 = __VLS_5({
    ...{ 'onClick': {} },
    text: true,
}, ...__VLS_functionalComponentArgsRest(__VLS_5));
let __VLS_8;
let __VLS_9;
let __VLS_10;
const __VLS_11 = {
    onClick: (...[$event]) => {
        __VLS_ctx.$emit('logout');
    }
};
__VLS_7.slots.default;
const __VLS_12 = {}.Setting;
/** @type {[typeof __VLS_components.Setting, ]} */ ;
// @ts-ignore
const __VLS_13 = __VLS_asFunctionalComponent(__VLS_12, new __VLS_12({}));
const __VLS_14 = __VLS_13({}, ...__VLS_functionalComponentArgsRest(__VLS_13));
var __VLS_7;
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
(__VLS_ctx.nav.find(item => item.id === __VLS_ctx.view)?.label);
__VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
(__VLS_ctx.nav.find(item => item.id === __VLS_ctx.view)?.label);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "top-actions" },
});
const __VLS_16 = {}.ElInput;
/** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
// @ts-ignore
const __VLS_17 = __VLS_asFunctionalComponent(__VLS_16, new __VLS_16({
    modelValue: (__VLS_ctx.query),
    placeholder: "搜索运单或异常说明",
    clearable: true,
}));
const __VLS_18 = __VLS_17({
    modelValue: (__VLS_ctx.query),
    placeholder: "搜索运单或异常说明",
    clearable: true,
}, ...__VLS_functionalComponentArgsRest(__VLS_17));
const __VLS_20 = {}.ElButton;
/** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
// @ts-ignore
const __VLS_21 = __VLS_asFunctionalComponent(__VLS_20, new __VLS_20({
    ...{ 'onClick': {} },
    circle: true,
    icon: (__VLS_ctx.Refresh),
}));
const __VLS_22 = __VLS_21({
    ...{ 'onClick': {} },
    circle: true,
    icon: (__VLS_ctx.Refresh),
}, ...__VLS_functionalComponentArgsRest(__VLS_21));
let __VLS_24;
let __VLS_25;
let __VLS_26;
const __VLS_27 = {
    onClick: (__VLS_ctx.loadData)
};
var __VLS_23;
const __VLS_28 = {}.ElAvatar;
/** @type {[typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, ]} */ ;
// @ts-ignore
const __VLS_29 = __VLS_asFunctionalComponent(__VLS_28, new __VLS_28({
    size: (34),
}));
const __VLS_30 = __VLS_29({
    size: (34),
}, ...__VLS_functionalComponentArgsRest(__VLS_29));
__VLS_31.slots.default;
(__VLS_ctx.user.display_name.slice(0, 1));
var __VLS_31;
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "user-name" },
});
(__VLS_ctx.user.display_name);
__VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
    ...{ class: "content" },
});
__VLS_asFunctionalDirective(__VLS_directives.vLoading)(null, { ...__VLS_directiveBindingRestFields, value: (__VLS_ctx.loading) }, null, null);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "page-block" },
});
if (__VLS_ctx.view === 'overview') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "ops-hero" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "control-glyph" },
    });
    const __VLS_32 = {}.DataAnalysis;
    /** @type {[typeof __VLS_components.DataAnalysis, ]} */ ;
    // @ts-ignore
    const __VLS_33 = __VLS_asFunctionalComponent(__VLS_32, new __VLS_32({}));
    const __VLS_34 = __VLS_33({}, ...__VLS_functionalComponentArgsRest(__VLS_33));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "ops-kpi-grid" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.totalShipments);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.tasksInTransit);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.activeCases.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.activeCases.filter(item => item.blocks_fulfillment).length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head compact" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    const __VLS_36 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_37 = __VLS_asFunctionalComponent(__VLS_36, new __VLS_36({
        ...{ 'onClick': {} },
        text: true,
        type: "primary",
    }));
    const __VLS_38 = __VLS_37({
        ...{ 'onClick': {} },
        text: true,
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_37));
    let __VLS_40;
    let __VLS_41;
    let __VLS_42;
    const __VLS_43 = {
        onClick: (...[$event]) => {
            if (!(__VLS_ctx.view === 'overview'))
                return;
            __VLS_ctx.view = 'exceptions';
        }
    };
    __VLS_39.slots.default;
    var __VLS_39;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "attention-list" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.activeCases.slice(0, 4)))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (item.id),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "attention-mark" },
        });
        const __VLS_44 = {}.Warning;
        /** @type {[typeof __VLS_components.Warning, ]} */ ;
        // @ts-ignore
        const __VLS_45 = __VLS_asFunctionalComponent(__VLS_44, new __VLS_44({}));
        const __VLS_46 = __VLS_45({}, ...__VLS_functionalComponentArgsRest(__VLS_45));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "attention-title" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (item.case_type);
        const __VLS_48 = {}.ElTag;
        /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
        // @ts-ignore
        const __VLS_49 = __VLS_asFunctionalComponent(__VLS_48, new __VLS_48({
            size: "small",
            type: (__VLS_ctx.severityType(item.severity)),
        }));
        const __VLS_50 = __VLS_49({
            size: "small",
            type: (__VLS_ctx.severityType(item.severity)),
        }, ...__VLS_functionalComponentArgsRest(__VLS_49));
        __VLS_51.slots.default;
        (item.severity);
        var __VLS_51;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (item.description);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (item.shipment_id);
        (new Date(item.opened_at).toLocaleString('zh-CN'));
        const __VLS_52 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_53 = __VLS_asFunctionalComponent(__VLS_52, new __VLS_52({
            ...{ 'onClick': {} },
        }));
        const __VLS_54 = __VLS_53({
            ...{ 'onClick': {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_53));
        let __VLS_56;
        let __VLS_57;
        let __VLS_58;
        const __VLS_59 = {
            onClick: (...[$event]) => {
                if (!(__VLS_ctx.view === 'overview'))
                    return;
                __VLS_ctx.openAction(item, item.status === 'OPEN' || item.status === 'ASSIGNED' ? 'start-processing' : 'resolve');
            }
        };
        __VLS_55.slots.default;
        var __VLS_55;
    }
    if (!__VLS_ctx.activeCases.length) {
        const __VLS_60 = {}.ElEmpty;
        /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
        // @ts-ignore
        const __VLS_61 = __VLS_asFunctionalComponent(__VLS_60, new __VLS_60({
            description: "当前无待处理异常",
        }));
        const __VLS_62 = __VLS_61({
            description: "当前无待处理异常",
        }, ...__VLS_functionalComponentArgsRest(__VLS_61));
    }
}
else if (__VLS_ctx.view === 'exceptions') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    const __VLS_64 = {}.ElSegmented;
    /** @type {[typeof __VLS_components.ElSegmented, typeof __VLS_components.elSegmented, ]} */ ;
    // @ts-ignore
    const __VLS_65 = __VLS_asFunctionalComponent(__VLS_64, new __VLS_64({
        modelValue: (__VLS_ctx.exceptionTab),
        options: ([{ label: '待处理', value: 'active' }, { label: '全部', value: 'all' }]),
    }));
    const __VLS_66 = __VLS_65({
        modelValue: (__VLS_ctx.exceptionTab),
        options: ([{ label: '待处理', value: 'active' }, { label: '全部', value: 'all' }]),
    }, ...__VLS_functionalComponentArgsRest(__VLS_65));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "exception-grid" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.visibleCases))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (item.id),
            ...{ class: "exception-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "exception-card-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (item.case_type);
        const __VLS_68 = {}.ElTag;
        /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
        // @ts-ignore
        const __VLS_69 = __VLS_asFunctionalComponent(__VLS_68, new __VLS_68({
            type: (__VLS_ctx.severityType(item.severity)),
        }));
        const __VLS_70 = __VLS_69({
            type: (__VLS_ctx.severityType(item.severity)),
        }, ...__VLS_functionalComponentArgsRest(__VLS_69));
        __VLS_71.slots.default;
        (item.severity);
        var __VLS_71;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        (item.description);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (item.shipment_id);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "case-footer" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (item.status);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (item.blocks_fulfillment ? '已阻断' : '未阻断');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "case-actions" },
        });
        if (['OPEN', 'ASSIGNED'].includes(item.status)) {
            const __VLS_72 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_73 = __VLS_asFunctionalComponent(__VLS_72, new __VLS_72({
                ...{ 'onClick': {} },
                type: "primary",
            }));
            const __VLS_74 = __VLS_73({
                ...{ 'onClick': {} },
                type: "primary",
            }, ...__VLS_functionalComponentArgsRest(__VLS_73));
            let __VLS_76;
            let __VLS_77;
            let __VLS_78;
            const __VLS_79 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!(__VLS_ctx.view === 'exceptions'))
                        return;
                    if (!(['OPEN', 'ASSIGNED'].includes(item.status)))
                        return;
                    __VLS_ctx.openAction(item, 'start-processing');
                }
            };
            __VLS_75.slots.default;
            var __VLS_75;
        }
        if (item.status === 'PROCESSING') {
            const __VLS_80 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_81 = __VLS_asFunctionalComponent(__VLS_80, new __VLS_80({
                ...{ 'onClick': {} },
            }));
            const __VLS_82 = __VLS_81({
                ...{ 'onClick': {} },
            }, ...__VLS_functionalComponentArgsRest(__VLS_81));
            let __VLS_84;
            let __VLS_85;
            let __VLS_86;
            const __VLS_87 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!(__VLS_ctx.view === 'exceptions'))
                        return;
                    if (!(item.status === 'PROCESSING'))
                        return;
                    __VLS_ctx.openAction(item, 'wait-for-customer');
                }
            };
            __VLS_83.slots.default;
            var __VLS_83;
        }
        if (item.status === 'WAITING_FOR_CUSTOMER') {
            const __VLS_88 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_89 = __VLS_asFunctionalComponent(__VLS_88, new __VLS_88({
                ...{ 'onClick': {} },
            }));
            const __VLS_90 = __VLS_89({
                ...{ 'onClick': {} },
            }, ...__VLS_functionalComponentArgsRest(__VLS_89));
            let __VLS_92;
            let __VLS_93;
            let __VLS_94;
            const __VLS_95 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!(__VLS_ctx.view === 'exceptions'))
                        return;
                    if (!(item.status === 'WAITING_FOR_CUSTOMER'))
                        return;
                    __VLS_ctx.openAction(item, 'resume-processing');
                }
            };
            __VLS_91.slots.default;
            var __VLS_91;
        }
        if (['PROCESSING', 'WAITING_FOR_CUSTOMER'].includes(item.status)) {
            const __VLS_96 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_97 = __VLS_asFunctionalComponent(__VLS_96, new __VLS_96({
                ...{ 'onClick': {} },
                type: "success",
            }));
            const __VLS_98 = __VLS_97({
                ...{ 'onClick': {} },
                type: "success",
            }, ...__VLS_functionalComponentArgsRest(__VLS_97));
            let __VLS_100;
            let __VLS_101;
            let __VLS_102;
            const __VLS_103 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!(__VLS_ctx.view === 'exceptions'))
                        return;
                    if (!(['PROCESSING', 'WAITING_FOR_CUSTOMER'].includes(item.status)))
                        return;
                    __VLS_ctx.openAction(item, 'resolve');
                }
            };
            __VLS_99.slots.default;
            var __VLS_99;
        }
        if (item.status === 'RESOLVED') {
            const __VLS_104 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_105 = __VLS_asFunctionalComponent(__VLS_104, new __VLS_104({
                ...{ 'onClick': {} },
            }));
            const __VLS_106 = __VLS_105({
                ...{ 'onClick': {} },
            }, ...__VLS_functionalComponentArgsRest(__VLS_105));
            let __VLS_108;
            let __VLS_109;
            let __VLS_110;
            const __VLS_111 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!(__VLS_ctx.view === 'exceptions'))
                        return;
                    if (!(item.status === 'RESOLVED'))
                        return;
                    __VLS_ctx.openAction(item, 'close');
                }
            };
            __VLS_107.slots.default;
            var __VLS_107;
        }
    }
    if (!__VLS_ctx.visibleCases.length) {
        const __VLS_112 = {}.ElEmpty;
        /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
        // @ts-ignore
        const __VLS_113 = __VLS_asFunctionalComponent(__VLS_112, new __VLS_112({
            description: "没有匹配的异常工单",
        }));
        const __VLS_114 = __VLS_113({
            description: "没有匹配的异常工单",
        }, ...__VLS_functionalComponentArgsRest(__VLS_113));
    }
}
else if (__VLS_ctx.view === 'fulfillment') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    const __VLS_116 = {}.ElTable;
    /** @type {[typeof __VLS_components.ElTable, typeof __VLS_components.elTable, typeof __VLS_components.ElTable, typeof __VLS_components.elTable, ]} */ ;
    // @ts-ignore
    const __VLS_117 = __VLS_asFunctionalComponent(__VLS_116, new __VLS_116({
        data: (__VLS_ctx.shipments.filter(item => !__VLS_ctx.query || item.shipment_no.includes(__VLS_ctx.query) || item.id.includes(__VLS_ctx.query))),
        ...{ class: "shipment-table" },
    }));
    const __VLS_118 = __VLS_117({
        data: (__VLS_ctx.shipments.filter(item => !__VLS_ctx.query || item.shipment_no.includes(__VLS_ctx.query) || item.id.includes(__VLS_ctx.query))),
        ...{ class: "shipment-table" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_117));
    __VLS_119.slots.default;
    const __VLS_120 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_121 = __VLS_asFunctionalComponent(__VLS_120, new __VLS_120({
        prop: "shipment_no",
        label: "运单号",
        minWidth: "180",
    }));
    const __VLS_122 = __VLS_121({
        prop: "shipment_no",
        label: "运单号",
        minWidth: "180",
    }, ...__VLS_functionalComponentArgsRest(__VLS_121));
    __VLS_123.slots.default;
    {
        const { default: __VLS_thisSlot } = __VLS_123.slots;
        const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "shipment-no" },
        });
        (row.shipment_no);
    }
    var __VLS_123;
    const __VLS_124 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_125 = __VLS_asFunctionalComponent(__VLS_124, new __VLS_124({
        prop: "status",
        label: "当前状态",
    }));
    const __VLS_126 = __VLS_125({
        prop: "status",
        label: "当前状态",
    }, ...__VLS_functionalComponentArgsRest(__VLS_125));
    const __VLS_128 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_129 = __VLS_asFunctionalComponent(__VLS_128, new __VLS_128({
        label: "SLA",
        width: "120",
    }));
    const __VLS_130 = __VLS_129({
        label: "SLA",
        width: "120",
    }, ...__VLS_functionalComponentArgsRest(__VLS_129));
    __VLS_131.slots.default;
    {
        const { default: __VLS_thisSlot } = __VLS_131.slots;
        const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
        const __VLS_132 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_133 = __VLS_asFunctionalComponent(__VLS_132, new __VLS_132({
            ...{ 'onClick': {} },
            text: true,
        }));
        const __VLS_134 = __VLS_133({
            ...{ 'onClick': {} },
            text: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_133));
        let __VLS_136;
        let __VLS_137;
        let __VLS_138;
        const __VLS_139 = {
            onClick: (...[$event]) => {
                if (!!(__VLS_ctx.view === 'overview'))
                    return;
                if (!!(__VLS_ctx.view === 'exceptions'))
                    return;
                if (!(__VLS_ctx.view === 'fulfillment'))
                    return;
                __VLS_ctx.showSla(row);
            }
        };
        __VLS_135.slots.default;
        var __VLS_135;
    }
    var __VLS_131;
    const __VLS_140 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_141 = __VLS_asFunctionalComponent(__VLS_140, new __VLS_140({
        label: "运营动作",
        width: "180",
    }));
    const __VLS_142 = __VLS_141({
        label: "运营动作",
        width: "180",
    }, ...__VLS_functionalComponentArgsRest(__VLS_141));
    __VLS_143.slots.default;
    {
        const { default: __VLS_thisSlot } = __VLS_143.slots;
        const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
        const __VLS_144 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_145 = __VLS_asFunctionalComponent(__VLS_144, new __VLS_144({
            ...{ 'onClick': {} },
            type: "primary",
            plain: true,
            size: "small",
        }));
        const __VLS_146 = __VLS_145({
            ...{ 'onClick': {} },
            type: "primary",
            plain: true,
            size: "small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_145));
        let __VLS_148;
        let __VLS_149;
        let __VLS_150;
        const __VLS_151 = {
            onClick: (...[$event]) => {
                if (!!(__VLS_ctx.view === 'overview'))
                    return;
                if (!!(__VLS_ctx.view === 'exceptions'))
                    return;
                if (!(__VLS_ctx.view === 'fulfillment'))
                    return;
                __VLS_ctx.confirmArrival(row);
            }
        };
        __VLS_147.slots.default;
        var __VLS_147;
    }
    var __VLS_143;
    var __VLS_119;
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "sla-empty" },
    });
    const __VLS_152 = {}.Clock;
    /** @type {[typeof __VLS_components.Clock, ]} */ ;
    // @ts-ignore
    const __VLS_153 = __VLS_asFunctionalComponent(__VLS_152, new __VLS_152({}));
    const __VLS_154 = __VLS_153({}, ...__VLS_functionalComponentArgsRest(__VLS_153));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    const __VLS_156 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_157 = __VLS_asFunctionalComponent(__VLS_156, new __VLS_156({
        ...{ 'onClick': {} },
        type: "primary",
    }));
    const __VLS_158 = __VLS_157({
        ...{ 'onClick': {} },
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_157));
    let __VLS_160;
    let __VLS_161;
    let __VLS_162;
    const __VLS_163 = {
        onClick: (...[$event]) => {
            if (!!(__VLS_ctx.view === 'overview'))
                return;
            if (!!(__VLS_ctx.view === 'exceptions'))
                return;
            if (!!(__VLS_ctx.view === 'fulfillment'))
                return;
            __VLS_ctx.view = 'fulfillment';
        }
    };
    __VLS_159.slots.default;
    var __VLS_159;
}
const __VLS_164 = {}.ElDialog;
/** @type {[typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, ]} */ ;
// @ts-ignore
const __VLS_165 = __VLS_asFunctionalComponent(__VLS_164, new __VLS_164({
    modelValue: (__VLS_ctx.actionDialog),
    title: (__VLS_ctx.actionMode === 'resolve' ? '解决异常工单' : '更新工单状态'),
    width: "470px",
}));
const __VLS_166 = __VLS_165({
    modelValue: (__VLS_ctx.actionDialog),
    title: (__VLS_ctx.actionMode === 'resolve' ? '解决异常工单' : '更新工单状态'),
    width: "470px",
}, ...__VLS_functionalComponentArgsRest(__VLS_165));
__VLS_167.slots.default;
const __VLS_168 = {}.ElForm;
/** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
// @ts-ignore
const __VLS_169 = __VLS_asFunctionalComponent(__VLS_168, new __VLS_168({
    labelPosition: "top",
}));
const __VLS_170 = __VLS_169({
    labelPosition: "top",
}, ...__VLS_functionalComponentArgsRest(__VLS_169));
__VLS_171.slots.default;
if (__VLS_ctx.actionMode === 'resolve') {
    const __VLS_172 = {}.ElFormItem;
    /** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
    // @ts-ignore
    const __VLS_173 = __VLS_asFunctionalComponent(__VLS_172, new __VLS_172({
        label: "解决方式",
    }));
    const __VLS_174 = __VLS_173({
        label: "解决方式",
    }, ...__VLS_functionalComponentArgsRest(__VLS_173));
    __VLS_175.slots.default;
    const __VLS_176 = {}.ElSelect;
    /** @type {[typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, ]} */ ;
    // @ts-ignore
    const __VLS_177 = __VLS_asFunctionalComponent(__VLS_176, new __VLS_176({
        modelValue: (__VLS_ctx.resolutionCode),
    }));
    const __VLS_178 = __VLS_177({
        modelValue: (__VLS_ctx.resolutionCode),
    }, ...__VLS_functionalComponentArgsRest(__VLS_177));
    __VLS_179.slots.default;
    const __VLS_180 = {}.ElOption;
    /** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
    // @ts-ignore
    const __VLS_181 = __VLS_asFunctionalComponent(__VLS_180, new __VLS_180({
        label: "信息已更正",
        value: "INFORMATION_CORRECTED",
    }));
    const __VLS_182 = __VLS_181({
        label: "信息已更正",
        value: "INFORMATION_CORRECTED",
    }, ...__VLS_functionalComponentArgsRest(__VLS_181));
    const __VLS_184 = {}.ElOption;
    /** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
    // @ts-ignore
    const __VLS_185 = __VLS_asFunctionalComponent(__VLS_184, new __VLS_184({
        label: "无需后续动作",
        value: "NO_FURTHER_ACTION",
    }));
    const __VLS_186 = __VLS_185({
        label: "无需后续动作",
        value: "NO_FURTHER_ACTION",
    }, ...__VLS_functionalComponentArgsRest(__VLS_185));
    var __VLS_179;
    var __VLS_175;
}
const __VLS_188 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_189 = __VLS_asFunctionalComponent(__VLS_188, new __VLS_188({
    label: "处理说明",
}));
const __VLS_190 = __VLS_189({
    label: "处理说明",
}, ...__VLS_functionalComponentArgsRest(__VLS_189));
__VLS_191.slots.default;
const __VLS_192 = {}.ElInput;
/** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
// @ts-ignore
const __VLS_193 = __VLS_asFunctionalComponent(__VLS_192, new __VLS_192({
    modelValue: (__VLS_ctx.actionReason),
    type: "textarea",
    rows: (4),
    placeholder: (__VLS_ctx.actionMode === 'resolve' ? '说明解决措施' : '可选：补充本次处理原因'),
}));
const __VLS_194 = __VLS_193({
    modelValue: (__VLS_ctx.actionReason),
    type: "textarea",
    rows: (4),
    placeholder: (__VLS_ctx.actionMode === 'resolve' ? '说明解决措施' : '可选：补充本次处理原因'),
}, ...__VLS_functionalComponentArgsRest(__VLS_193));
var __VLS_191;
var __VLS_171;
{
    const { footer: __VLS_thisSlot } = __VLS_167.slots;
    const __VLS_196 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_197 = __VLS_asFunctionalComponent(__VLS_196, new __VLS_196({
        ...{ 'onClick': {} },
    }));
    const __VLS_198 = __VLS_197({
        ...{ 'onClick': {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_197));
    let __VLS_200;
    let __VLS_201;
    let __VLS_202;
    const __VLS_203 = {
        onClick: (...[$event]) => {
            __VLS_ctx.actionDialog = false;
        }
    };
    __VLS_199.slots.default;
    var __VLS_199;
    const __VLS_204 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_205 = __VLS_asFunctionalComponent(__VLS_204, new __VLS_204({
        ...{ 'onClick': {} },
        type: "primary",
    }));
    const __VLS_206 = __VLS_205({
        ...{ 'onClick': {} },
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_205));
    let __VLS_208;
    let __VLS_209;
    let __VLS_210;
    const __VLS_211 = {
        onClick: (__VLS_ctx.submitAction)
    };
    __VLS_207.slots.default;
    var __VLS_207;
}
var __VLS_167;
const __VLS_212 = {}.ElDialog;
/** @type {[typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, ]} */ ;
// @ts-ignore
const __VLS_213 = __VLS_asFunctionalComponent(__VLS_212, new __VLS_212({
    modelValue: (__VLS_ctx.slaDialog),
    title: "运单 SLA",
    width: "620px",
}));
const __VLS_214 = __VLS_213({
    modelValue: (__VLS_ctx.slaDialog),
    title: "运单 SLA",
    width: "620px",
}, ...__VLS_functionalComponentArgsRest(__VLS_213));
__VLS_215.slots.default;
const __VLS_216 = {}.ElTable;
/** @type {[typeof __VLS_components.ElTable, typeof __VLS_components.elTable, typeof __VLS_components.ElTable, typeof __VLS_components.elTable, ]} */ ;
// @ts-ignore
const __VLS_217 = __VLS_asFunctionalComponent(__VLS_216, new __VLS_216({
    data: (__VLS_ctx.slaRows),
}));
const __VLS_218 = __VLS_217({
    data: (__VLS_ctx.slaRows),
}, ...__VLS_functionalComponentArgsRest(__VLS_217));
__VLS_219.slots.default;
const __VLS_220 = {}.ElTableColumn;
/** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
// @ts-ignore
const __VLS_221 = __VLS_asFunctionalComponent(__VLS_220, new __VLS_220({
    prop: "stage",
    label: "阶段",
}));
const __VLS_222 = __VLS_221({
    prop: "stage",
    label: "阶段",
}, ...__VLS_functionalComponentArgsRest(__VLS_221));
const __VLS_224 = {}.ElTableColumn;
/** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
// @ts-ignore
const __VLS_225 = __VLS_asFunctionalComponent(__VLS_224, new __VLS_224({
    prop: "status",
    label: "状态",
}));
const __VLS_226 = __VLS_225({
    prop: "status",
    label: "状态",
}, ...__VLS_functionalComponentArgsRest(__VLS_225));
const __VLS_228 = {}.ElTableColumn;
/** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
// @ts-ignore
const __VLS_229 = __VLS_asFunctionalComponent(__VLS_228, new __VLS_228({
    prop: "promised_delivery_at",
    label: "承诺时间",
}));
const __VLS_230 = __VLS_229({
    prop: "promised_delivery_at",
    label: "承诺时间",
}, ...__VLS_functionalComponentArgsRest(__VLS_229));
const __VLS_232 = {}.ElTableColumn;
/** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
// @ts-ignore
const __VLS_233 = __VLS_asFunctionalComponent(__VLS_232, new __VLS_232({
    prop: "eta_at",
    label: "预计时间",
}));
const __VLS_234 = __VLS_233({
    prop: "eta_at",
    label: "预计时间",
}, ...__VLS_functionalComponentArgsRest(__VLS_233));
const __VLS_236 = {}.ElTableColumn;
/** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
// @ts-ignore
const __VLS_237 = __VLS_asFunctionalComponent(__VLS_236, new __VLS_236({
    prop: "breached",
    label: "已违约",
}));
const __VLS_238 = __VLS_237({
    prop: "breached",
    label: "已违约",
}, ...__VLS_functionalComponentArgsRest(__VLS_237));
__VLS_239.slots.default;
{
    const { default: __VLS_thisSlot } = __VLS_239.slots;
    const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
    const __VLS_240 = {}.ElTag;
    /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
    // @ts-ignore
    const __VLS_241 = __VLS_asFunctionalComponent(__VLS_240, new __VLS_240({
        type: (row.breached ? 'danger' : 'success'),
    }));
    const __VLS_242 = __VLS_241({
        type: (row.breached ? 'danger' : 'success'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_241));
    __VLS_243.slots.default;
    (row.breached ? '是' : '否');
    var __VLS_243;
}
var __VLS_239;
var __VLS_219;
if (!__VLS_ctx.slaRows.length) {
    const __VLS_244 = {}.ElEmpty;
    /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
    // @ts-ignore
    const __VLS_245 = __VLS_asFunctionalComponent(__VLS_244, new __VLS_244({
        description: "该运单没有 SLA 实例",
    }));
    const __VLS_246 = __VLS_245({
        description: "该运单没有 SLA 实例",
    }, ...__VLS_functionalComponentArgsRest(__VLS_245));
}
var __VLS_215;
/** @type {__VLS_StyleScopedClasses['app-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['operations-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar']} */ ;
/** @type {__VLS_StyleScopedClasses['logo']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-label']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['ops-status']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar-foot']} */ ;
/** @type {__VLS_StyleScopedClasses['main']} */ ;
/** @type {__VLS_StyleScopedClasses['topbar']} */ ;
/** @type {__VLS_StyleScopedClasses['crumb']} */ ;
/** @type {__VLS_StyleScopedClasses['top-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['user-name']} */ ;
/** @type {__VLS_StyleScopedClasses['content']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['ops-hero']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['control-glyph']} */ ;
/** @type {__VLS_StyleScopedClasses['ops-kpi-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['compact']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['attention-list']} */ ;
/** @type {__VLS_StyleScopedClasses['attention-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['attention-title']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['exception-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['exception-card']} */ ;
/** @type {__VLS_StyleScopedClasses['exception-card-head']} */ ;
/** @type {__VLS_StyleScopedClasses['case-footer']} */ ;
/** @type {__VLS_StyleScopedClasses['case-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['shipment-table']} */ ;
/** @type {__VLS_StyleScopedClasses['shipment-no']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['sla-empty']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            Clock: Clock,
            DataAnalysis: DataAnalysis,
            Refresh: Refresh,
            Setting: Setting,
            Warning: Warning,
            view: view,
            loading: loading,
            shipments: shipments,
            totalShipments: totalShipments,
            query: query,
            exceptionTab: exceptionTab,
            actionDialog: actionDialog,
            actionMode: actionMode,
            actionReason: actionReason,
            resolutionCode: resolutionCode,
            slaDialog: slaDialog,
            slaRows: slaRows,
            nav: nav,
            activeCases: activeCases,
            visibleCases: visibleCases,
            tasksInTransit: tasksInTransit,
            loadData: loadData,
            openAction: openAction,
            submitAction: submitAction,
            confirmArrival: confirmArrival,
            showSla: showSla,
            severityType: severityType,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
    __typeProps: {},
});
; /* PartiallyEnd: #4569/main.vue */
