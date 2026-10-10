import QtQuick
import QtQuick.Layouts
import SwirlQuick
SwirlGlassPanel {
    id:card
    property string label:"下载速度"
    property string value:"0 KB/s"
    property string secondary:""
    property string iconName:"download"
    property color valueColor:Theme.text
    property color chartColor:Theme.accent
    property bool bars:false
    implicitHeight:143; implicitWidth:175
    RowLayout {
        x:14; y:10; width:parent.width-28; spacing:18
        Rectangle {
            width:46; height:46; radius:Theme.pillRadius(height); color:Theme.withAlpha(card.chartColor,0.09)
            SwirlIcon { anchors.centerIn:parent; name:card.iconName; size:27; color:card.chartColor }
        }
        Text { text:card.label; color:Theme.muted; font.pixelSize:17; Layout.fillWidth:true; elide:Text.ElideRight }
    }
    Text { x:25; y:61; width:parent.width-40; text:card.value; color:card.valueColor; font.family:"Segoe UI"; font.pixelSize:32; font.weight:Font.DemiBold; elide:Text.ElideRight }
    SwirlSparkline { x:parent.width*0.31; y:parent.height-44; width:parent.width*0.63; height:34; lineColor:card.chartColor; bars:card.bars }
}
