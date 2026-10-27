pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

ColumnLayout {
    id: types
    property bool editable: true
    readonly property var choices: [
        {key: "manual", name: qsTr("手动选择"), icon: "pin", detail: qsTr("固定使用你选定的节点，随时切换成员。")},
        {key: "url_test", name: qsTr("自动测速"), icon: "gauge", detail: qsTr("定期检测候选节点，按检测结果选择出口。")},
        {key: "fallback", name: qsTr("故障转移"), icon: "shield", detail: qsTr("按候选顺序使用健康节点，故障时接续。")},
        {key: "load_balance", name: qsTr("负载均衡"), icon: "layers", detail: qsTr("将新连接分配给多个候选，保持服务出口稳定。")}
    ]
    signal createRequested(string strategy, Item source)
    spacing: Theme.dp(12)
    SwirlText { text: qsTr("选择一种出口工作方式"); color: Theme.text; font.pixelSize: Theme.fontSize(17); font.weight: Font.DemiBold }
    SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("把节点组织成可复用的出口，再分配给默认策略或专属服务。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
    GridLayout {
        Layout.fillWidth: true; columns: 2; columnSpacing: Theme.dp(10); rowSpacing: Theme.dp(10)
        Repeater {
            model: types.choices
            delegate: SwirlMotionButton {
                id: choice
                required property var modelData
                objectName: "createPolicyGroup-" + modelData.key
                Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; Layout.preferredHeight: Theme.dp(104)
                enabled: types.editable; hoverEnabled: true; padding: Theme.dp(14)
                Accessible.name: qsTr("创建%1策略组").arg(modelData.name)
                Accessible.description: modelData.detail
                background: Rectangle { radius: Theme.dp(12); color: choice.down ? Theme.pressed : choice.hovered ? Theme.hover : Theme.buttonBase; border.width: choice.visualFocus ? Theme.borderWidth : 0; border.color: Theme.text; Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } } }
                contentItem: ColumnLayout {
                    spacing: Theme.dp(8)
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(8)
                        SwirlIcon { name: choice.modelData.icon; size: Theme.dp(18); color: Theme.text; Accessible.ignored: true }
                        SwirlText { Layout.fillWidth: true; text: choice.modelData.name; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                        SwirlIcon { name: "plus"; size: Theme.dp(14); color: Theme.muted; Accessible.ignored: true }
                    }
                    SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: choice.modelData.detail; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                }
                onClicked: types.createRequested(modelData.key, choice)
            }
        }
    }
    SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("选择候选节点并保存，再分配给默认出口或专属服务；也支持嵌套策略组。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
}
