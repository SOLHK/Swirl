import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
Button {
    id:row
    property string iconName:""
    property string title:""
    property bool arrow:true
    implicitHeight:36
    padding:0; hoverEnabled:true
    background:Rectangle {
        color:row.down ? Theme.selected : row.hovered ? Theme.hover : "transparent"
        radius:Theme.controlRadius
        Rectangle { width:parent.width-52; x:52; height:1; color:Theme.border; opacity:0.65 }
    }
    contentItem:RowLayout {
        spacing:24
        SwirlIcon { name:row.iconName; size:25 }
        Text { text:row.title; color:Theme.muted; font.pixelSize:17; Layout.fillWidth:true; elide:Text.ElideRight }
        SwirlIcon { visible:row.arrow; name:"chevron-right"; size:17 }
    }
    Accessible.name:title
}
