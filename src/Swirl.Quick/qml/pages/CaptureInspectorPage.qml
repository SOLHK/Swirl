pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    required property var captureProvider
    property string selectedId: ""
    property string query: ""
    readonly property var filteredRows: page.captureProvider.sessions.filter(function(row) {
        var q = page.query.trim().toLowerCase()
        return String(row.url).toLowerCase().indexOf(q) >= 0 || String(row.method).toLowerCase().indexOf(q) >= 0 || String(row.statusText).toLowerCase().indexOf(q) >= 0
    })
    readonly property var selected: {
        var rows = page.captureProvider.sessions
        for (var i = 0; i < rows.length; ++i)
            if (rows[i].id === page.selectedId) return rows[i]
        return null
    }
    function detailText() {
        if (!page.selected) return "选择请求查看请求与响应。\n\nHTTPS CONNECT 只显示目标和流量，没有解密 TLS。"
        if (detailTabs.currentIndex === 0)
            return page.selected.method + " " + page.selected.url + "\n" + page.selected.status + " · " + page.selected.statusText + "\n" + page.selected.time + " · " + page.selected.duration + "\n上传 " + page.selected.upBytes + " B · 下载 " + page.selected.downBytes + " B\n\n" + (page.selected.tunnel ? "这是 HTTPS 隧道元数据，不能查看加密正文。" : "明文 HTTP 会话。") + (page.selected.truncated ? "\n正文预览超过 64 KiB 或响应达到限制。" : "")
        if (detailTabs.currentIndex === 1) return page.selected.requestHeaders + "\n\n" + (page.selected.requestBody || "无请求正文")
        return page.selected.responseHeaders + "\n\n" + (page.selected.responseBody || "无响应正文")
    }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.dp(12)
        SwirlGlassPanel {
            Layout.preferredWidth: Theme.dp(252)
            Layout.minimumWidth: Theme.dp(225)
            Layout.fillHeight: true
            cornerRadius: Theme.containerRadius
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.dp(16)
                spacing: Theme.dp(11)
                SwirlText { text: "抓包设置"; color: Theme.text; font.pixelSize: Theme.fontSize(20); font.weight: Font.DemiBold }
                SwirlStatusBadge { label: page.captureProvider.running ? "监听中 · 真实" : "未启动"; tone: page.captureProvider.running ? "success" : "neutral" }
                SwirlText { text: "本机端口"; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                SwirlTextField {
                    id: portField
                    objectName: "capturePortField"
                    text: "8899"
                    enabled: !page.captureProvider.running
                    Layout.fillWidth: true
                    validator: IntValidator { bottom: 0; top: 65535 }
                    Accessible.name: "抓包监听端口"
                }
                SwirlButton {
                    objectName: "captureStartButton"; text: page.captureProvider.running ? "停止抓包" : "开始抓包"; primary: !page.captureProvider.running; Layout.fillWidth: true
                    onClicked: {
                        if (page.captureProvider.running) {
                            page.captureProvider.stop()
                            AppState.addEvent("已停止真实抓包", "neutral")
                        } else if (page.captureProvider.start(Number(portField.text))) {
                            AppState.addEvent("开始 HTTP 抓包 · 本机端口 " + page.captureProvider.port, "success")
                        }
                    }
                }
                SwirlText { text: page.captureProvider.running ? "127.0.0.1:" + page.captureProvider.port : "监听地址仅在开始后启用。"; color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.WordWrap; Layout.fillWidth: true }
                SwirlText { text: page.captureProvider.error.length ? page.captureProvider.error : "将客户端 HTTP/HTTPS 代理指向捕获端口即可捕获。配置 CA 和 MitM 主机名后可解密 HTTPS 正文。"; color: page.captureProvider.error.length ? Theme.red : Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Item { Layout.fillHeight: true }
                SwirlButton { text: "清空"; Layout.fillWidth: true; onClicked: { page.captureProvider.clear(); page.selectedId = "" } }
                SwirlButton { objectName: "captureExportButton"; text: "导出 HAR"; Layout.fillWidth: true; enabled: page.captureProvider.sessions.length > 0; onClicked: exportDialog.open() }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: Theme.dp(8)
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.dp(10)
                SwirlText { text: "HTTP 请求"; color: Theme.text; font.pixelSize: Theme.fontSize(20); font.weight: Font.DemiBold }
                SwirlSearchField { Layout.fillWidth: true; placeholderText: "筛选域名、方法或状态"; onTextChanged: page.query = text }
                SwirlText { text: page.captureProvider.sessions.length + " 条 · " + page.captureProvider.activeCount + " 个活动连接"; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            }
            SwirlGlassPanel {
                Layout.fillWidth: true; Layout.fillHeight: true; cornerRadius: Theme.containerRadius
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: Theme.dp(10); spacing: Theme.dp(8)
                    SwirlGlassPanel {
                        Layout.fillWidth: true; Layout.fillHeight: true; cornerRadius: Theme.tableRadius; clip: true
                        SwirlDataTable {
                            objectName: "captureTable"; anchors.fill: parent; incrementalRows:true;animateRowChanges:false;rows: page.filteredRows; selectedId: page.selectedId
                            textPixelSize: 12; headerPixelSize: 11
                            columns: [{key:"method",label:"方法",w:80},{key:"host",label:"目标",w:190},{key:"status",label:"状态",w:65},{key:"protocol",label:"类型",w:110},{key:"duration",label:"耗时",w:90},{key:"size",label:"下载",w:90}]
                            onRowSelected: function(row) { page.selectedId = row.id }
                        }
                        SwirlText { visible: page.captureProvider.sessions.length === 0; anchors.centerIn: parent; text: page.captureProvider.running ? "等待应用通过代理发送请求…" : "开始抓包后，请求会显示在这里。"; color: Theme.muted; font.pixelSize: Theme.fontSize(13) }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        SwirlText { text: "请求详情"; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                        SwirlSegmentedControl { id: detailTabs; options: ["概览", "请求", "响应"]; Layout.preferredWidth: Theme.dp(228) }
                    }
                    ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(138); clip: true
                        TextArea { renderType: TextEdit.NativeRendering; font.weight: Theme.bodyFontWeight; font.hintingPreference: Font.PreferFullHinting; Binding on font.variableAxes { delayed:true; value:Theme.variableAxesFor(font.family,font.weight) } objectName: "captureDetail"; text: page.detailText(); readOnly: true; selectByMouse: true; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); wrapMode: TextEdit.Wrap; background: Item {} }
                    }
                }
            }
            SwirlText { text: "认证、Cookie 与常见 URL 密钥已隐藏；正文预览最多 64 KiB，HTTP 响应上限 2 MiB。HAR 文件仍可能包含请求正文。"; color: Theme.muted; font.pixelSize: Theme.fontSize(11); wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
    }
    FileDialog {
        id: exportDialog; title: "导出真实抓包会话"; fileMode: FileDialog.SaveFile; nameFilters: ["HTTP Archive (*.har)"]; defaultSuffix: "har"
        onAccepted: if (page.captureProvider.exportHar(selectedFile)) AppState.toast = "真实会话已导出为 HAR。"
    }
}
