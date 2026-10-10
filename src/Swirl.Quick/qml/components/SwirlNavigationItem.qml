import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
Item {
    id: entry
    property string pageId: "overview"
    property string title: "总览"
    property string iconName: "home"
    property bool compact: false
    readonly property bool chosen: AppState.currentPage === entry.pageId
    signal activated()
    implicitHeight: 41
    implicitWidth: compact ? 58 : 221
    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: 8; anchors.rightMargin: 8
        radius: 12
        antialiasing: true
        color: entry.chosen ? Theme.selected : hover.containsMouse ? Theme.hover : "transparent"
        border.width: entry.chosen ? 1 : 0
        border.color: Theme.glassRim
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Rectangle {
            visible: entry.chosen
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 14; anchors.rightMargin: 14
            height: 1; color: Theme.glassGlint; opacity: 0.85
        }
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: entry.compact ? 23 : 21
        anchors.rightMargin: 16
        spacing: 12
        SwirlIcon {
            name: entry.iconName
            size: 18
            color: entry.chosen ? Theme.accent : Theme.muted
        }
        Text {
            visible: !entry.compact
            Layout.fillWidth: true
            text: entry.title
            color: entry.chosen ? Theme.text : Theme.muted
            font.pixelSize: 12
            font.family: "Microsoft YaHei UI"
            font.weight: entry.chosen ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
    }
    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: entry.activated()
        ToolTip.visible: entry.compact && containsMouse
        ToolTip.text: entry.title
    }
}
