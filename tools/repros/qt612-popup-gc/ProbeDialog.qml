pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
Dialog {
    id: dialog
    property bool ready: false
    Component.onCompleted: ready=true
    parent: Overlay.overlay
    width: 320
    property OwnedHelper helper: OwnedHelper { target: dialog.header }
    Binding { target: dialog.header; property: "width"; value: dialog.width }
    Dialog {
        id: discard
        parent: dialog.parent
        title: "Discard"
        property OwnedHelper headerHelper: OwnedHelper { target: discard.header }
        Binding { target: discard.header; property: "width"; value: dialog.width }
        contentItem: Loader { active: discard.visible; sourceComponent: Text { text: "confirm" } }
        background: Rectangle {
            property bool forcedGc: gcProbe.collect("nested-deferred-background-binding")
            color: "white"
        }
    }
    background: Item {
        property bool forcedGc: gcProbe.collect("outer-deferred-background-binding")
        Rectangle {
            anchors.fill: parent
            color: "white"
            property QtObject borderData: QtObject { property real size: 1 }
            function contourPath() { return "M0 0L1 1" }
            property string path: contourPath()
            property real borderWidth: borderData.size
        }
    }
    contentItem: Column {
        property bool forcedGc: gcProbe.collect("outer-deferred-content-binding")
        TextField { id: field; property OwnedHelper axes: OwnedHelper { target: field } }
    }
}
