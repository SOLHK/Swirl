pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"

Item {
    id: actions
    required property var record
    property bool editable: false
    property bool testable: false
    signal favoriteRequested()
    signal detailsRequested()
    signal editRequested()
    signal testRequested()
    signal copyRequested()
    function openMenu() { menu.showAt() }
    function closeMenu() { menu.close() }
    RowLayout {
        anchors.fill: parent; spacing: 0
        SubscriptionAction {
            objectName: "nodeRowFavorite-" + actions.record.id
            Layout.preferredWidth: Theme.dp(44); Layout.fillHeight: true
            iconName: actions.record.favorite ? "star-filled" : "star"
            Accessible.name: (actions.record.favorite ? qsTr("取消收藏 %1") : qsTr("收藏 %1")).arg(actions.record.name)
            Accessible.role: Accessible.CheckBox; Accessible.checked: !!actions.record.favorite
            tooltip: Accessible.name
            onClicked: actions.favoriteRequested()
        }
        SubscriptionAction {
            id: more
            objectName: "nodeRowMore-" + actions.record.id
            Layout.preferredWidth: Theme.dp(44); Layout.fillHeight: true
            iconName: "ellipsis"
            Accessible.name: qsTr("%1 的更多操作").arg(actions.record.name)
            tooltip: Accessible.name
            onClicked: actions.openMenu()
        }
    }
    component NodeMenuItem: MenuItem {
        id: option
        implicitHeight: Math.max(Theme.dp(36), contentItem.implicitHeight + Theme.dp(12))
        leftPadding: Theme.dp(12); rightPadding: Theme.dp(12)
        contentItem: SwirlText { text: option.text; color: option.enabled ? Theme.text : Theme.muted; font.pixelSize: Theme.fontSize(12); verticalAlignment: Text.AlignVCenter }
        background: SwirlControlSurface {quiet:true;hovered:option.hovered;pressed:option.down;focused:option.visualFocus;selected:option.highlighted;controlEnabled:option.enabled}
    }
    SwirlContextMenu {
        id: menu
        objectName: "nodeRowMenu-" + actions.record.id
        popupType: Popup.Item; parent: more; x: more.width - width; y: more.height; transformOrigin: Item.TopRight
        items: []; implicitWidth: Theme.dp(190)
        NodeMenuItem { objectName: "nodeRowDetails-" + actions.record.id; text: qsTr("查看详情"); onTriggered: actions.detailsRequested() }
        NodeMenuItem { objectName: "nodeRowTest-" + actions.record.id; text: qsTr("测试此节点"); enabled: actions.testable; onTriggered: actions.testRequested() }
        NodeMenuItem { objectName: "nodeRowCopy-" + actions.record.id; text: qsTr("复制安全信息"); onTriggered: actions.copyRequested() }
        NodeMenuItem { objectName: "nodeRowEdit-" + actions.record.id; text: qsTr("编辑节点"); enabled: actions.editable; onTriggered: actions.editRequested() }
    }
}
