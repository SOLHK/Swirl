import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"

SwirlToolbarButton {
    id: control
    property string label: ""
    property string tone: "neutral"
    property string detail: ""
    property string activityPhase: ""
    property bool proxyWing: false
    implicitWidth: Math.ceil(group.implicitWidth + leftPadding + rightPadding)
    Accessible.name: label
    Accessible.description: detail
    contentItem: Item {
        implicitWidth: group.implicitWidth
        implicitHeight: group.implicitHeight
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        RowLayout {
            id: group
            objectName: "statusCapsuleContentGroup"
            anchors.centerIn: parent
            spacing: Theme.dp(7)
            Item {
                objectName: "statusCapsuleAccessory"
                Layout.preferredWidth: Theme.toolbarIconSize
                Layout.preferredHeight: Theme.toolbarIconSize
                Rectangle {
                    anchors.centerIn: parent
                    width: Theme.dp(6); height: width; radius: width / 2
                    color: control.tone === "success" ? Theme.successText
                        : control.tone === "warning" ? Theme.orange : Theme.muted
                    opacity: control.activityPhase === "pending" ? 0.55 : 1
                    Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
                }
            }
            SwirlText {
                objectName: "statusCapsuleLabel"
                text: control.label; textRole: "smallLabel"; tabularFigures: true
                font.pixelSize: Theme.toolbarFontSize; font.weight: Theme.bodyFontWeight
                color: control.tone === "success" ? Theme.successText : Theme.text
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
    HoverHandler { enabled: control.enabled; cursorShape: Qt.PointingHandCursor }
}
