import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

Item {
    id: row
    property string title: ""
    property string description: ""
    property bool separator: true
    property bool stackControls: width < Theme.dp(460)
    default property alias controls: actions.data
    implicitWidth: 0
    implicitHeight: layout.implicitHeight + Theme.dp(28)
    GridLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        columns: row.stackControls ? 1 : 2
        columnSpacing: Theme.dp(24)
        rowSpacing: Theme.dp(10)
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.dp(5)
            SwirlText { Layout.fillWidth: true; text: row.title; color: Theme.text; font.pixelSize: Theme.fontSize(14); wrapMode: Text.Wrap }
            SwirlText { Layout.fillWidth: true; visible: text.length > 0; text: row.description; color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
        }
        RowLayout {
            id: actions
            Layout.minimumWidth: 0
            Layout.alignment: row.stackControls ? Qt.AlignLeft : Qt.AlignRight | Qt.AlignVCenter
            spacing: Theme.compactGap
        }
    }
    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: Theme.borderWidth; color: Theme.separator; visible: row.separator }
}
