import QtQuick
import QtQuick.Layouts
import SwirlQuick
SwirlGlassPanel {
    id:card
    property string label:"Download"
    property string value:"0 MB/s"
    property string secondary:"In this session"
    property string iconName:"activity"
    property color valueColor:Theme.text
    implicitHeight:136
    implicitWidth:175
    ColumnLayout {
        anchors.fill:parent; anchors.margins:18
        spacing:9
        RowLayout {
            Layout.fillWidth:true
            SwirlIcon { name:card.iconName; size:16; color:Theme.muted }
            Text { text:card.label; font.pixelSize:12; color:Theme.muted; Layout.fillWidth:true }
        }
        Text {
            text:card.value; color:card.valueColor
            font.pixelSize:24; font.weight:Font.DemiBold
            font.family:"Segoe UI"
            elide:Text.ElideRight
            Layout.fillWidth:true
        }
        Text { text:card.secondary; font.pixelSize:11; color:Theme.muted; Layout.fillWidth:true; elide:Text.ElideRight }
    }
}