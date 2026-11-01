import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"
SwirlMotionButton {
    id: entry
    objectName:"nav-"+pageId
    property string pageId: "overview"
    property string title: "总览"
    property string iconName: "home"
    property bool compact: false
    readonly property bool chosen: AppState.sidebarPage === pageId
    signal activated()
    property var selectionOwner:null
    Component.onCompleted:if(selectionOwner)selectionOwner.registerEntry(entry)
    Component.onDestruction:if(selectionOwner)selectionOwner.unregisterEntry(entry)
    implicitHeight:Theme.sidebarRowHeight
    implicitWidth: Theme.dp(compact ? 58 : 180)
    leftPadding:Theme.dp(8); rightPadding:Theme.dp(10)
    topPadding:0; bottomPadding:0
    hoverEnabled: true
    background: SwirlControlSurface {
        radius:Theme.sidebarRowRadius
        quiet:true
        hovered:entry.hovered
        pressed:entry.down
        focused:entry.visualFocus
        controlEnabled:entry.enabled
        color:!entry.enabled || entry.chosen ? "transparent" : entry.down ? Theme.withAlpha(Theme.text,0.05) : entry.hovered ? Theme.withAlpha(Theme.text,0.025) : "transparent"
    }
    contentItem: RowLayout {
        opacity:entry.enabled?1:Theme.disabledOpacity
        spacing:Theme.dp(10)
        SwirlIcon { name: "nav-"+entry.pageId; size:Theme.dp(18); color:entry.chosen?Theme.navigationAccent:entry.enabled && entry.hovered?Theme.text:Theme.muted }
        SwirlText {renderType:Text.NativeRendering;
            textRole: "navigation"
            visible: !entry.compact; Layout.fillWidth: true
            text: entry.title; color: Theme.text
            font.pixelSize:Theme.fontSize(13); font.family: Theme.fontFamily
            font.weight:entry.chosen?Font.DemiBold:Font.Medium
            elide: Text.ElideRight
        }
    }
    onClicked: activated()
    Accessible.name: title
    Accessible.role: Accessible.ListItem
    Accessible.selectable: true
    Accessible.selected: chosen

}
