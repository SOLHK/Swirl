import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
Item {
    id: control
    property var options: ["下载", "上传", "总流量"]
    property var optionIcons: []
    property int currentIndex: 0
    property bool accentSelection: false
    property int textPixelSize: 11
    property bool rounded: false
    signal activated(int index, string value)
    implicitHeight:Theme.dp(25); implicitWidth:Theme.dp(295)
    Rectangle { anchors.fill:parent; radius:control.rounded ? height/2 : Theme.segmentedRadius; color:control.rounded?(control.accentSelection?Theme.buttonBase:Theme.surface):Theme.material("field"); border.width:control.rounded?0:Theme.borderWidth; border.color:Theme.border }
    Rectangle {
        x:(control.rounded?0:Theme.dp(2))+control.currentIndex*width;y:control.rounded?0:Theme.dp(2)
        width:(control.width-(control.rounded?0:Theme.dp(4)))/Math.max(1,control.options.length)
        height:control.height-(control.rounded?0:Theme.dp(4))
        radius:control.rounded?height/2:Theme.segmentedSelectedRadius
        color:control.accentSelection?Theme.primaryControl:control.rounded?Theme.buttonBase:Theme.segmentSelected
        Behavior on x{enabled:!SwirlMotion.reduced;NumberAnimation{duration:SwirlMotion.switchDuration;easing.type:Easing.OutCubic}}
    }
    Row {
        anchors.fill: parent; anchors.margins:control.rounded?0:Theme.dp(2)
        Repeater {
            model: control.options
            delegate: SwirlMotionButton {
                required property int index
                required property var modelData
                width: (control.width-(control.rounded?0:Theme.dp(4))) / control.options.length; height: control.height-(control.rounded?0:Theme.dp(4))
                hoverEnabled:true
                background: Rectangle {
                    radius:control.rounded ? height/2 : Theme.segmentedSelectedRadius
                    color:control.currentIndex!==index && parent.hovered?Theme.withAlpha(Theme.hover,0.5):"transparent"
                    Behavior on color{ColorAnimation{duration:SwirlMotion.hoverDuration}}
                }
                contentItem: Text {
                    text: AppState.zh(String(modelData))
                    color:control.currentIndex===index&&control.accentSelection?"white":control.rounded?Theme.text:control.currentIndex===index?"white":Theme.muted
                    leftPadding:control.optionIcons.length?Theme.dp(18):0
                    SwirlIcon{visible:control.optionIcons.length>index;name:control.optionIcons[index]||"link";size:Theme.dp(16);color:parent.color;x:(parent.width-parent.contentWidth)/2-Theme.dp(22);anchors.verticalCenter:parent.verticalCenter}
                    font.pixelSize:Theme.fontSize(control.textPixelSize); font.family:Theme.fontFamily
                    horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter
                }
                onClicked: { control.currentIndex = index; control.activated(index,String(modelData)) }
            }
        }
    }
}
