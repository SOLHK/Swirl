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
    property bool clearGlass: false
    property int textPixelSize: 11
    property bool rounded: false
    function segmentStart(index) { return Math.round((width-Theme.dp(4))*index/Math.max(1,options.length)*Screen.devicePixelRatio)/Screen.devicePixelRatio }
    function segmentWidth(index) { return segmentStart(index+1)-segmentStart(index) }
    signal activated(int index, string value)
    implicitHeight:Theme.statusHeight; implicitWidth:Theme.dp(295)
    SwirlClearGlassSurface { anchors.fill:parent; elevated:false; radius:control.rounded ? height/2 : Theme.segmentedRadius }
    Rectangle {
        property real selectionPosition:control.currentIndex
        x:Theme.dp(2)+control.segmentStart(selectionPosition);y:Theme.dp(2)
        width:control.segmentWidth(control.currentIndex)
        height:control.height-Theme.dp(4)
        radius:control.rounded?height/2:Theme.segmentedSelectedRadius
        color:control.accentSelection?Theme.primaryControl:control.clearGlass?Theme.withAlpha("#FFFFFF",Theme.dark?0.14:0.72):control.rounded?Theme.buttonBase:Theme.segmentSelected
        border.width:0
        border.color:control.clearGlass?Theme.withAlpha(Theme.dark?"#FFFFFF":"#777777",Theme.dark?0.14:0.10):"transparent"
        Behavior on selectionPosition{enabled:!SwirlMotion.reduced;NumberAnimation{duration:SwirlMotion.switchDuration;easing.type:Easing.OutCubic}}
    }
    Row {
        anchors.fill: parent; anchors.margins:Theme.dp(2)
        Repeater {
            model: control.options
            delegate: SwirlMotionButton {
                required property int index
                required property var modelData
                width: control.segmentWidth(index); height: control.height-Theme.dp(4)
                hoverEnabled:true
                background: Rectangle {
                    radius:control.rounded ? height/2 : Theme.segmentedSelectedRadius
                    border.width:parent.activeFocus?Theme.dp(2):0;border.color:Theme.focusBorder
                    color:control.currentIndex!==index && parent.hovered?Theme.withAlpha(Theme.hover,0.5):"transparent"
                    Behavior on color{ColorAnimation{duration:SwirlMotion.hoverDuration}}
                }
                contentItem: SwirlText {
                    text: AppState.zh(String(modelData))
                    color:!control.enabled?Theme.muted:control.currentIndex===index&&control.accentSelection?"white":control.currentIndex===index?Theme.text:Theme.muted
                    leftPadding:control.optionIcons.length?Theme.dp(18):0
                    SwirlIcon{visible:control.optionIcons.length>index;name:control.optionIcons[index]||"link";size:Theme.dp(16);color:parent.color;x:Math.round((parent.width-parent.contentWidth)/2-Theme.dp(22));anchors.verticalCenter:parent.verticalCenter}
                    textRole:"button"
                    font.pixelSize:Theme.fontSize(control.textPixelSize); font.family:Theme.fontFamily
                    horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter
                }
                onClicked: { control.currentIndex = index; control.activated(index,String(modelData)) }
            }
        }
    }
}
