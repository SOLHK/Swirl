import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

Item {
    id: section
    property string title: ""
    property string description: ""
    default property alias actions: actionRow.data
    readonly property Item titleItem: titleLabel
    implicitHeight: layout.implicitHeight
    implicitWidth: 0

    ColumnLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.dp(4)
        RowLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.compactGap
            SwirlText {
                id: titleLabel
                text: section.title
                textRole: "title"
                fitWidth: false
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                color: Theme.text
                font.pixelSize: Theme.sectionTitleSize
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
            RowLayout {
                id: actionRow
                visible: children.length > 0
                Layout.alignment: Qt.AlignRight | Qt.AlignTop
                spacing: Theme.compactGap
            }
        }
        SwirlText {
            visible: text.length > 0
            text: section.description
            textRole: "auxiliary"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            color: Theme.muted
            font.pixelSize: Theme.captionSize
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
        }
    }
}
