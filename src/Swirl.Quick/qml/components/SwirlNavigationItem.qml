import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
Button {
    id: entry
    objectName:"nav-"+pageId
    property string pageId: "overview"
    property string title: "总览"
    property string iconName: "home"
    property bool compact: false
    readonly property bool chosen: AppState.currentPage === pageId
    signal activated()
    implicitHeight:Theme.dp(33)
    implicitWidth: Theme.dp(compact ? 58 : 250)
    leftPadding:Theme.dp(16); rightPadding:Theme.dp(12)
    topPadding:0; bottomPadding:0
    hoverEnabled: true
    background: Rectangle {
        radius: Theme.roundedRadius(width,height)
        // Selection is exclusive; hover on the previous row must not look selected.
        color: entry.chosen ? (entry.down ? Theme.navigationPressed : Theme.navigationSelected) : "transparent"
        antialiasing:true
        border.width: Theme.dp(entry.visualFocus ? 2 : 0)
        border.color: Theme.focusBorder
    }
    contentItem: RowLayout {
        spacing:Theme.dp(18)
        SwirlIcon { name: entry.iconName; size:Theme.dp(22); color: Theme.text }
        Text {
            visible: !entry.compact; Layout.fillWidth: true
            text: entry.title; color: Theme.text
            font.pixelSize:Theme.fontSize(17); font.family: Theme.fontFamily
            font.weight: Font.Normal
            elide: Text.ElideRight
        }
    }
    onClicked: activated()
    Accessible.name: title
    Accessible.role: Accessible.ListItem
    Accessible.selectable: true
    Accessible.selected: chosen
    ToolTip.visible: hovered && compact && !previewCaptureMode
    ToolTip.text: title
}
