import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Bell, Box, Check, CircleCheck, Connection, Refresh, Setting, Van, Warning } from '@element-plus/icons-vue';
import { acceptCourierTask, confirmCourierDelivery, confirmCourierPickup, listCourierTasks, reportException, startCourierDelivery } from './api';
const __VLS_props = defineProps();
const __VLS_emit = defineEmits();
const tasks = ref([]);
const loading = ref(false);
const activeTab = ref('active');
const search = ref('');
const signerDialog = ref(false);
const exceptionDialog = ref(false);
const selectedTask = ref(null);
const signerName = ref('');
const exceptionForm = ref({ case_type: 'PICKUP_FAILED', description: '' });
const taskPage = ref(1);
const taskPageSize = 5;
const filteredTasks = computed(() => tasks.value.filter((task) => {
    const tabMatch = activeTab.value === 'all' || (activeTab.value === 'completed' ? task.status === 'COMPLETED' : task.status !== 'COMPLETED' && task.status !== 'CANCELLED');
    return tabMatch && (!search.value || task.shipment_id.toLowerCase().includes(search.value.toLowerCase()));
}));
const availableCount = computed(() => tasks.value.filter(task => task.status === 'AVAILABLE').length);
const acceptedCount = computed(() => tasks.value.filter(task => task.status === 'ACCEPTED').length);
const completedCount = computed(() => tasks.value.filter(task => task.status === 'COMPLETED').length);
const pagedTasks = computed(() => filteredTasks.value.slice((taskPage.value - 1) * taskPageSize, taskPage.value * taskPageSize));
const currentTasks = computed(() => pagedTasks.value);
async function loadTasks() {
    loading.value = true;
    try {
        tasks.value = await listCourierTasks();
        taskPage.value = 1;
    }
    catch {
        ElMessage.error('任务加载失败，请确认快递员所属网点');
    }
    finally {
        loading.value = false;
    }
}
async function execute(task) {
    try {
        if (task.status === 'AVAILABLE')
            await acceptCourierTask(task.id);
        else if (task.task_type === 'PICKUP')
            await confirmCourierPickup(task.id);
        else
            await startCourierDelivery(task.shipment_id);
        ElMessage.success(task.status === 'AVAILABLE' ? '接单成功' : task.task_type === 'PICKUP' ? '取件已确认' : '已开始派送');
        await loadTasks();
    }
    catch (error) {
        ElMessage.error(error.response?.data?.message || '任务状态已变化，请刷新后重试');
    }
}
function openSigner(task) { selectedTask.value = task; signerName.value = ''; signerDialog.value = true; }
async function submitSigner() {
    if (!selectedTask.value || !signerName.value.trim())
        return;
    try {
        await confirmCourierDelivery(selectedTask.value.shipment_id, signerName.value.trim());
        signerDialog.value = false;
        ElMessage.success('签收已确认');
        await loadTasks();
    }
    catch (error) {
        ElMessage.error(error.response?.data?.message || '签收确认失败');
    }
}
function openException(task) { selectedTask.value = task; exceptionForm.value = { case_type: task.task_type === 'PICKUP' ? 'PICKUP_FAILED' : 'RECIPIENT_UNREACHABLE', description: '' }; exceptionDialog.value = true; }
async function submitException() {
    if (!selectedTask.value || !exceptionForm.value.description.trim())
        return;
    try {
        await reportException({ shipment_id: selectedTask.value.shipment_id, case_type: exceptionForm.value.case_type, description: exceptionForm.value.description.trim(), evidence_summary: { task_id: selectedTask.value.id, source: 'COURIER_APP' } });
        exceptionDialog.value = false;
        ElMessage.success('异常已上报');
    }
    catch (error) {
        ElMessage.error(error.response?.data?.message || '异常上报失败');
    }
}
function taskTitle(task) { return task.task_type === 'PICKUP' ? '上门取件' : '末端派送'; }
function primaryText(task) { if (task.status === 'AVAILABLE')
    return '接下任务'; return task.task_type === 'PICKUP' ? '确认取件' : '开始派送'; }
