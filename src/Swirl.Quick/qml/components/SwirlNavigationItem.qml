import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
Button {
    id: entry
    property string pageId: "overview"
    property string title: "总览"
    property string iconName: "home"
    property bool compact: false
    readonly property bool chosen: AppState.currentPage === pageId
    signal activated()
    implicitHeight: chosen ? 48 : 38
    implicitWidth: compact ? 58 : 217
    leftPadding:20; rightPadding:16
    hoverEnabled:true
    background: SwirlPillSurface {
        selected: entry.chosen; hovered:entry.hovered; pressed:entry.down
        subtleShadow:entry.chosen
        color:entry.down ? Theme.pressed : entry.chosen ? Theme.selected : entry.hovered ? Theme.hover : "transparent"
        border.color:entry.activeFocus ? Theme.focusBorder : entry.chosen ? Theme.controlBorder : "transparent"
    }
    contentItem: RowLayout {
        spacing:25
        SwirlIcon { name:entry.iconName; size:26; color:entry.chosen ? Theme.accent : Theme.muted }
        Text {
            visible:!entry.compact; Layout.fillWidth:true
            text:entry.title; color:entry.chosen ? Theme.accent : Theme.muted
            font.pixelSize:18; font.family:Theme.fontFamily; font.weight:entry.chosen ? Font.DemiBold : Font.Normal
            elide:Text.ElideRight
        }
    }
    onClicked:activated()
    Accessible.name: title
    ToolTip.visible: compact && hovered
    ToolTip.text: title
}
