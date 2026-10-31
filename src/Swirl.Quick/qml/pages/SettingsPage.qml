import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

FocusScope {
    id: page
    property string section: "常规"
    property var sections: ["常规", "字体", "代理", "TUN", "DNS", "端口", "系统集成", "启动", "通知", "数据管理", "隐私与安全", "快捷键", "关于 Swirl"]
    property var visited: ({"常规": true})
    property var history: []
    property string previousSection: "常规"
    property bool returning: false
    property int direction: 1
    readonly property int selectedIndex: Math.max(0, sections.indexOf(section))
    readonly property Item motionTitle: heading.titleItem

    function currentSectionReady() {
        const pane = panes.itemAt(selectedIndex)
        return !!pane && pane.ready
    }

    function scrollToBottom() {
        const pane = panes.itemAt(selectedIndex)
        if (pane) pane.scrollToBottom()
    }
    function scrollToTop() {
        const pane = panes.itemAt(selectedIndex)
        if (pane) pane.scrollToTop()
    }
    function selectSection(name, control) {
        if (sections.indexOf(name) < 0 || section === name) return
        if (control) SwirlMotion.noteTrigger(control)
        section = name
    }
    function moveCategory(step) {
        const next = Math.max(0, Math.min(sections.length - 1, selectedIndex + step))
        selectSection(sections[next], categories)
        categories.positionViewAtIndex(next, ListView.Contain)
        const control = categories.itemAtIndex(next)
        if (control) (control.button || control).forceActiveFocus(Qt.TabFocusReason)
    }
    function goBack() {
        if (!history.length) return false
        const stack = history.slice()
        const target = stack.pop()
        history = stack
        returning = true
        section = target
        returning = false
        return true
    }
    function handleSectionEscape() { return dismissals.count === 0 && goBack() }
    onSectionChanged: {
        if (sections.indexOf(section) < 0) { section = previousSection; return }
        direction = sections.indexOf(section) >= sections.indexOf(previousSection) ? 1 : -1
        if (!returning) history = history.concat([previousSection]).slice(-32)
        previousSection = section
        const next = Object.assign({}, visited)
        next[section] = true
        visited = next
    }
    Keys.onEscapePressed: function(event) { event.accepted = dismissals.count === 0 && goBack() }
    Keys.onShortcutOverride: function(event) {
        if (dismissals.count === 0 && history.length && event.key === Qt.Key_Left && (event.modifiers & Qt.AltModifier)) event.accepted = true
    }
    Keys.onPressed: function(event) {
        if (dismissals.count === 0 && event.key === Qt.Key_Left && (event.modifiers & Qt.AltModifier)) event.accepted = goBack()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.pagePadding
        spacing: Theme.sectionGap
        SwirlPageHeader {
            id: heading
            Layout.fillWidth: true
            title: qsTr("软件设置")
            description: qsTr("外观、连接与本机偏好")
            SwirlButton { text: qsTr("返回分区"); visible: page.history.length > 0; quiet: true; onClicked: page.goBack() }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.sectionGap
            ListView {
                id: categories
                objectName: "settingsSectionList"
                Layout.preferredWidth: Theme.dp(page.width < Theme.dp(700) ? 132 : 164)
                Layout.fillHeight: true
                clip: true
                spacing: Theme.dp(3)
                model: page.sections
                currentIndex: page.selectedIndex
                keyNavigationEnabled: false
                activeFocusOnTab: true
                Keys.onUpPressed: page.moveCategory(-1)
                Keys.onDownPressed: page.moveCategory(1)
                ScrollBar.vertical: SwirlScrollBar {}
                SwirlArcMotion {
                    id: selectionPath
                    parent: categories.contentItem
                    targetX: 0
                    targetY: categories.currentItem ? categories.currentItem.y + categories.currentItem.headerHeight : 0
                    bend: Theme.dp(5)
                    motionEnabled: page.visible
                }
                Rectangle {
                    parent: categories.contentItem
                    x: selectionPath.position.x
                    y: selectionPath.position.y
                    width: categories.width
                    height: Theme.dp(38)
                    radius: Theme.controlRadius
                    color: Theme.withAlpha(Theme.accent, 0.09)
                    Rectangle { width: Theme.dp(3); height: Theme.dp(18); anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; radius: Theme.dp(1.5); color: Theme.accent }
                }
                delegate: Item {
                    id: categoryRow
                    required property string modelData
                    required property int index
                    readonly property real headerHeight: index === 0 ? Theme.dp(26) : index === 2 || index === 6 || index === 12 ? Theme.dp(34) : 0
                    readonly property Item button: category
                    width: ListView.view.width
                    height: headerHeight + Theme.dp(38)
                    SwirlText {
                        x: Theme.dp(12)
                        y: categoryRow.index === 0 ? 0 : Theme.dp(8)
                        visible: categoryRow.headerHeight > 0
                        text: categoryRow.index === 0 ? qsTr("个性化") : categoryRow.index === 2 ? qsTr("连接") : categoryRow.index === 6 ? qsTr("本机") : qsTr("产品")
                        color: Theme.muted
                        font.pixelSize: Theme.fontSize(11)
                    }
                    ItemDelegate {
                        id: category
                        objectName: "settingsSection-" + categoryRow.index
                        y: categoryRow.headerHeight
                        width: parent.width
                        height: Theme.dp(38)
                        text: categoryRow.modelData
                        highlighted: page.section === categoryRow.modelData
                        focusPolicy: Qt.StrongFocus
                        onClicked: page.selectSection(categoryRow.modelData, category)
                        background: Rectangle {
                            color: Theme.withAlpha(Theme.accent, feedback.light * 0.09)
                            radius: Theme.controlRadius
                        }
                        contentItem: SwirlText {
                            text: category.text
                            color: category.highlighted ? Theme.accent : Theme.text
                            font.pixelSize: Theme.fontSize(13)
                            font.weight: category.highlighted ? Font.DemiBold : Font.Normal
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                        SwirlInteractionMotion { id: feedback; hovered: category.hovered; pressed: category.down; focused: category.visualFocus; controlEnabled: category.enabled }
                        Accessible.name: text
                    }
                }
            }
            Rectangle { Layout.preferredWidth: Theme.borderWidth; Layout.fillHeight: true; color: Theme.separator }
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                Repeater {
                    id: panes
                    model: page.sections
                    delegate: Item {
                        id: paneShell
                        required property string modelData
                        anchors.fill: parent
                        property bool initialized: false
                        property bool hasPresented: false
                        readonly property bool selected: page.section === modelData
                        readonly property bool ready: content.status === Loader.Ready
                        visible: selected || reveal.moving || reveal.progress > 0
                        enabled: selected
                        z: selected ? 1 : 0
                        function scrollToBottom() { options.contentItem.contentY = Math.max(0, options.contentHeight - options.availableHeight) }
                        function scrollToTop() { options.contentItem.contentY = 0 }
                        function retarget() {
                            if (!initialized) return
                            if (selected && ready) {
                                if (!hasPresented) {
                                    curve.targetX = page.direction * Theme.dp(24)
                                    curve.targetY = Theme.dp(5)
                                    curve.settle()
                                    hasPresented = true
                                }
                                curve.targetX = 0
                                curve.targetY = 0
                                reveal.moveTo(1)
                            } else {
                                curve.targetX = -page.direction * Theme.dp(18)
                                curve.targetY = -Theme.dp(3)
                                reveal.moveTo(0)
                            }
                        }
                        onSelectedChanged: retarget()
                        onReadyChanged: retarget()
                        Connections {
                            target: paneShell.initialized ? page : null
                            enabled: paneShell.initialized
                            function onVisibleChanged() { if (paneShell.initialized && !page.visible) { reveal.finish(); curve.settle() } }
                        }
                        Component.onCompleted: { initialized = true; if (selected && ready) { hasPresented = true; reveal.progress = 1; reveal.destination = 1 } else retarget() }
                        SwirlArcMotion { id: curve; bend: Theme.dp(6); duration: SwirlMotion.pageDuration; motionEnabled: page.visible }
                        SwirlTransitionCoordinator { id: reveal; duration: SwirlMotion.pageDuration }
                        ScrollView {
                            id: options
                            anchors.fill: parent
                            opacity: reveal.progress
                            transform: Translate { x: curve.position.x; y: curve.position.y }
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            ScrollBar.vertical: SwirlScrollBar {}
                            ColumnLayout {
                                width: options.availableWidth
                                spacing: paneShell.modelData === "关于 Swirl" ? Theme.dp(8) : Theme.sectionGap
                                SwirlSectionTitle {
                                    Layout.fillWidth: true
                                    visible: paneShell.modelData !== "关于 Swirl"
                                    title: paneShell.modelData
                                    description: paneShell.modelData === "常规" ? qsTr("可用设置会自动保存。") : paneShell.modelData === "字体" ? qsTr("预览后应用到整个界面。") : paneShell.modelData === "代理" ? qsTr("查看实际接管状态与连接诊断。") : ""
                                }
                                Loader {
                                    id: content
                                    Layout.fillWidth: true
                                    active: page.visited[paneShell.modelData] === true
                                    asynchronous: true
                                    sourceComponent: paneShell.modelData === "常规" ? appearancePane : paneShell.modelData === "字体" ? fontPane : paneShell.modelData === "代理" ? proxyPane : paneShell.modelData === "关于 Swirl" ? aboutPane : capabilityPane
                                }
                                Item { Layout.preferredHeight: Theme.dp(paneShell.modelData === "关于 Swirl" ? 8 : 24) }
                            }
                        }
                        SwirlText { anchors.centerIn: parent; visible: paneShell.selected && !paneShell.ready; text: content.status === Loader.Error ? qsTr("无法加载此设置分区") : qsTr("正在准备设置…"); color: content.status === Loader.Error ? Theme.red : Theme.muted }
                        Component { id: appearancePane; SettingsAppearancePane { settingsPage: page } }
                        Component { id: fontPane; SwirlFontSettings {} }
                        Component { id: proxyPane; SettingsProxyPane { settingsPage: page } }
                        Component { id: aboutPane; SettingsAboutPane { settingsPage: page; viewportHeight: options.availableHeight } }
                        Component { id: capabilityPane; SettingsCapabilityPane { settingsPage: ({section: paneShell.modelData}) } }
                    }
                }
            }
        }
    }
}
