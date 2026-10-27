.pragma library

function copy(value) { return JSON.parse(JSON.stringify(value)) }
function sameTarget(a,b) { return Boolean(a&&b&&a.kind===b.kind&&String(a.id||"")===String(b.id||"")) }
function targetName(target,options) {
    if(!target||target.kind==="unconfigured")return qsTr("请选择出口")
    if(target.kind==="direct")return "DIRECT"
    if(target.kind==="reject")return qsTr("拒绝连接")
    const item=(options||[]).find(option=>sameTarget(option,target))
    return item?(item.available?item.name:qsTr("%1（当前不可用）").arg(item.name)):qsTr("出口不可用")
}
function targetAvailable(target,options) {
    return Boolean(target&&(options||[]).some(option=>sameTarget(option,target)&&option.available))
}
function strategyName(strategy) {
    return ({manual:qsTr("手动选择"),url_test:qsTr("自动测速"),fallback:qsTr("故障转移"),load_balance:qsTr("负载均衡")})[strategy]||qsTr("未知类型")
}
function domainSummary(domains) {
    return (domains||[]).map(domain=>(domain.type==="domain_suffix"?"*.":"")+domain.value).join(", ")
}
function conflicts(result) {return result&&result.validation&&result.validation.conflicts?result.validation.conflicts:result&&(result.conflicts||result.warnings)||[]}
function validationText(result,document) {
    const notices=conflicts(result),records=document?(document.service_policies||[]).concat(document.custom_rules||[],document.explicit_direct_rules||[]):[]
    const label=function(id,priority){const record=records.find(item=>item.id===id);return record&&record.name?record.name:qsTr("规则（优先级 %1）").arg(priority)}
    const detail=notices.map(notice=>{
        if(typeof notice==="string")return notice
        if(notice.first_id&&notice.second_id&&notice.witness){const first=label(notice.first_id,notice.first_priority),second=label(notice.second_id,notice.second_priority),winner=notice.winner_id===notice.first_id?first:second;return qsTr("“%1”与“%2”在 %3 重叠；优先使用“%4”。").arg(first).arg(second).arg(notice.witness).arg(winner)}
        return String(notice.message||notice.summary||qsTr("存在需要检查的规则重叠。"))
    }).join("\n")
    if(!result||!result.ok){const error=result&&result.error?String(result.error):qsTr("配置校验失败");return detail?error+"\n"+detail:error}
    return detail||qsTr("当前配置校验通过")
}
