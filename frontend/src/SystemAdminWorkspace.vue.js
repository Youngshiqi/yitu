import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Connection, DataBoard, Document, Files, FolderOpened, Refresh, Search, Setting, UploadFilled, Warning } from '@element-plus/icons-vue';
import { knowledgeAction, listDeadLetters, replayDeadLetter, reviewKnowledgeDocument, searchKnowledge, uploadKnowledgeDocument } from './api';
const __VLS_props = defineProps();
const __VLS_emit = defineEmits();
const view = ref('overview');
const loading = ref(false);
const deadLetters = ref([]);
const documents = ref([]);
const searchText = ref('');
const evidence = ref([]);
const uploadRef = ref();
const reviewDialog = ref(false);
const selectedDocument = ref(null);
const reviewForm = ref({ category: '', effective_from: '', effective_to: '' });
const nav = [{ id: 'overview', label: '系统概览', icon: DataBoard }, { id: 'deadletters', label: '死信队列', icon: Warning }, { id: 'knowledge', label: '知识库文档', icon: Files }, { id: 'retrieval', label: '检索验证', icon: Search }];
const pendingDeadLetters = computed(() => deadLetters.value.filter(item => !item.replayed_at));
const publishedDocuments = computed(() => documents.value.filter(item => item.status === 'PUBLISHED').length);
async function loadData() { loading.value = true; try {
    deadLetters.value = await listDeadLetters({ limit: 100, offset: 0 });
}
catch {
    ElMessage.error('系统运维数据加载失败');
}
finally {
    loading.value = false;
} }
async function replay(item) { try {
    await replayDeadLetter(item.id);
    ElMessage.success('死信已重新投递');
    await loadData();
}
catch (error) {
    ElMessage.error(error.response?.data?.message || '死信重放失败');
} }
async function upload(request) { try {
    const document = await uploadKnowledgeDocument(request.file);
    documents.value = [document, ...documents.value];
    ElMessage.success('文档已上传，正在进入解析队列');
}
catch (error) {
    ElMessage.error(error.response?.data?.message || '文档上传失败');
} }
function openReview(item) { selectedDocument.value = item; reviewForm.value = { category: item.category || '', effective_from: '', effective_to: '' }; reviewDialog.value = true; }
async function submitReview() { if (!selectedDocument.value)
    return; try {
    const updated = await reviewKnowledgeDocument(selectedDocument.value.id, { category: reviewForm.value.category || undefined, effective_from: reviewForm.value.effective_from || undefined, effective_to: reviewForm.value.effective_to || undefined });
    updateDocument(updated);
    reviewDialog.value = false;
    ElMessage.success('审核信息已保存');
}
catch (error) {
    ElMessage.error(error.response?.data?.message || '审核保存失败');
} }
async function documentAction(item, action) { try {
    updateDocument(await knowledgeAction(item.id, action));
    ElMessage.success(action === 'publish' ? '文档已发布' : action === 'reparse' ? '已重新提交解析' : '文档状态已更新');
}
catch (error) {
    ElMessage.error(error.response?.data?.message || '操作失败，请检查文档当前状态');
} }
function updateDocument(updated) { documents.value = documents.value.map(item => item.id === updated.id ? updated : item); }
async function runSearch() { if (!searchText.value.trim())
    return; try {
    evidence.value = (await searchKnowledge(searchText.value.trim())).items;
}
catch (error) {
    ElMessage.error(error.response?.data?.message || '知识检索失败');
} }
function statusType(status) { return status === 'PUBLISHED' ? 'success' : status === 'PARSE_FAILED' ? 'danger' : status === 'REVIEW_REQUIRED' ? 'warning' : 'info'; }
onMounted(loadData);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "app-shell system-shell" },
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
    if (item.id === 'deadletters' && __VLS_ctx.pendingDeadLetters.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.pendingDeadLetters.length);
    }
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "system-health" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
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
const __VLS_16 = {}.ElButton;
/** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
// @ts-ignore
const __VLS_17 = __VLS_asFunctionalComponent(__VLS_16, new __VLS_16({
    ...{ 'onClick': {} },
    circle: true,
    icon: (__VLS_ctx.Refresh),
}));
const __VLS_18 = __VLS_17({
    ...{ 'onClick': {} },
    circle: true,
    icon: (__VLS_ctx.Refresh),
}, ...__VLS_functionalComponentArgsRest(__VLS_17));
let __VLS_20;
let __VLS_21;
let __VLS_22;
const __VLS_23 = {
    onClick: (__VLS_ctx.loadData)
};
var __VLS_19;
const __VLS_24 = {}.ElAvatar;
/** @type {[typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, typeof __VLS_components.ElAvatar, typeof __VLS_components.elAvatar, ]} */ ;
// @ts-ignore
const __VLS_25 = __VLS_asFunctionalComponent(__VLS_24, new __VLS_24({
    size: (34),
}));
const __VLS_26 = __VLS_25({
    size: (34),
}, ...__VLS_functionalComponentArgsRest(__VLS_25));
__VLS_27.slots.default;
(__VLS_ctx.user.display_name.slice(0, 1));
var __VLS_27;
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
        ...{ class: "system-hero" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "system-emblem" },
    });
    const __VLS_28 = {}.Connection;
    /** @type {[typeof __VLS_components.Connection, ]} */ ;
    // @ts-ignore
    const __VLS_29 = __VLS_asFunctionalComponent(__VLS_28, new __VLS_28({}));
    const __VLS_30 = __VLS_29({}, ...__VLS_functionalComponentArgsRest(__VLS_29));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "system-kpis" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.pendingDeadLetters.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.documents.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.publishedDocuments);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head compact" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    const __VLS_32 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_33 = __VLS_asFunctionalComponent(__VLS_32, new __VLS_32({
        ...{ 'onClick': {} },
        text: true,
        type: "primary",
    }));
    const __VLS_34 = __VLS_33({
        ...{ 'onClick': {} },
        text: true,
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_33));
    let __VLS_36;
    let __VLS_37;
    let __VLS_38;
    const __VLS_39 = {
        onClick: (...[$event]) => {
            if (!(__VLS_ctx.view === 'overview'))
                return;
            __VLS_ctx.view = 'deadletters';
        }
    };
    __VLS_35.slots.default;
    var __VLS_35;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "sys-alerts" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.pendingDeadLetters.slice(0, 4)))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (item.id),
        });
        const __VLS_40 = {}.Warning;
        /** @type {[typeof __VLS_components.Warning, ]} */ ;
        // @ts-ignore
        const __VLS_41 = __VLS_asFunctionalComponent(__VLS_40, new __VLS_40({}));
        const __VLS_42 = __VLS_41({}, ...__VLS_functionalComponentArgsRest(__VLS_41));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (item.event_type);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (item.last_error);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (item.business_id);
        (item.attempts);
        const __VLS_44 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_45 = __VLS_asFunctionalComponent(__VLS_44, new __VLS_44({
            ...{ 'onClick': {} },
            type: "primary",
            plain: true,
        }));
        const __VLS_46 = __VLS_45({
            ...{ 'onClick': {} },
            type: "primary",
            plain: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_45));
        let __VLS_48;
        let __VLS_49;
        let __VLS_50;
        const __VLS_51 = {
            onClick: (...[$event]) => {
                if (!(__VLS_ctx.view === 'overview'))
                    return;
                __VLS_ctx.replay(item);
            }
        };
        __VLS_47.slots.default;
        var __VLS_47;
    }
    if (!__VLS_ctx.pendingDeadLetters.length) {
        const __VLS_52 = {}.ElEmpty;
        /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
        // @ts-ignore
        const __VLS_53 = __VLS_asFunctionalComponent(__VLS_52, new __VLS_52({
            description: "没有待处理死信",
        }));
        const __VLS_54 = __VLS_53({
            description: "没有待处理死信",
        }, ...__VLS_functionalComponentArgsRest(__VLS_53));
    }
}
else if (__VLS_ctx.view === 'deadletters') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "mono-caption" },
    });
    (__VLS_ctx.deadLetters.length);
    const __VLS_56 = {}.ElTable;
    /** @type {[typeof __VLS_components.ElTable, typeof __VLS_components.elTable, typeof __VLS_components.ElTable, typeof __VLS_components.elTable, ]} */ ;
    // @ts-ignore
    const __VLS_57 = __VLS_asFunctionalComponent(__VLS_56, new __VLS_56({
        data: (__VLS_ctx.deadLetters),
        ...{ class: "shipment-table" },
    }));
    const __VLS_58 = __VLS_57({
        data: (__VLS_ctx.deadLetters),
        ...{ class: "shipment-table" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_57));
    __VLS_59.slots.default;
    const __VLS_60 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_61 = __VLS_asFunctionalComponent(__VLS_60, new __VLS_60({
        prop: "event_type",
        label: "事件类型",
        minWidth: "150",
    }));
    const __VLS_62 = __VLS_61({
        prop: "event_type",
        label: "事件类型",
        minWidth: "150",
    }, ...__VLS_functionalComponentArgsRest(__VLS_61));
    const __VLS_64 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_65 = __VLS_asFunctionalComponent(__VLS_64, new __VLS_64({
        prop: "business_id",
        label: "业务标识",
        minWidth: "160",
    }));
    const __VLS_66 = __VLS_65({
        prop: "business_id",
        label: "业务标识",
        minWidth: "160",
    }, ...__VLS_functionalComponentArgsRest(__VLS_65));
    const __VLS_68 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_69 = __VLS_asFunctionalComponent(__VLS_68, new __VLS_68({
        prop: "attempts",
        label: "尝试次数",
        width: "90",
    }));
    const __VLS_70 = __VLS_69({
        prop: "attempts",
        label: "尝试次数",
        width: "90",
    }, ...__VLS_functionalComponentArgsRest(__VLS_69));
    const __VLS_72 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_73 = __VLS_asFunctionalComponent(__VLS_72, new __VLS_72({
        prop: "last_error",
        label: "最后错误",
        minWidth: "220",
        showOverflowTooltip: true,
    }));
    const __VLS_74 = __VLS_73({
        prop: "last_error",
        label: "最后错误",
        minWidth: "220",
        showOverflowTooltip: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_73));
    const __VLS_76 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_77 = __VLS_asFunctionalComponent(__VLS_76, new __VLS_76({
        prop: "suggested_action",
        label: "建议操作",
        minWidth: "150",
    }));
    const __VLS_78 = __VLS_77({
        prop: "suggested_action",
        label: "建议操作",
        minWidth: "150",
    }, ...__VLS_functionalComponentArgsRest(__VLS_77));
    const __VLS_80 = {}.ElTableColumn;
    /** @type {[typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, typeof __VLS_components.ElTableColumn, typeof __VLS_components.elTableColumn, ]} */ ;
    // @ts-ignore
    const __VLS_81 = __VLS_asFunctionalComponent(__VLS_80, new __VLS_80({
        label: "操作",
        width: "110",
    }));
    const __VLS_82 = __VLS_81({
        label: "操作",
        width: "110",
    }, ...__VLS_functionalComponentArgsRest(__VLS_81));
    __VLS_83.slots.default;
    {
        const { default: __VLS_thisSlot } = __VLS_83.slots;
        const [{ row }] = __VLS_getSlotParams(__VLS_thisSlot);
        if (!row.replayed_at) {
            const __VLS_84 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_85 = __VLS_asFunctionalComponent(__VLS_84, new __VLS_84({
                ...{ 'onClick': {} },
                type: "primary",
                size: "small",
            }));
            const __VLS_86 = __VLS_85({
                ...{ 'onClick': {} },
                type: "primary",
                size: "small",
            }, ...__VLS_functionalComponentArgsRest(__VLS_85));
            let __VLS_88;
            let __VLS_89;
            let __VLS_90;
            const __VLS_91 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!(__VLS_ctx.view === 'deadletters'))
                        return;
                    if (!(!row.replayed_at))
                        return;
                    __VLS_ctx.replay(row);
                }
            };
            __VLS_87.slots.default;
            var __VLS_87;
        }
        else {
            const __VLS_92 = {}.ElTag;
            /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
            // @ts-ignore
            const __VLS_93 = __VLS_asFunctionalComponent(__VLS_92, new __VLS_92({
                type: "success",
                size: "small",
            }));
            const __VLS_94 = __VLS_93({
                type: "success",
                size: "small",
            }, ...__VLS_functionalComponentArgsRest(__VLS_93));
            __VLS_95.slots.default;
            var __VLS_95;
        }
    }
    var __VLS_83;
    var __VLS_59;
}
else if (__VLS_ctx.view === 'knowledge') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    const __VLS_96 = {}.ElUpload;
    /** @type {[typeof __VLS_components.ElUpload, typeof __VLS_components.elUpload, typeof __VLS_components.ElUpload, typeof __VLS_components.elUpload, ]} */ ;
    // @ts-ignore
    const __VLS_97 = __VLS_asFunctionalComponent(__VLS_96, new __VLS_96({
        ref: "uploadRef",
        showFileList: (false),
        accept: "application/pdf,.pdf",
        httpRequest: (__VLS_ctx.upload),
    }));
    const __VLS_98 = __VLS_97({
        ref: "uploadRef",
        showFileList: (false),
        accept: "application/pdf,.pdf",
        httpRequest: (__VLS_ctx.upload),
    }, ...__VLS_functionalComponentArgsRest(__VLS_97));
    /** @type {typeof __VLS_ctx.uploadRef} */ ;
    var __VLS_100 = {};
    __VLS_99.slots.default;
    const __VLS_102 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_103 = __VLS_asFunctionalComponent(__VLS_102, new __VLS_102({
        type: "primary",
    }));
    const __VLS_104 = __VLS_103({
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_103));
    __VLS_105.slots.default;
    const __VLS_106 = {}.UploadFilled;
    /** @type {[typeof __VLS_components.UploadFilled, ]} */ ;
    // @ts-ignore
    const __VLS_107 = __VLS_asFunctionalComponent(__VLS_106, new __VLS_106({}));
    const __VLS_108 = __VLS_107({}, ...__VLS_functionalComponentArgsRest(__VLS_107));
    var __VLS_105;
    var __VLS_99;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "knowledge-note" },
    });
    const __VLS_110 = {}.FolderOpened;
    /** @type {[typeof __VLS_components.FolderOpened, ]} */ ;
    // @ts-ignore
    const __VLS_111 = __VLS_asFunctionalComponent(__VLS_110, new __VLS_110({}));
    const __VLS_112 = __VLS_111({}, ...__VLS_functionalComponentArgsRest(__VLS_111));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "document-grid" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.documents))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (item.id),
            ...{ class: "document-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "doc-icon" },
        });
        const __VLS_114 = {}.Document;
        /** @type {[typeof __VLS_components.Document, ]} */ ;
        // @ts-ignore
        const __VLS_115 = __VLS_asFunctionalComponent(__VLS_114, new __VLS_114({}));
        const __VLS_116 = __VLS_115({}, ...__VLS_functionalComponentArgsRest(__VLS_115));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "doc-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        (item.filename);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        ((item.size_bytes / 1024).toFixed(1));
        (item.content_type);
        const __VLS_118 = {}.ElTag;
        /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
        // @ts-ignore
        const __VLS_119 = __VLS_asFunctionalComponent(__VLS_118, new __VLS_118({
            type: (__VLS_ctx.statusType(item.status)),
        }));
        const __VLS_120 = __VLS_119({
            type: (__VLS_ctx.statusType(item.status)),
        }, ...__VLS_functionalComponentArgsRest(__VLS_119));
        __VLS_121.slots.default;
        (item.status);
        var __VLS_121;
        if (item.error_message) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "doc-error" },
            });
            (item.error_message);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dl, __VLS_intrinsicElements.dl)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
        (item.category || '未分类');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
        (item.page_count ?? '解析中');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
        (item.mineru_task_id || '等待提交');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "doc-actions" },
        });
        const __VLS_122 = {}.ElButton;
        /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
        // @ts-ignore
        const __VLS_123 = __VLS_asFunctionalComponent(__VLS_122, new __VLS_122({
            ...{ 'onClick': {} },
            size: "small",
        }));
        const __VLS_124 = __VLS_123({
            ...{ 'onClick': {} },
            size: "small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_123));
        let __VLS_126;
        let __VLS_127;
        let __VLS_128;
        const __VLS_129 = {
            onClick: (...[$event]) => {
                if (!!(__VLS_ctx.view === 'overview'))
                    return;
                if (!!(__VLS_ctx.view === 'deadletters'))
                    return;
                if (!(__VLS_ctx.view === 'knowledge'))
                    return;
                __VLS_ctx.openReview(item);
            }
        };
        __VLS_125.slots.default;
        var __VLS_125;
        if (item.status === 'REVIEW_REQUIRED') {
            const __VLS_130 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_131 = __VLS_asFunctionalComponent(__VLS_130, new __VLS_130({
                ...{ 'onClick': {} },
                type: "primary",
                size: "small",
            }));
            const __VLS_132 = __VLS_131({
                ...{ 'onClick': {} },
                type: "primary",
                size: "small",
            }, ...__VLS_functionalComponentArgsRest(__VLS_131));
            let __VLS_134;
            let __VLS_135;
            let __VLS_136;
            const __VLS_137 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!!(__VLS_ctx.view === 'deadletters'))
                        return;
                    if (!(__VLS_ctx.view === 'knowledge'))
                        return;
                    if (!(item.status === 'REVIEW_REQUIRED'))
                        return;
                    __VLS_ctx.documentAction(item, 'publish');
                }
            };
            __VLS_133.slots.default;
            var __VLS_133;
        }
        if (['PARSE_FAILED', 'ARCHIVED', 'DEACTIVATED'].includes(item.status)) {
            const __VLS_138 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_139 = __VLS_asFunctionalComponent(__VLS_138, new __VLS_138({
                ...{ 'onClick': {} },
                size: "small",
            }));
            const __VLS_140 = __VLS_139({
                ...{ 'onClick': {} },
                size: "small",
            }, ...__VLS_functionalComponentArgsRest(__VLS_139));
            let __VLS_142;
            let __VLS_143;
            let __VLS_144;
            const __VLS_145 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!!(__VLS_ctx.view === 'deadletters'))
                        return;
                    if (!(__VLS_ctx.view === 'knowledge'))
                        return;
                    if (!(['PARSE_FAILED', 'ARCHIVED', 'DEACTIVATED'].includes(item.status)))
                        return;
                    __VLS_ctx.documentAction(item, 'reparse');
                }
            };
            __VLS_141.slots.default;
            var __VLS_141;
        }
        if (item.status === 'PUBLISHED') {
            const __VLS_146 = {}.ElButton;
            /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
            // @ts-ignore
            const __VLS_147 = __VLS_asFunctionalComponent(__VLS_146, new __VLS_146({
                ...{ 'onClick': {} },
                type: "warning",
                plain: true,
                size: "small",
            }));
            const __VLS_148 = __VLS_147({
                ...{ 'onClick': {} },
                type: "warning",
                plain: true,
                size: "small",
            }, ...__VLS_functionalComponentArgsRest(__VLS_147));
            let __VLS_150;
            let __VLS_151;
            let __VLS_152;
            const __VLS_153 = {
                onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.view === 'overview'))
                        return;
                    if (!!(__VLS_ctx.view === 'deadletters'))
                        return;
                    if (!(__VLS_ctx.view === 'knowledge'))
                        return;
                    if (!(item.status === 'PUBLISHED'))
                        return;
                    __VLS_ctx.documentAction(item, 'archive');
                }
            };
            __VLS_149.slots.default;
            var __VLS_149;
        }
    }
    if (!__VLS_ctx.documents.length) {
        const __VLS_154 = {}.ElEmpty;
        /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
        // @ts-ignore
        const __VLS_155 = __VLS_asFunctionalComponent(__VLS_154, new __VLS_154({
            description: "上传第一份规则文档",
        }));
        const __VLS_156 = __VLS_155({
            description: "上传第一份规则文档",
        }, ...__VLS_functionalComponentArgsRest(__VLS_155));
    }
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
        ...{ class: "retrieval-search" },
    });
    const __VLS_158 = {}.ElInput;
    /** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
    // @ts-ignore
    const __VLS_159 = __VLS_asFunctionalComponent(__VLS_158, new __VLS_158({
        ...{ 'onKeyup': {} },
        modelValue: (__VLS_ctx.searchText),
        size: "large",
        placeholder: "输入规则问题，例如：哪些物品禁止寄递？",
    }));
    const __VLS_160 = __VLS_159({
        ...{ 'onKeyup': {} },
        modelValue: (__VLS_ctx.searchText),
        size: "large",
        placeholder: "输入规则问题，例如：哪些物品禁止寄递？",
    }, ...__VLS_functionalComponentArgsRest(__VLS_159));
    let __VLS_162;
    let __VLS_163;
    let __VLS_164;
    const __VLS_165 = {
        onKeyup: (__VLS_ctx.runSearch)
    };
    var __VLS_161;
    const __VLS_166 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_167 = __VLS_asFunctionalComponent(__VLS_166, new __VLS_166({
        ...{ 'onClick': {} },
        type: "primary",
        size: "large",
    }));
    const __VLS_168 = __VLS_167({
        ...{ 'onClick': {} },
        type: "primary",
        size: "large",
    }, ...__VLS_functionalComponentArgsRest(__VLS_167));
    let __VLS_170;
    let __VLS_171;
    let __VLS_172;
    const __VLS_173 = {
        onClick: (__VLS_ctx.runSearch)
    };
    __VLS_169.slots.default;
    const __VLS_174 = {}.Search;
    /** @type {[typeof __VLS_components.Search, ]} */ ;
    // @ts-ignore
    const __VLS_175 = __VLS_asFunctionalComponent(__VLS_174, new __VLS_174({}));
    const __VLS_176 = __VLS_175({}, ...__VLS_functionalComponentArgsRest(__VLS_175));
    var __VLS_169;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "evidence-list" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.evidence))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (`${item.document_id}-${item.score}`),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "evidence-score" },
        });
        ((item.score * 100).toFixed(0));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "evidence-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (item.title || item.filename);
        const __VLS_178 = {}.ElTag;
        /** @type {[typeof __VLS_components.ElTag, typeof __VLS_components.elTag, typeof __VLS_components.ElTag, typeof __VLS_components.elTag, ]} */ ;
        // @ts-ignore
        const __VLS_179 = __VLS_asFunctionalComponent(__VLS_178, new __VLS_178({
            size: "small",
            effect: "plain",
        }));
        const __VLS_180 = __VLS_179({
            size: "small",
            effect: "plain",
        }, ...__VLS_functionalComponentArgsRest(__VLS_179));
        __VLS_181.slots.default;
        (item.category || '未分类');
        var __VLS_181;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (item.content);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (item.filename);
        (item.page_start ? `第 ${item.page_start}-${item.page_end || item.page_start} 页` : '无页码');
    }
    if (!__VLS_ctx.evidence.length) {
        const __VLS_182 = {}.ElEmpty;
        /** @type {[typeof __VLS_components.ElEmpty, typeof __VLS_components.elEmpty, ]} */ ;
        // @ts-ignore
        const __VLS_183 = __VLS_asFunctionalComponent(__VLS_182, new __VLS_182({
            description: "输入问题后验证知识检索结果",
        }));
        const __VLS_184 = __VLS_183({
            description: "输入问题后验证知识检索结果",
        }, ...__VLS_functionalComponentArgsRest(__VLS_183));
    }
}
const __VLS_186 = {}.ElDialog;
/** @type {[typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, typeof __VLS_components.ElDialog, typeof __VLS_components.elDialog, ]} */ ;
// @ts-ignore
const __VLS_187 = __VLS_asFunctionalComponent(__VLS_186, new __VLS_186({
    modelValue: (__VLS_ctx.reviewDialog),
    title: "审核文档信息",
    width: "480px",
}));
const __VLS_188 = __VLS_187({
    modelValue: (__VLS_ctx.reviewDialog),
    title: "审核文档信息",
    width: "480px",
}, ...__VLS_functionalComponentArgsRest(__VLS_187));
__VLS_189.slots.default;
const __VLS_190 = {}.ElForm;
/** @type {[typeof __VLS_components.ElForm, typeof __VLS_components.elForm, typeof __VLS_components.ElForm, typeof __VLS_components.elForm, ]} */ ;
// @ts-ignore
const __VLS_191 = __VLS_asFunctionalComponent(__VLS_190, new __VLS_190({
    labelPosition: "top",
}));
const __VLS_192 = __VLS_191({
    labelPosition: "top",
}, ...__VLS_functionalComponentArgsRest(__VLS_191));
__VLS_193.slots.default;
const __VLS_194 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_195 = __VLS_asFunctionalComponent(__VLS_194, new __VLS_194({
    label: "知识分类",
}));
const __VLS_196 = __VLS_195({
    label: "知识分类",
}, ...__VLS_functionalComponentArgsRest(__VLS_195));
__VLS_197.slots.default;
const __VLS_198 = {}.ElInput;
/** @type {[typeof __VLS_components.ElInput, typeof __VLS_components.elInput, ]} */ ;
// @ts-ignore
const __VLS_199 = __VLS_asFunctionalComponent(__VLS_198, new __VLS_198({
    modelValue: (__VLS_ctx.reviewForm.category),
    placeholder: "例如：禁寄规则",
}));
const __VLS_200 = __VLS_199({
    modelValue: (__VLS_ctx.reviewForm.category),
    placeholder: "例如：禁寄规则",
}, ...__VLS_functionalComponentArgsRest(__VLS_199));
var __VLS_197;
const __VLS_202 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_203 = __VLS_asFunctionalComponent(__VLS_202, new __VLS_202({
    label: "生效时间",
}));
const __VLS_204 = __VLS_203({
    label: "生效时间",
}, ...__VLS_functionalComponentArgsRest(__VLS_203));
__VLS_205.slots.default;
const __VLS_206 = {}.ElDatePicker;
/** @type {[typeof __VLS_components.ElDatePicker, typeof __VLS_components.elDatePicker, ]} */ ;
// @ts-ignore
const __VLS_207 = __VLS_asFunctionalComponent(__VLS_206, new __VLS_206({
    modelValue: (__VLS_ctx.reviewForm.effective_from),
    type: "datetime",
    valueFormat: "YYYY-MM-DDTHH:mm:ssZ",
}));
const __VLS_208 = __VLS_207({
    modelValue: (__VLS_ctx.reviewForm.effective_from),
    type: "datetime",
    valueFormat: "YYYY-MM-DDTHH:mm:ssZ",
}, ...__VLS_functionalComponentArgsRest(__VLS_207));
var __VLS_205;
const __VLS_210 = {}.ElFormItem;
/** @type {[typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, typeof __VLS_components.ElFormItem, typeof __VLS_components.elFormItem, ]} */ ;
// @ts-ignore
const __VLS_211 = __VLS_asFunctionalComponent(__VLS_210, new __VLS_210({
    label: "失效时间",
}));
const __VLS_212 = __VLS_211({
    label: "失效时间",
}, ...__VLS_functionalComponentArgsRest(__VLS_211));
__VLS_213.slots.default;
const __VLS_214 = {}.ElDatePicker;
/** @type {[typeof __VLS_components.ElDatePicker, typeof __VLS_components.elDatePicker, ]} */ ;
// @ts-ignore
const __VLS_215 = __VLS_asFunctionalComponent(__VLS_214, new __VLS_214({
    modelValue: (__VLS_ctx.reviewForm.effective_to),
    type: "datetime",
    valueFormat: "YYYY-MM-DDTHH:mm:ssZ",
}));
const __VLS_216 = __VLS_215({
    modelValue: (__VLS_ctx.reviewForm.effective_to),
    type: "datetime",
    valueFormat: "YYYY-MM-DDTHH:mm:ssZ",
}, ...__VLS_functionalComponentArgsRest(__VLS_215));
var __VLS_213;
var __VLS_193;
{
    const { footer: __VLS_thisSlot } = __VLS_189.slots;
    const __VLS_218 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_219 = __VLS_asFunctionalComponent(__VLS_218, new __VLS_218({
        ...{ 'onClick': {} },
    }));
    const __VLS_220 = __VLS_219({
        ...{ 'onClick': {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_219));
    let __VLS_222;
    let __VLS_223;
    let __VLS_224;
    const __VLS_225 = {
        onClick: (...[$event]) => {
            __VLS_ctx.reviewDialog = false;
        }
    };
    __VLS_221.slots.default;
    var __VLS_221;
    const __VLS_226 = {}.ElButton;
    /** @type {[typeof __VLS_components.ElButton, typeof __VLS_components.elButton, typeof __VLS_components.ElButton, typeof __VLS_components.elButton, ]} */ ;
    // @ts-ignore
    const __VLS_227 = __VLS_asFunctionalComponent(__VLS_226, new __VLS_226({
        ...{ 'onClick': {} },
        type: "primary",
    }));
    const __VLS_228 = __VLS_227({
        ...{ 'onClick': {} },
        type: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_227));
    let __VLS_230;
    let __VLS_231;
    let __VLS_232;
    const __VLS_233 = {
        onClick: (__VLS_ctx.submitReview)
    };
    __VLS_229.slots.default;
    var __VLS_229;
}
var __VLS_189;
/** @type {__VLS_StyleScopedClasses['app-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['system-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar']} */ ;
/** @type {__VLS_StyleScopedClasses['logo']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-label']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['system-health']} */ ;
/** @type {__VLS_StyleScopedClasses['sidebar-foot']} */ ;
/** @type {__VLS_StyleScopedClasses['main']} */ ;
/** @type {__VLS_StyleScopedClasses['topbar']} */ ;
/** @type {__VLS_StyleScopedClasses['crumb']} */ ;
/** @type {__VLS_StyleScopedClasses['top-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['user-name']} */ ;
/** @type {__VLS_StyleScopedClasses['content']} */ ;
/** @type {__VLS_StyleScopedClasses['page-block']} */ ;
/** @type {__VLS_StyleScopedClasses['system-hero']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['system-emblem']} */ ;
/** @type {__VLS_StyleScopedClasses['system-kpis']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['compact']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['sys-alerts']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['mono-caption']} */ ;
/** @type {__VLS_StyleScopedClasses['shipment-table']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['knowledge-note']} */ ;
/** @type {__VLS_StyleScopedClasses['document-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['document-card']} */ ;
/** @type {__VLS_StyleScopedClasses['doc-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['doc-head']} */ ;
/** @type {__VLS_StyleScopedClasses['doc-error']} */ ;
/** @type {__VLS_StyleScopedClasses['doc-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['section-head']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['retrieval-search']} */ ;
/** @type {__VLS_StyleScopedClasses['evidence-list']} */ ;
/** @type {__VLS_StyleScopedClasses['evidence-score']} */ ;
/** @type {__VLS_StyleScopedClasses['evidence-head']} */ ;
// @ts-ignore
var __VLS_101 = __VLS_100;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            Connection: Connection,
            Document: Document,
            FolderOpened: FolderOpened,
            Refresh: Refresh,
            Search: Search,
            Setting: Setting,
            UploadFilled: UploadFilled,
            Warning: Warning,
            view: view,
            loading: loading,
            deadLetters: deadLetters,
            documents: documents,
            searchText: searchText,
            evidence: evidence,
            uploadRef: uploadRef,
            reviewDialog: reviewDialog,
            reviewForm: reviewForm,
            nav: nav,
            pendingDeadLetters: pendingDeadLetters,
            publishedDocuments: publishedDocuments,
            loadData: loadData,
            replay: replay,
            upload: upload,
            openReview: openReview,
            submitReview: submitReview,
            documentAction: documentAction,
            runSearch: runSearch,
            statusType: statusType,
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
