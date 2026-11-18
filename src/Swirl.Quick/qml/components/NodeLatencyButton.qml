import QtQuick
import SwirlQuick
import "../controls"

SwirlStatusCapsule {
    id:control
    property var record:({})
    objectName:"nodeLatency-"+String(record.id||"")
    readonly property bool pending:Boolean(record.testPending)
    readonly property bool measured:Boolean(record.testAvailable)
    readonly property string failure:!pending&&!measured&&record.probeStatusText&&record.probeStatusText!=="—"?String(record.probeStatusText):""
    label:pending?qsTr("检测中"):measured?String(record.exitLatency)+" ms":failure.length?(failure.indexOf("TLS")>=0?qsTr("TLS 失败"):failure.indexOf("DNS")>=0?qsTr("DNS 失败"):failure.indexOf("超时")>=0?qsTr("超时"):qsTr("失败")):qsTr("测延迟")
    text:label
    tone:measured?"success":failure.length?"warning":"neutral"
    activityPhase:pending?"pending":""
    detail:failure.length?failure+qsTr("。点击仅重试此节点。"):qsTr("请求发出到响应头返回的时间；HTTPS 会先完成 TLS。点击仅刷新此节点。")
    implicitHeight:Theme.dp(32)
    enabled:!pending
    Accessible.name:String(record.name||"")+qsTr("，延迟 %1，点击重新检测此节点").arg(label)
    SwirlToolTip { visible:control.hovered||control.activeFocus; text:control.detail }
}
