import QtQuick
import SwirlQuick
Item {
    id: control
    property var options: ["下载", "上传", "详细数据"]
    property int currentIndex: 0
    signal activated(int index, string value)
    implicitHeight: 38
    implicitWidth: 320
    Rectangle {
        anchors.fill: parent
        radius: 14
        color: Theme.material("field")
        border.width: 1
        border.color: Theme.glassRim
    }
    Row {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 2
        Repeater {
            model: control.options
            delegate: Item {
                width: Math.max(1, (control.width - 8 - (control.options.length-1)*2) / control.options.length)
                height: parent.height
                Rectangle {
                    anchors.fill: parent
                    radius: 11
                    color: control.currentIndex === index ? Theme.material("floating") :
                           hit.containsMouse ? Theme.hover : "transparent"
                    border.width: control.currentIndex === index ? 1 : 0
                    border.color: Theme.glassRim
                    Behavior on color { ColorAnimation { duration: Theme.motion } }
                }
                Text {
                    anchors.centerIn: parent
                    text: String(modelData)
                    color: control.currentIndex === index ? Theme.text : Theme.muted
                    font.pixelSize: 11
                    font.weight: control.currentIndex === index ? Font.DemiBold : Font.Normal
                    font.family: "Microsoft YaHei UI"
                }
                MouseArea {
                    id: hit
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        control.currentIndex = index
                        control.activated(index, String(modelData))
                    }
                }
            }
        }
    }
}
