import QtQuick
import QtQuick.Controls
import SwirlQuick
Item {
    id: control
    property var options: ["下载", "上传", "总流量"]
    property int currentIndex: 0
    property bool accentSelection: false
    signal activated(int index, string value)
    implicitHeight: 40; implicitWidth: 295
    Rectangle { anchors.fill:parent; radius:Theme.pillRadius(height); color:Theme.material("field") }
    Row {
        anchors.fill: parent
        Repeater {
            model: control.options
            delegate: Button {
                required property int index
                required property var modelData
                width: control.width / control.options.length; height: control.height
                hoverEnabled:true
                background: SwirlPillSurface {
                    visible: control.currentIndex === index || parent.hovered
                    primary: control.accentSelection && control.currentIndex === index
                    hovered: parent.hovered
                    subtleShadow: control.currentIndex === index
                }
                contentItem: Text {
                    text: String(modelData)
                    color: control.currentIndex === index ? control.accentSelection ? "white" : Theme.accent : Theme.muted
                    font.pixelSize: 15; font.family:Theme.fontFamily
                    horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter
                }
                onClicked: { control.currentIndex = index; control.activated(index,String(modelData)) }
            }
        }
    }
}
