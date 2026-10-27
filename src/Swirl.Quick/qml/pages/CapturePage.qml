pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    required property var captureProvider
    property int listenerPort: 8899
    readonly property Item motionTitle: heading.titleItem
    function scrollToBottom() { scroll.contentItem.contentY=Math.max(0,scroll.contentHeight-scroll.availableHeight) }
    function applyLimits() { captureProvider.setLimits([3,5,10,0][timeLimit.currentIndex],[50,100,500,0][sizeLimit.currentIndex],[100,500,1000][countLimit.currentIndex]) }
    component Note: SwirlText { color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.Wrap; lineHeight:1.4 }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.pagePadding; spacing:Theme.dp(20)
        SwirlPageHeader {
            id:heading; Layout.fillWidth:true; title:qsTr("HTTP 内容捕获")
            description:qsTr("在本机监听端口记录真实请求。HTTPS 正文需要配置 CA 与解密主机名。")
            SwirlFlow { objectName:"captureStateFlow"; Layout.preferredWidth:Theme.dp(42); Layout.preferredHeight:Theme.dp(18); phase:page.captureProvider.error.length?"failed":page.captureProvider.running?"succeeded":"idle" }
            SwirlToggle { objectName:"captureToggle"; large:true; checked:page.captureProvider.running; enabled:page.captureProvider.running||listenerInput.acceptableInput; onToggled:{if(checked){page.applyLimits();page.captureProvider.start(page.listenerPort)}else page.captureProvider.stop()} Accessible.name:qsTr("捕获 HTTP 内容") }
        }
        ScrollView {
            id:scroll; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff; ScrollBar.vertical:SwirlScrollBar {}
            ColumnLayout {
                width:scroll.availableWidth; spacing:Theme.dp(24)
                Rectangle {
                    Layout.fillWidth:true; Layout.preferredHeight:listenerBody.implicitHeight+Theme.dp(32); radius:Theme.dp(14); color:Theme.buttonBase
                    ColumnLayout {
                        id:listenerBody; anchors.fill:parent; anchors.margins:Theme.dp(16); spacing:Theme.dp(12)
                        RowLayout {
                            Layout.fillWidth:true
                            ColumnLayout { Layout.fillWidth:true; spacing:Theme.dp(5); SwirlText { text:page.captureProvider.running?qsTr("正在监听 127.0.0.1:%1").arg(page.captureProvider.port):qsTr("捕获尚未开始"); color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold } Note { text:qsTr("%1 条请求，%2 个活动连接").arg(page.captureProvider.sessions.length).arg(page.captureProvider.activeCount) } }
                            SwirlButton { text:qsTr("打开请求面板"); iconName:"capture"; onClicked:page.Window.window.openDashboard() }
                        }
                        Note { text:page.captureProvider.error.length?page.captureProvider.error:qsTr("将客户端 HTTP / HTTPS 代理指向捕获端口。停止捕获后可继续检查已记录的请求。"); color:page.captureProvider.error.length?Theme.red:Theme.muted }
                    }
                }
                GridLayout {
                    Layout.fillWidth:true; columns:page.width>=Theme.dp(650)?2:1; columnSpacing:Theme.dp(32); rowSpacing:Theme.dp(24)
                    ColumnLayout {
                        Layout.fillWidth:true; Layout.minimumWidth:0; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; spacing:Theme.dp(12)
                        SwirlSectionTitle { title:qsTr("监听与范围"); Layout.fillWidth:true }
                        RowLayout { Layout.fillWidth:true; SwirlText { text:qsTr("本机端口"); color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true } SwirlTextField { id:listenerInput; Layout.preferredWidth:Theme.dp(112); text:String(page.listenerPort); enabled:!page.captureProvider.running; validator:IntValidator { bottom:0; top:65535 } onEditingFinished:if(acceptableInput)page.listenerPort=Number(text); Accessible.name:qsTr("捕获监听端口") } }
                        Note { text:qsTr("使用空闲端口。监听仅在开始捕获后生效。") }
                        SwirlButton { text:qsTr("编辑记录筛选"); onClicked:filterDialog.open() }
                        Note { text:page.captureProvider.filter.length?qsTr("当前 URL 筛选：%1").arg(page.captureProvider.filter):qsTr("当前记录通过此端口的全部请求。") }
                        Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator }
                        ReferenceCheckBox { text:qsTr("捕获时自动开启 MITM"); checked:page.captureProvider.autoMitmEnabled; onToggled:page.captureProvider.autoMitmEnabled=checked }
                        Note { text:qsTr("仅对解密列表中的主机名生效；开始前需要配置 CA。") }
                        SwirlButton { text:qsTr("配置 HTTPS 解密"); quiet:true; iconName:"shield"; onClicked:AppState.navigate("tls") }
                    }
                    ColumnLayout {
                        Layout.fillWidth:true; Layout.minimumWidth:0; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; spacing:Theme.dp(12)
                        SwirlSectionTitle { title:qsTr("自动停止"); description:qsTr("达到任一限制时结束本次捕获。"); Layout.fillWidth:true }
                        GridLayout {
                            Layout.fillWidth:true; columns:2; columnSpacing:Theme.dp(16); rowSpacing:Theme.dp(14)
                            SwirlText { text:qsTr("时间"); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                            SwirlComboBox { id:timeLimit; Layout.fillWidth:true; model:[qsTr("3 分钟"),qsTr("5 分钟"),qsTr("10 分钟"),qsTr("无限制")]; onActivated:page.applyLimits(); Accessible.name:qsTr("捕获时间限制") }
                            SwirlText { text:qsTr("大小"); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                            SwirlComboBox { id:sizeLimit; Layout.fillWidth:true; model:["50 MB","100 MB","500 MB",qsTr("无限制")]; onActivated:page.applyLimits(); Accessible.name:qsTr("捕获大小限制") }
                            SwirlText { text:qsTr("请求数"); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                            SwirlComboBox { id:countLimit; Layout.fillWidth:true; model:[qsTr("100 请求"),qsTr("500 请求"),qsTr("1000 请求")]; onActivated:page.applyLimits(); Accessible.name:qsTr("捕获请求数量限制") }
                        }
                        Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator; Layout.topMargin:Theme.dp(10) }
                        SwirlText { text:qsTr("记录显示"); color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                        ReferenceCheckBox { text:qsTr("合并系统进程 · 研发中"); checked:false; enabled:false }
                        ReferenceCheckBox { text:qsTr("合并应用及子进程 · 研发中"); checked:false; enabled:false }
                        Note { text:qsTr("当前按实际采集的记录显示；进程合并尚未接入。") }
                    }
                }
                Item { Layout.preferredHeight:Theme.dp(8) }
            }
        }
    }
    SwirlDialog {
        ownerItem:page; id:filterDialog; title:qsTr("捕获记录筛选")
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(14)
            SwirlTextField { id:captureFilter; Layout.fillWidth:true; text:page.captureProvider.filter; placeholderText:qsTr("URL 包含文本，留空记录全部"); Accessible.name:qsTr("捕获 URL 筛选") }
            Note { text:qsTr("筛选实际捕获的 HTTP 请求与 CONNECT 隧道。") }
            RowLayout { Layout.alignment:Qt.AlignRight; SwirlButton { text:qsTr("取消"); onClicked:filterDialog.requestDismiss() } SwirlButton { text:qsTr("应用筛选"); primary:true; onClicked:{page.captureProvider.filter=captureFilter.text;filterDialog.markSaved();filterDialog.close()} } }
            SwirlButton { text:qsTr("打开请求面板"); quiet:true; onClicked:{filterDialog.close();page.Window.window.openDashboard()} }
        }
    }
}
