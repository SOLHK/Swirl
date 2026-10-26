import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

Item {
    id: header
    property string title: ""
    property string description: ""
    property string metadata: ""
    property bool stackActions: width < Theme.dp(540)
    default property alias actions: actionRow.data
    readonly property Item titleItem: titleLabel
    implicitHeight: layout.implicitHeight
    implicitWidth: 0

    GridLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        columns: header.stackActions ? 1 : 2
        columnSpacing: Theme.gap
        rowSpacing: Theme.compactGap
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.dp(7)
            SwirlText {
                id: titleLabel
                text: header.title
                textRole: "pageTitle"
                fitWidth: false
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                color: Theme.text
                font.pixelSize: Theme.pageTitleSize
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
            SwirlText {
                visible: text.length > 0
                text: header.description
                textRole: "body"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                color: Theme.muted
                font.pixelSize: Theme.captionSize
                lineHeight: 1.35
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
            SwirlText {
                visible: text.length > 0
                text: header.metadata
                textRole: "smallLabel"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                color: Theme.muted
                font.pixelSize: Theme.captionSize
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
        }
        RowLayout {
            id: actionRow
            visible: children.length > 0
            Layout.minimumWidth: 0
            Layout.alignment: header.stackActions ? Qt.AlignLeft : Qt.AlignRight | Qt.AlignTop
            spacing: Theme.compactGap
        }
    }
}
