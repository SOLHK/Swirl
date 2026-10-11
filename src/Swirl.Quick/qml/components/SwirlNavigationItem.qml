import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
Button {
    id: entry
    property string pageId: "overview"
    property string title: "总览"
    property string iconName: "home"
    property bool compact: false
    readonly property bool chosen: AppState.currentPage === pageId
    signal activated()
    implicitHeight: 42
    implicitWidth: compact ? 58 : 250
    leftPadding: 16; rightPadding: 12
    hoverEnabled: true
    background: Rectangle {
        radius: 8
        color: entry.down ? Theme.pressed : entry.chosen ? Theme.selected : entry.hovered ? Theme.hover : "transparent"
        border.width: entry.activeFocus ? 2 : 0
        border.color: Theme.focusBorder
        Behavior on color { ColorAnimation { duration: Theme.motion } }
    }
    contentItem: RowLayout {
        spacing: 22
        SwirlIcon { name: entry.iconName; size: 26; color: entry.chosen ? Theme.navigationAccent : Theme.text }
        Text {
            visible: !entry.compact; Layout.fillWidth: true
            text: entry.title; color: entry.chosen ? Theme.navigationAccent : Theme.text
            font.pixelSize: 18; font.family: Theme.fontFamily
            font.weight: entry.chosen ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
    }
    onClicked: activated()
    Accessible.name: title
    Accessible.role: Accessible.ListItem
    Accessible.selectable: true
    Accessible.selected: chosen
    ToolTip.visible: hovered && compact
    ToolTip.text: title
}
