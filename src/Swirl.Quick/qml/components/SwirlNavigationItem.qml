import QtQuick
import QtQuick.Layouts
import SwirlQuick
Item {
    id:entry
    property string pageId:"overview"
    property string title:"Overview"
    property string iconName:"home"
    property bool compact:false
    signal activated()
    implicitHeight:39
    implicitWidth:compact?58:221
    Rectangle {
        anchors.fill:parent
        anchors.leftMargin:6; anchors.rightMargin:6
        radius:10
        color:AppState.currentPage===entry.pageId?Theme.selected:
              hover.containsMouse?Theme.hover:"transparent"
        Behavior on color { ColorAnimation { duration:Theme.motion } }
    }
    RowLayout {
        anchors.fill:parent
        anchors.leftMargin:20; anchors.rightMargin:16
        spacing:13
        SwirlIcon {
            name:entry.iconName
            size:18
            color:AppState.currentPage===entry.pageId?Theme.accent:Theme.muted
        }
        Text {
            visible:!entry.compact
            Layout.fillWidth:true
            text:entry.title
            color:AppState.currentPage===entry.pageId?Theme.text:Theme.muted
            font.pixelSize:13
            font.weight:AppState.currentPage===entry.pageId?Font.DemiBold:Font.Normal
            elide:Text.ElideRight
        }
    }
    MouseArea {
        id:hover
        anchors.fill:parent
        hoverEnabled:true
        onClicked:entry.activated()
        ToolTip.visible:entry.compact&&containsMouse
        ToolTip.text:entry.title
    }
}