onMounted(loadTasks);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "app-shell courier-shell" },
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
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ class: "active" },
});
const __VLS_0 = {}.Van;
/** @type {[typeof __VLS_components.Van, ]} */ ;
// @ts-ignore
const __VLS_1 = __VLS_asFunctionalComponent(__VLS_0, new __VLS_0({}));
const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
if (__VLS_ctx.acceptedCount) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    (__VLS_ctx.acceptedCount);
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
const __VLS_4 = {}.Bell;
/** @type {[typeof __VLS_components.Bell, ]} */ ;
// @ts-ignore
const __VLS_5 = __VLS_asFunctionalComponent(__VLS_4, new __VLS_4({}));
const __VLS_6 = __VLS_5({}, ...__VLS_functionalComponentArgsRest(__VLS_5));
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "courier-shift" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "sidebar-foot" },
});
const __VLS_8 = {}.ElButton;
/** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
// @ts-ignore
const __VLS_9 = __VLS_asFunctionalComponent(__VLS_8, new __VLS_8({
    ...{ 'onClick': {} },
    text: true,
}));
const __VLS_10 = __VLS_9({
    ...{ 'onClick': {} },
    text: true,
}, ...__VLS_functionalComponentArgsRest(__VLS_9));
let __VLS_12;
let __VLS_13;
let __VLS_14;
const __VLS_15 = {
    onClick: (...[$event]) => {
        __VLS_ctx.$emit('logout');
    }
};
__VLS_11.slots.default;
const __VLS_16 = {}.Setting;
/** @type {[typeof __VLS_components.Setting, ]} */ ;
// @ts-ignore
const __VLS_17 = __VLS_asFunctionalComponent(__VLS_16, new __VLS_16({}));
const __VLS_18 = __VLS_17({}, ...__VLS_functionalComponentArgsRest(__VLS_17));
var __VLS_11;
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
__VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "top-actions" },
});
const __VLS_20 = {}.ElInput;
/** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
// @ts-ignore
const __VLS_21 = __VLS_asFunctionalComponent(__VLS_20, new __VLS_20({
    modelValue: (__VLS_ctx.search),
    placeholder: "搜索运单 UUID",
    clearable: true,
}));
const __VLS_22 = __VLS_21({
    modelValue: (__VLS_ctx.search),
    placeholder: "搜索运单 UUID",
    clearable: true,
}, ...__VLS_functionalComponentArgsRest(__VLS_21));
const __VLS_24 = {}.ElButton;
/** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
// @ts-ignore
const __VLS_25 = __VLS_asFunctionalComponent(__VLS_24, new __VLS_24({
    ...{ 'onClick': {} },
    circle: true,
    icon: (__VLS_ctx.Refresh),
}));
const __VLS_26 = __VLS_25({
    ...{ 'onClick': {} },
    circle: true,
    icon: (__VLS_ctx.Refresh),
}, ...__VLS_functionalComponentArgsRest(__VLS_25));
let __VLS_28;
let __VLS_29;
let __VLS_30;
const __VLS_31 = {
    onClick: (__VLS_ctx.loadTasks)
};
var __VLS_27;
const __VLS_32 = {}.ElAvatar;
/** @type {[typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, ]} */ ;
// @ts-ignore
const __VLS_33 = __VLS_asFunctionalComponent(__VLS_32, new __VLS_32({
    size: (34),
}));
const __VLS_34 = __VLS_33({
    size: (34),
}, ...__VLS_functionalComponentArgsRest(__VLS_33));
__VLS_35.slots.default;
(__VLS_ctx.user.display_name.slice(0, 1));
var __VLS_35;
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
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "courier-hero" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ class: "section-kicker" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "route-emblem" },
});
const __VLS_36 = {}.Van;
/** @type {[typeof __VLS_components.Van, ]} */ ;
// @ts-ignore
const __VLS_37 = __VLS_asFunctionalComponent(__VLS_36, new __VLS_36({}));
const __VLS_38 = __VLS_37({}, ...__VLS_functionalComponentArgsRest(__VLS_37));
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "stat-strip courier-stats" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
(__VLS_ctx.availableCount);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
(__VLS_ctx.acceptedCount);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
(__VLS_ctx.completedCount);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "task-toolbar" },
});
const __VLS_40 = {}.ElSegmented;
/** @type {[typeof __VLS_components.ElSegmented, typeof __VLS_components.elSegmented, ]} */ ;
// @ts-ignore
const __VLS_41 = __VLS_asFunctionalComponent(__VLS_40, new __VLS_40({
    ...{ 'onChange': {} },
    modelValue: (__VLS_ctx.activeTab),
    options: ([{ label: '进行中', value: 'active' }, { label: '已完成', value: 'completed' }, { label: '全部', value: 'all' }]),
}));
const __VLS_42 = __VLS_41({
    ...{ 'onChange': {} },
    modelValue: (__VLS_ctx.activeTab),
    options: ([{ label: '进行中', value: 'active' }, { label: '已完成', value: 'completed' }, { label: '全部', value: 'all' }]),
}, ...__VLS_functionalComponentArgsRest(__VLS_41));
let __VLS_44;
let __VLS_45;
let __VLS_46;
const __VLS_47 = {
    onChange: (...[$event]) => {
        __VLS_ctx.taskPage = 1;
    }
};
var __VLS_43;
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
(__VLS_ctx.filteredTasks.length);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "courier-task-list" },
});
for (const [task] of __VLS_getVForSourceType((__VLS_ctx.pagedTasks))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        key: (task.id),
        ...{ class: "courier-task" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "task-sequence" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (task.task_type === 'PICKUP' ? 'P' : 'D');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "task-copy" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "task-heading" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    (task.task_type === 'PICKUP' ? 'PICKUP TASK' : 'DELIVERY TASK');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    (__VLS_ctx.taskTitle(task));
    const __VLS_48 = {}.ElTag;
    /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
    // @ts-ignore
    const __VLS_49 = __VLS_asFunctionalComponent(__VLS_48, new __VLS_48({
        type: (task.status === 'COMPLETED' ? 'success' : task.status === 'AVAILABLE' ? 'warning' : 'primary'),
    }));
    const __VLS_50 = __VLS_49({
        type: (task.status === 'COMPLETED' ? 'success' : task.status === 'AVAILABLE' ? 'warning' : 'primary'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_49));
    __VLS_51.slots.default;
    (task.status === 'AVAILABLE' ? '待接单' : task.status === 'ACCEPTED' ? '执行中' : task.status === 'COMPLETED' ? '已完成' : '已取消');
    var __VLS_51;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "task-meta" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    const __VLS_52 = {}.Box;
    /** @type {[typeof __VLS_components.Box, ]} */ ;
    // @ts-ignore
    const __VLS_53 = __VLS_asFunctionalComponent(__VLS_52, new __VLS_52({}));
    const __VLS_54 = __VLS_53({}, ...__VLS_functionalComponentArgsRest(__VLS_53));
    (task.shipment_id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    const __VLS_56 = {}.Connection;
    /** @type {[typeof __VLS_components.Connection, ]} */ ;
    // @ts-ignore
    const __VLS_57 = __VLS_asFunctionalComponent(__VLS_56, new __VLS_56({}));
    const __VLS_58 = __VLS_57({}, ...__VLS_functionalComponentArgsRest(__VLS_57));
    (task.assignee_id ? '已分配给当前快递员' : '网点公共任务');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "task-actions" },
    });
    if (task.status !== 'COMPLETED' && task.status !== 'CANCELLED') {
        const __VLS_60 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_61 = __VLS_asFunctionalComponent(__VLS_60, new __VLS_60({
            ...{ 'onClick': {} },
            type: "primary",
        }));
        const __VLS_62 = __VLS_61({
            ...{ 'onClick': {} },
            type: "primary",
        }, ...__VLS_functionalComponentArgsRest(__VLS_61));
        let __VLS_64;
        let __VLS_65;
        let __VLS_66;
        const __VLS_67 = {
            onClick: (...[$event]) => {
                if (!(task.status !== 'COMPLETED' && task.status !== 'CANCELLED'))
                    return;
                __VLS_ctx.execute(task);
            }
        };
        __VLS_63.slots.default;
        (__VLS_ctx.primaryText(task));
        var __VLS_63;
    }
    if (task.task_type === 'DELIVERY' && task.status === 'ACCEPTED') {
        const __VLS_68 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_69 = __VLS_asFunctionalComponent(__VLS_68, new __VLS_68({
            ...{ 'onClick': {} },
        }));
        const __VLS_70 = __VLS_69({
            ...{ 'onClick': {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_69));
        let __VLS_72;
        let __VLS_73;
        let __VLS_74;
        const __VLS_75 = {
            onClick: (...[$event]) => {
                if (!(task.task_type === 'DELIVERY' && task.status === 'ACCEPTED'))
                    return;
                __VLS_ctx.openSigner(task);
            }
        };
        __VLS_71.slots.default;
        const __VLS_76 = {}.CircleCheck;
        /** @type {[typeof __VLS_components.CircleCheck, ]} */ ;
        // @ts-ignore
        const __VLS_77 = __VLS_asFunctionalComponent(__VLS_76, new __VLS_76({}));
        const __VLS_78 = __VLS_77({}, ...__VLS_functionalComponentArgsRest(__VLS_77));
        var __VLS_71;
    }
    if (task.status !== 'COMPLETED') {
        const __VLS_80 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_81 = __VLS_asFunctionalComponent(__VLS_80, new __VLS_80({
            ...{ 'onClick': {} },
            text: true,
            type: "danger",
        }));
        const __VLS_82 = __VLS_81({
            ...{ 'onClick': {} },
            text: true,
            type: "danger",
        }, ...__VLS_functionalComponentArgsRest(__VLS_81));
        let __VLS_84;
        let __VLS_85;
        let __VLS_86;
        const __VLS_87 = {
            onClick: (...[$event]) => {
                if (!(task.status !== 'COMPLETED'))
                    return;
                __VLS_ctx.openException(task);
            }
        };
        __VLS_83.slots.default;
        const __VLS_88 = {}.Warning;
        /** @type {[typeof __VLS_components.Warning, ]} */ ;
        // @ts-ignore
        const __VLS_89 = __VLS_asFunctionalComponent(__VLS_88, new __VLS_88({}));
        const __VLS_90 = __VLS_89({}, ...__VLS_functionalComponentArgsRest(__VLS_89));
        var __VLS_83;
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "task-complete" },
        });
        const __VLS_92 = {}.Check;
        /** @type {[typeof __VLS_components.Check, ]} */ ;
        // @ts-ignore
        const __VLS_93 = __VLS_asFunctionalComponent(__VLS_92, new __VLS_92({}));
        const __VLS_94 = __VLS_93({}, ...__VLS_functionalComponentArgsRest(__VLS_93));
    }
}
if (!__VLS_ctx.filteredTasks.length) {
    const __VLS_96 = {}.ElEmpty;
    /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
    // @ts-ignore
    const __VLS_97 = __VLS_asFunctionalComponent(__VLS_96, new __VLS_96({
        description: "当前没有任务",
    }));
    const __VLS_98 = __VLS_97({
        description: "当前没有任务",
    }, ...__VLS_functionalComponentArgsRest(__VLS_97));
}
if (__VLS_ctx.filteredTasks.length > __VLS_ctx.taskPageSize) {
    const __VLS_100 = {}.ElPagination;
    /** @type {[typeof __VLS_components.ElPagination, typeof __VLS_components.elPagination, ]} */ ;
    // @ts-ignore
    const __VLS_101 = __VLS_asFunctionalComponent(__VLS_100, new __VLS_100({
        currentPage: (__VLS_ctx.taskPage),
        pageSize: (__VLS_ctx.taskPageSize),
        layout: "prev, pager, next",
        total: (__VLS_ctx.filteredTasks.length),
        ...{ class: "list-pagination" },
    }));
    const __VLS_102 = __VLS_101({
        currentPage: (__VLS_ctx.taskPage),
        pageSize: (__VLS_ctx.taskPageSize),
        layout: "prev, pager, next",
        total: (__VLS_ctx.filteredTasks.length),
        ...{ class: "list-pagination" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_101));
}
const __VLS_104 = {}.ElDialog;
/** @type {[typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, ]} */ ;
// @ts-ignore
const __VLS_105 = __VLS_asFunctionalComponent(__VLS_104, new __VLS_104({
    modelValue: (__VLS_ctx.signerDialog),
    title: "确认签收",
    width: "430px",
}));
const __VLS_106 = __VLS_105({
    modelValue: (__VLS_ctx.signerDialog),
    title: "确认签收",
    width: "430px",
}, ...__VLS_functionalComponentArgsRest(__VLS_105));
__VLS_107.slots.default;
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ class: "dialog-tip" },
});
const __VLS_108 = {}.ElForm;
/** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
// @ts-ignore
const __VLS_109 = __VLS_asFunctionalComponent(__VLS_108, new __VLS_108({
    labelPosition: "top",
}));
const __VLS_110 = __VLS_109({
    labelPosition: "top",
}, ...__VLS_functionalComponentArgsRest(__VLS_109));
__VLS_111.slots.default;
const __VLS_112 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_113 = __VLS_asFunctionalComponent(__VLS_112, new __VLS_112({
    label: "签收人",
}));
const __VLS_114 = __VLS_113({
    label: "签收人",
}, ...__VLS_functionalComponentArgsRest(__VLS_113));
__VLS_115.slots.default;
const __VLS_116 = {}.ElInput;
/** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
// @ts-ignore
const __VLS_117 = __VLS_asFunctionalComponent(__VLS_116, new __VLS_116({
    modelValue: (__VLS_ctx.signerName),
    placeholder: "请输入签收人姓名",
}));
const __VLS_118 = __VLS_117({
    modelValue: (__VLS_ctx.signerName),
    placeholder: "请输入签收人姓名",
}, ...__VLS_functionalComponentArgsRest(__VLS_117));
var __VLS_115;
var __VLS_111;
{
    const { footer: __VLS_thisSlot } = __VLS_107.slots;
    const __VLS_120 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_121 = __VLS_asFunctionalComponent(__VLS_120, new __VLS_120({
        ...{ 'onClick': {} },
    }));
    const __VLS_122 = __VLS_121({
        ...{ 'onClick': {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_121));
    let __VLS_124;
    let __VLS_125;
    let __VLS_126;
    const __VLS_127 = {
        onClick: (...[$event]) => {
            __VLS_ctx.signerDialog = false;
        }
    };
    __VLS_123.slots.default;
    var __VLS_123;
    const __VLS_128 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_129 = __VLS_asFunctionalComponent(__VLS_128, new __VLS_128({
        ...{ 'onClick': {} },
        type: "primary",
    }));
    const __VLS_130 = __VLS_129({
        ...{ 'onClick': {} },
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_129));
    let __VLS_132;
    let __VLS_133;
    let __VLS_134;
    const __VLS_135 = {
        onClick: (__VLS_ctx.submitSigner)
    };
    __VLS_131.slots.default;
    var __VLS_131;
}
var __VLS_107;
const __VLS_136 = {}.ElDialog;
/** @type {[typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, ]} */ ;
// @ts-ignore
const __VLS_137 = __VLS_asFunctionalComponent(__VLS_136, new __VLS_136({
    modelValue: (__VLS_ctx.exceptionDialog),
    title: "上报履约异常",
    width: "480px",
}));
const __VLS_138 = __VLS_137({
    modelValue: (__VLS_ctx.exceptionDialog),
    title: "上报履约异常",
    width: "480px",
}, ...__VLS_functionalComponentArgsRest(__VLS_137));
__VLS_139.slots.default;
const __VLS_140 = {}.ElForm;
/** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
// @ts-ignore
const __VLS_141 = __VLS_asFunctionalComponent(__VLS_140, new __VLS_140({
    labelPosition: "top",
}));
const __VLS_142 = __VLS_141({
    labelPosition: "top",
}, ...__VLS_functionalComponentArgsRest(__VLS_141));
__VLS_143.slots.default;
const __VLS_144 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_145 = __VLS_asFunctionalComponent(__VLS_144, new __VLS_144({
    label: "异常类型",
}));
const __VLS_146 = __VLS_145({
    label: "异常类型",
}, ...__VLS_functionalComponentArgsRest(__VLS_145));
__VLS_147.slots.default;
const __VLS_148 = {}.ElSelect;
/** @type {[typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, typeof __VLS_components.ElSelect, typeof __VLS_components.elSelect, ]} */ ;
// @ts-ignore
const __VLS_149 = __VLS_asFunctionalComponent(__VLS_148, new __VLS_148({
    modelValue: (__VLS_ctx.exceptionForm.case_type),
}));
const __VLS_150 = __VLS_149({
    modelValue: (__VLS_ctx.exceptionForm.case_type),
}, ...__VLS_functionalComponentArgsRest(__VLS_149));
__VLS_151.slots.default;
const __VLS_152 = {}.ElOption;
/** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
// @ts-ignore
const __VLS_153 = __VLS_asFunctionalComponent(__VLS_152, new __VLS_152({
    label: "取件失败",
    value: "PICKUP_FAILED",
}));
const __VLS_154 = __VLS_153({
    label: "取件失败",
    value: "PICKUP_FAILED",
}, ...__VLS_functionalComponentArgsRest(__VLS_153));
const __VLS_156 = {}.ElOption;
/** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
// @ts-ignore
const __VLS_157 = __VLS_asFunctionalComponent(__VLS_156, new __VLS_156({
    label: "地址错误",
    value: "ADDRESS_ERROR",
}));
const __VLS_158 = __VLS_157({
    label: "地址错误",
    value: "ADDRESS_ERROR",
}, ...__VLS_functionalComponentArgsRest(__VLS_157));
const __VLS_160 = {}.ElOption;
/** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
// @ts-ignore
const __VLS_161 = __VLS_asFunctionalComponent(__VLS_160, new __VLS_160({
    label: "无法联系收件人",
    value: "RECIPIENT_UNREACHABLE",
}));
const __VLS_162 = __VLS_161({
    label: "无法联系收件人",
    value: "RECIPIENT_UNREACHABLE",
}, ...__VLS_functionalComponentArgsRest(__VLS_161));
const __VLS_164 = {}.ElOption;
/** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
// @ts-ignore
const __VLS_165 = __VLS_asFunctionalComponent(__VLS_164, new __VLS_164({
    label: "拒收",
    value: "REFUSED",
}));
const __VLS_166 = __VLS_165({
    label: "拒收",
    value: "REFUSED",
}, ...__VLS_functionalComponentArgsRest(__VLS_165));
const __VLS_168 = {}.ElOption;
/** @type {[typeof __VLS_components.ElOption, typeof __VLS_components.elOption, ]} */ ;
// @ts-ignore
const __VLS_169 = __VLS_asFunctionalComponent(__VLS_168, new __VLS_168({
    label: "包裹破损",
    value: "DAMAGE",
}));
const __VLS_170 = __VLS_169({
    label: "包裹破损",
    value: "DAMAGE",
}, ...__VLS_functionalComponentArgsRest(__VLS_169));
var __VLS_151;
var __VLS_147;
const __VLS_172 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_173 = __VLS_asFunctionalComponent(__VLS_172, new __VLS_172({
    label: "现场说明",
}));
const __VLS_174 = __VLS_173({
    label: "现场说明",
}, ...__VLS_functionalComponentArgsRest(__VLS_173));
__VLS_175.slots.default;
const __VLS_176 = {}.ElInput;
/** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
// @ts-ignore
const __VLS_177 = __VLS_asFunctionalComponent(__VLS_176, new __VLS_176({
    modelValue: (__VLS_ctx.exceptionForm.description),
    type: "textarea",
    rows: (4),
    placeholder: "说明现场情况和已采取的措施",
}));
const __VLS_178 = __VLS_177({
    modelValue: (__VLS_ctx.exceptionForm.description),
    type: "textarea",
    rows: (4),
    placeholder: "说明现场情况和已采取的措施",
}, ...__VLS_functionalComponentArgsRest(__VLS_177));
var __VLS_175;
var __VLS_143;
{
    const { footer: __VLS_thisSlot } = __VLS_139.slots;
    const __VLS_180 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_181 = __VLS_asFunctionalComponent(__VLS_180, new __VLS_180({
        ...{ 'onClick': {} },
    }));
    const __VLS_182 = __VLS_181({
        ...{ 'onClick': {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_181));
    let __VLS_184;
    let __VLS_185;
    let __VLS_186;
    const __VLS_187 = {
        onClick: (...[$event]) => {
            __VLS_ctx.exceptionDialog = false;
        }
    };
    __VLS_183.slots.default;
    var __VLS_183;
    const __VLS_188 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_189 = __VLS_asFunctionalComponent(__VLS_188, new __VLS_188({
        ...{ 'onClick': {} },
        type: "danger",
    }));
    const __VLS_190 = __VLS_189({
        ...{ 'onClick': {} },
        type: "danger",
    }, ...__VLS_functionalComponentArgsRest(__VLS_189));
    let __VLS_192;
    let __VLS_193;
    let __VLS_194;
    const __VLS_195 = {
        onClick: (__VLS_ctx.submitException)
    };
    __VLS_191.slots.default;
    var __VLS_191;
}
var __VLS_139;
/** @type {__VLS_StyleScopedClasses['app-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['courier-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar']} */ ;
/** @type {__VLS_StyleScopedClasses['logo']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-label']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['courier-shift']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar-foot']} */ ;
/** @type {__VLS_StyleScopedClasses['main']} */ ;
/** @type {__VLS_StyleScopedClasses['topbar']} */ ;
/** @type {__VLS_StyleScopedClasses['crumb']} */ ;
/** @type {__VLS_StyleScopedClasses['top-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['user-name']} */ ;
/** @type {__VLS_StyleScopedClasses['content']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['courier-hero']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['route-emblem']} */ ;
/** @type {__VLS_StyleScopedClasses['stat-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['courier-stats']} */ ;
/** @type {__VLS_StyleScopedClasses['task-toolbar']} */ ;
/** @type {__VLS_StyleScopedClasses['courier-task-list']} */ ;
/** @type {__VLS_StyleScopedClasses['courier-task']} */ ;
/** @type {__VLS_StyleScopedClasses['task-sequence']} */ ;
/** @type {__VLS_StyleScopedClasses['task-copy']} */ ;
/** @type {__VLS_StyleScopedClasses['task-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['task-meta']} */ ;
/** @type {__VLS_StyleScopedClasses['task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['task-complete']} */ ;
/** @type {__VLS_StyleScopedClasses['list-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['dialog-tip']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            Bell: Bell,
            Box: Box,
            Check: Check,
            CircleCheck: CircleCheck,
            Connection: Connection,
            Refresh: Refresh,
            Setting: Setting,
            Van: Van,
            Warning: Warning,
            loading: loading,
            activeTab: activeTab,
            search: search,
            signerDialog: signerDialog,
            exceptionDialog: exceptionDialog,
            signerName: signerName,
            exceptionForm: exceptionForm,
            taskPage: taskPage,
            taskPageSize: taskPageSize,
            filteredTasks: filteredTasks,
            availableCount: availableCount,
            acceptedCount: acceptedCount,
            completedCount: completedCount,
            pagedTasks: pagedTasks,
            loadTasks: loadTasks,
            execute: execute,
            openSigner: openSigner,
            submitSigner: submitSigner,
            openException: openException,
            submitException: submitException,
            taskTitle: taskTitle,
            primaryText: primaryText,
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
