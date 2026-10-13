import QtQuick
import QtQuick.Controls
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
    readonly property bool chosen: AppState.currentPage === pageId
    signal activated()
    property real selectionX:0
    property real selectionY:0
    property bool selectionReady:false
    function updateSelection() {
        if(!chosen || !selectionReady)return
        const target=entry.mapToItem(null,0,0)
        const old=SwirlMotion.navigationRect
        selectionX=old && !SwirlMotion.reduced ? old.x-target.x : 0
        selectionY=old && !SwirlMotion.reduced ? old.y-target.y : 0
        SwirlMotion.navigationRect=Qt.rect(target.x,target.y,width,height)
        settleX.restart();settleY.restart()
    }
    onChosenChanged: {
        if(!chosen && selectionReady) {
            const p=entry.mapToItem(null,selectionX,selectionY)
            SwirlMotion.navigationRect=Qt.rect(p.x,p.y,width,height)
        } else Qt.callLater(updateSelection)
    }
    Component.onCompleted:{selectionReady=true;Qt.callLater(updateSelection)}
    SwirlSpring {id:settleX;target:entry;property:"selectionX";to:0}
    SwirlSpring {id:settleY;target:entry;property:"selectionY";to:0;epsilon:0.1}
    implicitHeight:Theme.dp(44)
    implicitWidth: Theme.dp(compact ? 58 : 250)
    leftPadding:Theme.dp(10); rightPadding:Theme.dp(12)
    topPadding:0; bottomPadding:0
    hoverEnabled: true
    background: Rectangle {
        radius:Theme.navigationRadius
        color:entry.chosen?(entry.down?Theme.navigationPressed:Theme.navigationSelected):"transparent"
        antialiasing:true
        border.width:Theme.dp(entry.visualFocus?2:0)
        border.color:Theme.focusBorder
        transform:Translate{x:entry.selectionX;y:entry.selectionY}
    }
    contentItem: RowLayout {
        spacing:Theme.dp(10)
        SwirlIcon { name: entry.iconName; size:Theme.dp(20); color: Theme.text }
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
