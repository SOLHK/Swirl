pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

Row {
    id: controls
    required property var targetWindow
    readonly property bool maximized: targetWindow.visibility === Window.Maximized
    width: Theme.dp(138)
    height: Theme.dp(32)
    Repeater {
        model: 3
        Button {
            id: button
            required property int index
            width: Theme.dp(46); height: controls.height
            hoverEnabled: true
            objectName: index === 0 ? "windowMinimizeButton" : index === 1 ? "windowMaximizeButton" : "windowCloseButton"
            Accessible.name: index === 0 ? qsTr("最小化") : index === 1 ? (controls.maximized ? qsTr("还原") : qsTr("最大化")) : qsTr("关闭")
            property bool motionInitialized:false
            property color shownColor:targetColor
            readonly property color targetColor:index===2 && (hovered || down)?(down?"#C42B1C":"#E81123")
                :down?Theme.interactionPressed:hovered?Theme.interactionHover:"transparent"
            readonly property bool animate:visible && controls.targetWindow.visible && controls.targetWindow.visibility!==Window.Minimized && !SwirlMotion.reduced
            readonly property bool moving:backgroundTravel.running
            function finishMotion(){if(motionInitialized){backgroundTravel.stop();shownColor=targetColor}}
            function retargetMotion(){
                if(!motionInitialized)return
                if(!animate){finishMotion();return}
                backgroundTravel.stop();backgroundTravel.from=shownColor;backgroundTravel.to=targetColor
                if(shownColor!==targetColor)backgroundTravel.start()
            }
            onTargetColorChanged:retargetMotion()
            onAnimateChanged:if(!animate)finishMotion()
            Component.onCompleted:{motionInitialized=true;finishMotion()}
            ColorAnimation {id:backgroundTravel;target:button;property:"shownColor";duration:SwirlMotion.hoverDuration}
            background: Rectangle {
                color: button.shownColor
                border.width: button.visualFocus ? 1 / Screen.devicePixelRatio : 0
                border.color: Theme.focusBorder
            }
            contentItem: Item {
                readonly property color ink: button.index === 2 && button.hovered ? "white" : controls.targetWindow.active ? Theme.text : Theme.muted
                readonly property real stroke: Math.max(1, Math.round(Screen.devicePixelRatio)) / Screen.devicePixelRatio
                Item {
                    anchors.centerIn: parent
                    width: Theme.dp(10); height: Theme.dp(10)
                    Rectangle {
                        visible: button.index === 0
                        width: parent.width; height: button.contentItem.stroke
                        anchors.verticalCenter: parent.verticalCenter; color: button.contentItem.ink
                    }
                    Rectangle {
                        visible: button.index === 1
                        x: controls.maximized ? Theme.dp(2) : 0
                        width: controls.maximized ? Theme.dp(8) : parent.width; height: width
                        color: "transparent"; border.color: button.contentItem.ink; border.width: button.contentItem.stroke
                    }
                    Rectangle {
                        visible: button.index === 1 && controls.maximized
                        y: Theme.dp(2); width: Theme.dp(8); height: width
                        color: Theme.canvas; border.color: button.contentItem.ink; border.width: button.contentItem.stroke
                    }
                    Repeater {
                        model: button.index === 2 ? 2 : 0
                        Rectangle {
                            required property int index
                            anchors.centerIn: parent
                            width: Theme.dp(13); height: button.contentItem.stroke
                            rotation: index === 0 ? 45 : -45
                            antialiasing: true; color: button.contentItem.ink
                        }
                    }
                }
            }
            onClicked: {
                if (index === 0) controls.targetWindow.showMinimized()
                else if (index === 1) {
                    if (controls.maximized) controls.targetWindow.showNormal()
                    else controls.targetWindow.showMaximized()
                } else controls.targetWindow.close()
            }
            ToolTip.visible: hovered && !previewCaptureMode
            ToolTip.delay: 650
            ToolTip.text: Accessible.name
        }
    }
}
