pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
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
    property bool rounded: true
    function segmentStart(index) { return Math.round((width-Theme.dp(4))*index/Math.max(1,options.length)*Screen.devicePixelRatio)/Screen.devicePixelRatio }
    function segmentWidth(index) { return segmentStart(index+1)-segmentStart(index) }
    signal activated(int index, string value)
    implicitHeight:Theme.statusHeight; implicitWidth:Theme.dp(295)
    Rectangle { anchors.fill:parent; radius:control.rounded ? Theme.pillRadius(height) : Theme.segmentedRadius; color:Theme.buttonBase; border.width:Theme.increaseContrast?Theme.borderWidth:0; border.color:Theme.text }
    Rectangle {
        property real selectionPosition:control.currentIndex
        x:Theme.dp(2)+control.segmentStart(selectionPosition);y:Theme.dp(2)
        width:control.segmentWidth(control.currentIndex)
        height:control.height-Theme.dp(4)
        radius:control.rounded?Theme.pillRadius(height):Theme.segmentedSelectedRadius
        color:control.accentSelection?Theme.primaryButton:Theme.segmentSelected
        opacity:control.enabled?1:0.45
        border.width:0
        border.color:Theme.controlBorder
        Behavior on selectionPosition{enabled:!SwirlMotion.reduced;NumberAnimation{duration:SwirlMotion.switchDuration;easing.type:Easing.OutCubic}}
    }
    Row {
        anchors.fill: parent; anchors.margins:Theme.dp(2)
        Repeater {
            model: control.options
            delegate: SwirlMotionButton {
                id: segment
                required property int index
                required property var modelData
                width: control.segmentWidth(segment.index); height: control.height-Theme.dp(4)
                hoverEnabled:true
                background: Rectangle {
                    radius:control.rounded ? Theme.pillRadius(height) : Theme.segmentedSelectedRadius
                    border.width:segment.visualFocus?Theme.borderWidth:0;border.color:control.currentIndex===segment.index&&control.accentSelection?Theme.primaryButtonText:Theme.text
                    color:control.currentIndex!==segment.index && segment.hovered?Theme.withAlpha(Theme.hover,0.5):"transparent"
                    Behavior on color{enabled:!SwirlMotion.reduced;ColorAnimation{duration:SwirlMotion.hoverDuration}}
                }
                contentItem: SwirlText {
                    text: AppState.zh(String(segment.modelData))
                    color:!control.enabled?Theme.muted:control.currentIndex===segment.index&&control.accentSelection?Theme.primaryButtonText:control.currentIndex===segment.index?Theme.text:Theme.muted
                    leftPadding:control.optionIcons.length?Theme.dp(18):0
                    SwirlIcon{visible:control.optionIcons.length>segment.index;name:control.optionIcons[segment.index]||"link";size:Theme.dp(16);color:parent.color;x:Math.round((parent.width-parent.contentWidth)/2-Theme.dp(22));anchors.verticalCenter:parent.verticalCenter}
                    textRole:"button"
                    font.pixelSize:Theme.fontSize(control.textPixelSize); font.family:Theme.fontFamily
                    horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter
                }
                Accessible.role: Accessible.RadioButton
                Accessible.name: String(segment.modelData)
                Accessible.checked: control.currentIndex === segment.index
                onClicked: { control.currentIndex = segment.index; control.activated(segment.index,String(segment.modelData)) }
            }
        }
    }
}
