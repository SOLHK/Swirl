import QtQuick
import QtQuick.Controls
import SwirlQuick
ComboBox {
    id: control
    implicitWidth: 146
    implicitHeight: 44
    hoverEnabled: true
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 17
    leftPadding: 15; rightPadding: 31
    contentItem: Text {
        text: control.displayText
        color: Theme.text
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        leftPadding: 4; rightPadding: 4
    }
    indicator: Canvas {
        id: chevron
        x: control.width-width-13; y: (control.height-height)/2
        width: 14; height: 14
        onPaint: {
            var ctx=getContext("2d")
            ctx.reset(); ctx.strokeStyle=Theme.muted
            ctx.lineWidth=1.65; ctx.lineCap="round"; ctx.lineJoin="round"
            ctx.beginPath(); ctx.moveTo(3,5); ctx.lineTo(7,9); ctx.lineTo(11,5); ctx.stroke()
        }
        Connections { target: Theme; function onMutedChanged() { chevron.requestPaint() } }
    }
    background: SwirlPillSurface {
        radius: Theme.pillRadius(height)
        antialiasing: true
        color: control.pressed ? Theme.selected : control.hovered ? Theme.material("floating") : Theme.material("field")
        border.width: 1
        border.color: control.activeFocus ? Theme.accent : Theme.glassRim
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: 13; anchors.rightMargin: 13
            anchors.top: parent.top; anchors.topMargin: 1
            height: 1; color: Theme.glassGlint; opacity: 0.65
        }
        Behavior on color { ColorAnimation { duration: Theme.motion } }
    }
    delegate: ItemDelegate {
        width: control.width
        height: 36
        text: String(modelData)
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: parent.text
            color: Theme.text; font.pixelSize: 17; font.family: "Microsoft YaHei UI"
            verticalAlignment: Text.AlignVCenter; leftPadding: 12
        }
        background: Rectangle {
            radius: 10; color: parent.highlighted ? Theme.selected : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.motion } }
        }
    }
    popup: Popup {
        y: control.height + 7
        width: control.width
        padding: 6
        implicitHeight: Math.min(290, contentItem.implicitHeight+12)
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion }
                NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: Theme.motion; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motion } }
        background: Rectangle {
            color: Theme.material("floating")
            radius: 16
            border.width: 1; border.color: Theme.glassRim
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }
}
