pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"

SwirlDialog {
    id: dialog
    property string sourceId: ""
    property bool pending: false
    property bool advanced: false
    property string errorMessage: ""
    property bool canSave: true
    property bool recoveryRequired: false
    readonly property string sourceName: displayName.text
    readonly property string sourceUrl: urlField.text.trim()
    readonly property int intervalMinutes: [360, 720, 1440, 10080][interval.currentIndex]
    readonly property bool autoUpdate: autoEnabled.checked
    readonly property string formatHint: ["auto", "clash", "loon", "shadowrocket", "surge", "quantumult-x", "sing-box"][formatPreference.currentIndex]
    signal saveRequested()
    signal recoveryRequested()
    objectName: "subscriptionDialog"
    title: sourceId.length ? qsTr("编辑订阅") : qsTr("添加订阅")
    dismissBlocked: pending
    height: Math.min(implicitHeight, parent ? parent.height - Theme.dp(30) : implicitHeight)
    stateFingerprint: String(autoUpdate) + ":" + intervalMinutes + ":" + formatHint

    function edit(record, source) {
        sourceId = record ? record.id : ""
        displayName.text = record ? record.name : ""
        urlField.text = ""
        formatPreference.currentIndex = record ? Math.max(0, ["auto", "clash", "loon", "shadowrocket", "surge", "quantumult-x", "sing-box"].indexOf(record.formatHint)) : 0
        interval.currentIndex = record ? Math.max(0, [360, 720, 1440, 10080].indexOf(record.intervalMinutes)) : 2
        autoEnabled.checked = record ? record.enabled : true
        advanced = false
        errorMessage = ""
        pending = false
        if (source) SwirlMotion.noteTrigger(source)
        open()
        Qt.callLater(function() { if (form.viewport) form.viewport.contentY = 0; displayName.forceActiveFocus() })
    }
    onClosed: urlField.text = ""

    function keyboardFocused(control) {
        return control.activeFocus && (control.focusReason === Qt.TabFocusReason
            || control.focusReason === Qt.BacktabFocusReason
            || control.focusReason === Qt.ShortcutFocusReason)
    }

    component DialogButton: SwirlMotionButton {
        id: control
        property bool primary: false
        property bool quiet: false
        readonly property bool keyboardFocus: activeFocus && (focusReason === Qt.TabFocusReason
            || focusReason === Qt.BacktabFocusReason || focusReason === Qt.ShortcutFocusReason)
        implicitWidth: Math.max(Theme.dp(72), contentItem.implicitWidth + leftPadding + rightPadding)
        implicitHeight: Theme.dp(34)
        leftPadding: Theme.dp(14); rightPadding: Theme.dp(14)
        topPadding: Theme.dp(6); bottomPadding: Theme.dp(6)
        hoverEnabled: true
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(13)
        font.weight: Font.Medium
        font.hintingPreference: Font.PreferFullHinting
        Accessible.name: text
        background: SwirlControlSurface {
            hovered:control.hovered
            pressed:control.down
            focused:control.keyboardFocus
            quiet:control.quiet
            primary:control.primary
            controlEnabled:control.enabled
        }
        contentItem: SwirlText {
            text: control.text; textRole: "button"
            font.family: control.font.family; font.pixelSize: control.font.pixelSize; font.weight: control.font.weight
            color: control.primary ? Theme.primaryButtonText : Theme.text
            opacity: control.enabled ? 1 : 0.45
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component FormField: SwirlTextField {
        id: control
        readonly property bool keyboardFocus: activeFocus && (focusReason === Qt.TabFocusReason
            || focusReason === Qt.BacktabFocusReason || focusReason === Qt.ShortcutFocusReason)
        implicitHeight: Theme.dp(36)
        background: Rectangle {
            radius: Theme.dp(8)
            color: Theme.dark ? Theme.field : Theme.surface
            border.color: control.keyboardFocus ? Theme.text : Theme.controlBorder
            border.width: Theme.borderWidth
        }
    }

    component FormChoice: SwirlComboBox {
        id: control
        readonly property bool keyboardFocus: activeFocus && (focusReason === Qt.TabFocusReason
            || focusReason === Qt.BacktabFocusReason || focusReason === Qt.ShortcutFocusReason)
        implicitHeight: Theme.dp(34)
        indicator: SwirlIcon {
            name: "chevron-right"; size: Theme.dp(12); rotation: 90
            x: Math.round(control.width - width - Theme.dp(10)); y: Math.round((control.height - height) / 2)
            color: Theme.muted
        }
        background: SwirlControlSurface {
            hovered:control.hovered
            pressed:control.pressed
            focused:control.keyboardFocus
            controlEnabled:control.enabled
        }
        delegate: ItemDelegate {
            id: option
            SwirlPressMotion{}
            required property int index
            objectName: "swirlComboOption-" + index
            width: ListView.view.width
            height: Math.max(Theme.dp(34), contentItem.implicitHeight + topPadding + bottomPadding)
            topPadding: Theme.dp(4); bottomPadding: Theme.dp(4)
            text: control.textAt(index)
            highlighted: control.highlightedIndex === index
            contentItem: SwirlText {
                text: AppState.zh(option.text); textRole: "list"
                font.pixelSize: Theme.fontSize(13); color: Theme.text
                leftPadding: Theme.dp(24); rightPadding: Theme.dp(8)
                verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                SwirlIcon {
                    visible: control.currentIndex === option.index
                    name: "checkmark"; size: Theme.dp(13); color: Theme.text
                    x: Theme.dp(3); anchors.verticalCenter: parent.verticalCenter
                }
            }
            background: SwirlControlSurface {
                quiet:true
                hovered:option.hovered
                pressed:option.down
                focused:option.visualFocus
                selected:option.highlighted
                controlEnabled:option.enabled
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: Theme.dp(16)
        PolicyFormScroll {
            id: form
            objectName: "subscriptionFormViewport"
            ownerItem: dialog.ownerItem; formBody: body
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
            Layout.preferredHeight: Math.min(body.implicitHeight, Theme.dp(400))
            ColumnLayout {
                id: body
                objectName: "subscriptionFormBody"
                width: form.availableWidth; spacing: Theme.dp(18)
                ColumnLayout {
                    Layout.fillWidth: true; spacing: Theme.dp(8)
                    SwirlText { text: qsTr("订阅来源"); color: Theme.text; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold }
                    SwirlText { text: qsTr("名称"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                    FormField {
                        id: displayName; objectName: "subscriptionName"
                        Layout.fillWidth: true; enabled: !dialog.pending
                        placeholderText: qsTr("我的订阅"); maximumLength: 128
                        Accessible.name: qsTr("订阅名称")
                    }
                    SwirlText { Layout.topMargin: Theme.dp(4); text: qsTr("HTTPS 订阅地址"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                    FormField {
                        id: urlField; objectName: "subscriptionUrl"
                        Layout.fillWidth: true; enabled: !dialog.pending
                        echoMode: TextInput.Password
                        placeholderText: dialog.sourceId.length ? qsTr("留空保留已加密地址") : "https://…"
                        Accessible.name: qsTr("订阅地址")
                        inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhSensitiveData
                    }
                    SwirlText {
                        objectName: "subscriptionAutomaticImport"
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        text: qsTr("自动识别格式，只更新节点；完整配置需单独审阅。")
                        color: Theme.muted; font.pixelSize: Theme.fontSize(12)
                    }
                }
                Rectangle { Layout.fillWidth: true; implicitHeight: Theme.borderWidth; color: Theme.separator }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: Theme.dp(10)
                    SwirlText { text: qsTr("更新"); color: Theme.text; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(12)
                        SwirlText { text: qsTr("自动更新"); Layout.fillWidth: true; color: Theme.text; font.pixelSize: Theme.fontSize(13) }
                        FormChoice {
                            id: interval; objectName: "subscriptionInterval"
                            Layout.preferredWidth: Theme.dp(124)
                            enabled: autoEnabled.checked && !dialog.pending
                            model: [qsTr("每 6 小时"), qsTr("每 12 小时"), qsTr("每天"), qsTr("每周")]
                            Accessible.name: qsTr("自动更新间隔")
                        }
                        SwirlToggle {
                            id: autoEnabled
                            checked: true; enabled: !dialog.pending
                            Accessible.name: qsTr("自动更新订阅")
                            indicator: Rectangle {
                                width: autoEnabled.width; height: autoEnabled.height
                                radius: height / 2
                                color: autoEnabled.checked ? Theme.text : Theme.controlBorder
                                opacity: autoEnabled.enabled ? autoEnabled.hovered ? 0.85 : 1 : 0.45
                                Rectangle {
                                    anchors.fill:parent
                                    visible:opacity>0;opacity:autoEnabled.enabled && dialog.keyboardFocused(autoEnabled)?1:0
                                    radius:height/2;color:Theme.withAlpha(Theme.text,0.12)
                                    Behavior on opacity {enabled:!SwirlMotion.reduced;NumberAnimation {duration:SwirlMotion.focusDuration}}
                                }
                                Rectangle {
                                    property real thumbPosition: autoEnabled.checked ? 1 : 0
                                    width: parent.height - Theme.dp(4); height: width; radius: height / 2
                                    x: Math.round(Theme.dp(2) + (parent.width - width - Theme.dp(4)) * thumbPosition)
                                    y: Theme.dp(2); color: Theme.surface
                                    Behavior on thumbPosition { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.switchDuration; easing.type: Easing.OutCubic } }
                                }
                                Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }
                            }
                        }
                    }
                    DialogButton {
                        id: advancedControl
                        objectName: "subscriptionAdvanced"
                        Layout.fillWidth: true
                        leftPadding: 0; rightPadding: 0
                        text: dialog.advanced ? qsTr("收起高级设置") : qsTr("高级设置")
                        quiet: true; enabled: !dialog.pending
                        onClicked: dialog.advanced = !dialog.advanced
                        contentItem: RowLayout {
                            spacing: Theme.dp(6)
                            SwirlIcon {
                                name: "chevron-right"; size: Theme.dp(12); color: Theme.muted
                                rotation: dialog.advanced ? 90 : 0
                                Behavior on rotation { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.statusDuration; easing.type: Easing.OutCubic } }
                            }
                            SwirlText { text: advancedControl.text; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                            Item { Layout.fillWidth: true }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; visible: dialog.advanced; spacing: Theme.dp(8)
                        SwirlText { text: qsTr("客户端格式"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                        FormChoice {
                            id: formatPreference; objectName: "subscriptionFormat"
                            Layout.fillWidth: true; enabled: !dialog.pending
                            model: [qsTr("自动"), "Clash", "Loon", qsTr("Shadowrocket / 通用"), "Surge / Surfboard", "Quantumult X", "sing-box"]
                            Accessible.name: qsTr("订阅格式")
                        }
                        SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("仅影响向服务器请求的客户端格式，下载后仍检测实际内容。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                    }
                }
                SwirlText {
                    objectName: "subscriptionSaveError"
                    Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0
                    text: dialog.errorMessage; textFormat: Text.PlainText
                    color: Theme.red; font.pixelSize: Theme.fontSize(12)
                    activeFocusOnTab: true; Accessible.role: Accessible.AlertMessage
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: Theme.borderWidth; color: Theme.separator }
        ColumnLayout {
            Layout.fillWidth: true; spacing: Theme.dp(10)
            DialogButton {
                objectName: "recoverSubscriptionSave"; text: qsTr("恢复已保存的操作")
                Layout.fillWidth: true; quiet: true
                visible: dialog.pending && dialog.recoveryRequired
                onClicked: dialog.recoveryRequested()
            }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.dp(8)
                Item { Layout.fillWidth: true }
                DialogButton { text: qsTr("取消"); enabled: !dialog.pending; onClicked: dialog.requestDismiss() }
                DialogButton {
                    objectName: "saveSubscription"
                    text: dialog.pending ? qsTr("正在保存…") : qsTr("保存并更新"); primary: true
                    enabled: !dialog.pending && dialog.canSave && displayName.text.trim().length > 0 && (dialog.sourceId.length > 0 || urlField.text.trim().length > 0)
                    onClicked: dialog.saveRequested()
                }
            }
        }
    }
}
