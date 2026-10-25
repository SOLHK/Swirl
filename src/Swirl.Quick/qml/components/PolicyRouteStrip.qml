pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

Rectangle {
    id: strip
    property var defaultPolicy: ({target: {kind: "unconfigured"}})
    property var targetOptions: []
    property string sourceLabel: ""
    property string mode: "rule"
    property bool editable: true
    readonly property var target: defaultPolicy.target || {kind: "unconfigured"}
    readonly property bool configured: ["node", "group"].indexOf(target.kind) >= 0
    signal targetRequested(Item source)
    color: Theme.buttonBase
    radius: Theme.dp(12)
    implicitHeight: body.implicitHeight + Theme.dp(24)

    ColumnLayout {
        id: body
        anchors.fill: parent; anchors.margins: Theme.dp(12); spacing: Theme.dp(10)
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(12)
            ColumnLayout {
                Layout.preferredWidth: Theme.dp(148); spacing: Theme.dp(3)
                SwirlText { text: qsTr("默认出口"); color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                SwirlText { Layout.fillWidth: true; text: strip.mode === "global" ? qsTr("普通流量") : strip.mode === "direct" ? qsTr("已保存的代理出口") : qsTr("未单独分配的流量"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
            }
            SwirlIcon { name: "chevron-right"; size: Theme.dp(14); color: Theme.muted; Accessible.ignored: true }
            SubscriptionAction {
                id: choose
                objectName: "defaultPolicyTarget"
                Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredHeight: Theme.dp(48)
                enabled: strip.editable
                text: Policy.targetName(strip.target, strip.targetOptions)
                tooltip: text
                Accessible.name: qsTr("默认策略出口：%1").arg(text)
                contentItem: RowLayout {
                    spacing: Theme.dp(10)
                    SwirlIcon { name: strip.target.kind === "group" ? "layers" : "route"; size: Theme.dp(19); color: Theme.muted; Accessible.ignored: true }
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(3)
                        SwirlText { objectName: "defaultPolicyTargetText"; Layout.fillWidth: true; Layout.minimumWidth: 0; text: choose.text; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold; elide: Text.ElideRight }
                        SwirlText { objectName: "defaultPolicySource"; Layout.fillWidth: true; Layout.minimumWidth: 0; text: strip.sourceLabel || qsTr("选择节点或策略组"); textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                    }
                    SwirlIcon { name: "chevron-up-down"; size: Theme.dp(12); color: Theme.muted; Accessible.ignored: true }
                }
                onClicked: strip.targetRequested(choose)
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.border }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(8)
            SwirlIcon { name: strip.mode === "rule" ? "shield" : "route"; size: Theme.dp(14); color: Theme.muted; Accessible.ignored: true }
            SwirlText {
                objectName: "policyRoutingExplanation"
                Layout.fillWidth: true; wrapMode: Text.Wrap
                text: strip.mode === "direct" ? qsTr("直连模式：受接管流量直接出站，以下分配暂不参与路由。")
                    : strip.mode === "global" ? qsTr("普通流量走默认出口，保留必要本地直连；专属分配暂不参与路由。")
                    : qsTr("国内规则命中使用 DIRECT；专属服务使用下方出口，其余流量走默认出口。")
                color: Theme.muted; font.pixelSize: Theme.fontSize(12)
            }
            SwirlText { visible: strip.mode === "rule"; text: "DIRECT"; color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; Accessible.name: qsTr("国内规则命中时直连") }
        }
    }
}
