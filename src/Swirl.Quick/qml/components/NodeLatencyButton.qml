import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"

SwirlMotionButton {
    id:control
    property var record:({})
    objectName:"nodeLatency-"+String(record.id||"")
    readonly property bool pending:Boolean(record.testPending)
    readonly property bool measured:Boolean(record.testAvailable)
    readonly property color tint:measured?Theme.green:Theme.accent
    text:pending?qsTr("检测中"):measured?String(record.exitLatency)+" ms":String(record.probeStatusText||qsTr("测延迟"))
    implicitWidth:Theme.dp(104);implicitHeight:Theme.dp(32)
    padding:Theme.dp(8);hoverEnabled:true;enabled:!pending
    Accessible.name:String(record.name||"")+qsTr("，延迟 %1，点击重新检测此节点").arg(text)
    background:Rectangle {
        radius:height/2;antialiasing:true
        gradient:Gradient {
            GradientStop {position:0;color:Theme.withAlpha(control.tint,control.down?0.23:control.hovered?0.19:0.12)}
            GradientStop {position:0.55;color:Theme.withAlpha(control.tint,0.06)}
            GradientStop {position:1;color:Theme.withAlpha(control.tint,0.15)}
        }
        border.width:control.visualFocus?Theme.dp(2):Theme.dp(1)
        border.color:Theme.withAlpha(control.tint,control.visualFocus?0.85:0.26)
        SwirlLiquidGlass {anchors.fill:parent;cornerRadius:parent.radius;interaction:control.hovered||control.down?1:0}
        Rectangle {x:parent.width*0.19;y:Theme.dp(1);width:parent.width*0.62;height:Theme.dp(1);radius:height/2;color:Theme.glassHighlight;opacity:Theme.dark?0.35:0.85}
    }
    contentItem:RowLayout {
        spacing:Theme.dp(4)
        SwirlIcon {name:control.pending?"activity":"refresh";size:Theme.dp(12);color:Theme.text;Accessible.ignored:true}
        SwirlText {objectName:"nodeLatencyValue";Layout.fillWidth:true;text:control.text;textFormat:Text.PlainText;horizontalAlignment:Text.AlignHCenter;elide:Text.ElideRight;color:Theme.text;font.pixelSize:Theme.fontSize(12);font.weight:Font.DemiBold;font.features:({"tnum":1})}
    }
    SwirlToolTip {visible:control.hovered;text:qsTr("请求发出到响应头返回的时间；HTTPS 会先完成 TLS。点击仅刷新此节点。");delay:600}
}
