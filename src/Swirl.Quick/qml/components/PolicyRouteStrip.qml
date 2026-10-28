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
    color: Theme.surface
    radius: Theme.dp(16)
    implicitHeight: body.implicitHeight + Theme.dp(32)

    ColumnLayout {
        id: body
        anchors.fill: parent; anchors.margins: Theme.dp(16); spacing: Theme.dp(10)
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(12)
            ColumnLayout {
                Layout.preferredWidth: Theme.dp(148); Layout.fillWidth: false; spacing: Theme.dp(3)
                SwirlText { text: qsTr("默认策略"); color: Theme.text; font.pixelSize: Theme.fontSize(18); font.weight: Font.DemiBold }
                SwirlText { Layout.fillWidth: true; text: strip.mode === "global" ? qsTr("普通流量") : strip.mode === "direct" ? qsTr("已保存的代理出口") : qsTr("未单独分配的流量"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
            }
            SubscriptionAction {
                id: choose
                objectName: "defaultPolicyTarget"
                Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredHeight: Theme.dp(48)
                enabled: strip.editable
                text: Policy.targetName(strip.target, strip.targetOptions)
                tooltip: qsTr("更换出口：%1").arg(text)
                Accessible.name: qsTr("更换默认策略出口，当前：%1").arg(text)
                leftPadding: Theme.pillRadius(height)
                rightPadding: Theme.pillRadius(height)
                topPadding: Theme.dp(4)
                bottomPadding: Theme.dp(4)
                background: SwirlControlSurface {
                    objectName: "defaultPolicyTargetSurface"
                    hovered: choose.hovered
                    pressed: choose.down
                    focused: choose.visualFocus
                    controlEnabled: choose.enabled
                }
                contentItem: RowLayout {
                    spacing: Theme.dp(10)
                    opacity: choose.enabled ? 1 : Theme.disabledOpacity
                    SwirlIcon { name: strip.target.kind === "group" ? "layers" : "route"; size: Theme.dp(19); color: Theme.muted; Accessible.ignored: true }
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(3)
                        SwirlText { objectName: "defaultPolicyTargetText"; Layout.fillWidth: true; Layout.minimumWidth: 0; text: choose.text; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold; elide: Text.ElideRight }
                        SwirlText { objectName: "defaultPolicySource"; Layout.fillWidth: true; Layout.minimumWidth: 0; text: strip.sourceLabel || qsTr("选择节点或策略组"); textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                    }
                    SwirlText { text: qsTr("更换出口"); color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.Medium; Accessible.ignored: true }
                    SwirlIcon { name: "chevron-right"; rotation: 90; size: Theme.dp(18); color: Theme.text; Accessible.ignored: true }
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
                Layout.fillWidth: true; Layout.alignment: Qt.AlignBaseline; wrapMode: Text.Wrap
                text: strip.mode === "direct" ? qsTr("直连模式：受接管流量直接出站，以下分配暂不参与路由。")
                    : strip.mode === "global" ? qsTr("普通流量走默认出口，保留必要本地直连；专属分配暂不参与路由。")
                    : qsTr("国内规则命中使用 DIRECT；专属服务使用下方出口，其余流量走默认出口。")
                color: Theme.muted; font.pixelSize: Theme.fontSize(12)
            }
            SwirlText { visible: strip.mode === "rule"; Layout.alignment: Qt.AlignBaseline; text: "DIRECT"; color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; Accessible.name: qsTr("国内规则命中时直连") }
        }
    }
}
