import QtQuick
import QtQuick.Layouts
import SwirlQuick
SwirlGlassPanel {
    id:card
    cornerRadius:Theme.cardRadius
    property string label:"下载速度"
    property string value:"0 KB/s"
    property string secondary:""
    property string iconName:"download"
    property color valueColor:Theme.text
    property color chartColor:Theme.accent
    property bool bars:false
    implicitHeight:Theme.dp(143); implicitWidth:Theme.dp(175)
    RowLayout {
        x:Theme.dp(14); y:Theme.dp(10); width:parent.width-Theme.dp(28); spacing:Theme.dp(18)
        Rectangle {
            Layout.preferredWidth:Theme.dp(46); Layout.preferredHeight:Theme.dp(46); radius:Math.min(width,height)/2; color:Theme.withAlpha(card.chartColor,0.09)
            SwirlIcon { anchors.centerIn:parent; name:card.iconName; size:Theme.dp(27); color:card.chartColor }
        }
        Text { text:card.label; color:Theme.muted; font.pixelSize:Theme.fontSize(17); Layout.fillWidth:true; elide:Text.ElideRight }
    }
    Text { x:Theme.dp(25); y:Theme.dp(61); width:parent.width-Theme.dp(40); text:card.value; color:card.valueColor; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(32); font.weight:Font.DemiBold; elide:Text.ElideRight }
    SwirlSparkline { x:parent.width*0.31; y:parent.height-Theme.dp(54); width:parent.width*0.63; height:Theme.dp(43); lineColor:card.chartColor; bars:card.bars }
}
