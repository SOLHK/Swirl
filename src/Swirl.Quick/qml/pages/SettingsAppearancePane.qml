import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    id: pane
    required property var settingsPage
    spacing: Theme.dp(4)
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("外观"); description: qsTr("选择适合当前光线与阅读习惯的界面。") }
    SettingsRowPane {
        Layout.fillWidth: true
        title: qsTr("颜色主题")
        description: qsTr("浅色、深色，或跟随 Windows。")
        SwirlComboBox { objectName: "themeModePicker"; model: [qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")]; currentIndex: ["System", "Light", "Dark"].indexOf(Theme.mode); onActivated: function(index) { Theme.mode = ["System", "Light", "Dark"][index] }; Accessible.name: qsTr("颜色主题") }
    }
    SettingsRowPane { Layout.fillWidth: true; title: qsTr("透明材质"); description: qsTr("使用可用的窗口背景与玻璃效果。关闭后使用清晰的实色表面。"); SwirlToggle { checked: Theme.transparency; onToggled: Theme.transparency = checked; Accessible.name: qsTr("透明材质") } }
    SettingsRowPane { Layout.fillWidth: true; separator: false; title: qsTr("增强对比度"); description: qsTr("强化文字、边界与焦点的辨识度。"); SwirlToggle { objectName: "increaseContrastToggle"; checked: Theme.increaseContrast; onToggled: Theme.increaseContrast = checked; Accessible.name: qsTr("增强对比度") } }
    Item { Layout.preferredHeight: Theme.dp(20) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("动画与交互"); description: qsTr("动态效果随操作展开，减少动态效果时保留状态与焦点反馈。") }
    SettingsRowPane { Layout.fillWidth: true; title: qsTr("减少动态效果"); description: qsTr("收束页面、曲线与浮层运动。"); SwirlToggle { checked: Theme.reduceMotion; onToggled: Theme.reduceMotion = checked; Accessible.name: qsTr("减少动态效果") } }
    SettingsRowPane { Layout.fillWidth: true; separator: false; title: qsTr("跟随系统动态效果"); description: qsTr("遵循 Windows 的辅助功能设置。"); SwirlToggle { objectName: "followSystemMotionToggle"; checked: Theme.followSystemMotion; onToggled: Theme.followSystemMotion = checked; Accessible.name: qsTr("跟随系统动态效果") } }
    Item { Layout.preferredHeight: Theme.dp(20) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("字体与显示"); description: qsTr("字体预览、可变轴与文字层级集中在字体分区。") }
    SettingsRowPane {
        Layout.fillWidth: true
        title: qsTr("界面字体")
        description: fontManager.currentFamily
        SwirlButton { id: fontButton; text: qsTr("选择字体"); quiet: true; onClicked: pane.settingsPage.selectSection("字体", fontButton) }
    }
    SettingsRowPane {
        Layout.fillWidth: true
        title: qsTr("界面缩放")
        description: Theme.followSystemScale ? qsTr("自动跟随 Windows 显示缩放，使用 Qt 原生 DPI。") : qsTr("手动缩放 %1%").arg(Math.round(Theme.uiScale * 100))
        SwirlComboBox { objectName: "scaleModeCombo"; model: [qsTr("自动跟随系统"), qsTr("手动自定义")]; currentIndex: Theme.followSystemScale ? 0 : 1; onActivated: currentIndex === 0 ? Theme.followSystem() : Theme.setScalePercent(Theme.uiScale * 100); Accessible.name: qsTr("界面缩放模式") }
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: Theme.dp(12)
        SwirlSlider { id: scaleSlider; objectName: "scaleSlider"; Layout.fillWidth: true; from: 0.75; to: 1.5; stepSize: 0.01; enabled: !Theme.followSystemScale; onMoved: Theme.setScalePercent(Math.round(value * 100)); Binding { target: scaleSlider; property: "value"; value: Theme.uiScale; when: !scaleSlider.pressed } Accessible.name: qsTr("界面缩放百分比") }
        SwirlText { text: qsTr("%1%").arg(Math.round(Theme.uiScale * 100)); color: Theme.text; font.pixelSize: Theme.fontSize(13) }
        SwirlButton { text: qsTr("恢复默认"); quiet: true; enabled: !Theme.followSystemScale || Theme.uiScale !== 1.0; onClicked: Theme.resetScale() }
    }
    SwirlText { Layout.fillWidth: true; Layout.topMargin: Theme.dp(10); text: qsTr("以上设置会自动保存。字体预览需要单独确认应用。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    Item { Layout.preferredHeight: Theme.dp(20) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("窗口偏好"); description: qsTr("下列选项尚未接入，当前不可更改。") }
    Repeater {
        model: [qsTr("关闭窗口时保留后台"), qsTr("记住窗口尺寸"), qsTr("显示工具提示")]
        SettingsRowPane { required property string modelData; Layout.fillWidth: true; title: modelData; description: qsTr("研发中"); SwirlToggle { enabled: false; Accessible.name: modelData } }
    }
}
