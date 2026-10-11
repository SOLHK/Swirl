import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string selectedId:""
    readonly property var filteredRows:{
        var query=filter.text.trim().toLowerCase()
        return captureProvider.sessions.filter(function(r){return (r.url+r.method+r.statusText).toLowerCase().indexOf(query)>=0})
    }
    readonly property var selected:{
        var rows=captureProvider.sessions
        for(var i=0;i<rows.length;i++)if(rows[i].id===selectedId)return rows[i]
        return null
    }
    function detailText() {
        if(!selected)return "选择左侧会话查看真实请求与响应。\n\nHTTPS CONNECT 只显示目标和流量，没有解密 TLS。"
        if(detailTabs.currentIndex===0)return selected.method+" "+selected.url+"\n"+selected.status+" · "+selected.statusText+"\n"+selected.time+" · "+selected.duration+"\n上传 "+selected.upBytes+" B · 下载 "+selected.downBytes+" B\n\n"+(selected.tunnel?"这是 HTTPS 隧道元数据，不能查看加密正文。":"明文 HTTP 会话。")+(selected.truncated?"\n正文预览超过 64 KiB 或响应达到限制。":"")
        if(detailTabs.currentIndex===1)return selected.requestHeaders+"\n\n"+(selected.requestBody||"无请求正文")
        return selected.responseHeaders+"\n\n"+(selected.responseBody||"无响应正文")
    }
    ColumnLayout {
        anchors.fill:parent; spacing:14
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:183
            ColumnLayout {
                anchors.fill:parent; anchors.margins:20; spacing:10
                RowLayout {
                    Layout.fillWidth:true; spacing:16
                    SwirlIcon { name:"capture"; size:32; color:Theme.accent }
                    ColumnLayout {
                        Layout.fillWidth:true; spacing:3
                        Text { text:"抓包"; color:Theme.text; font.pixelSize:25; font.weight:Font.DemiBold }
                        Text { text:"真实 HTTP 会话捕获 · HTTPS CONNECT 隧道记录"; color:Theme.muted; font.pixelSize:15; Layout.fillWidth:true; elide:Text.ElideRight }
                    }
                    SwirlStatusBadge { label:captureProvider.running?"监听中 · 真实":"未启动"; tone:captureProvider.running?"success":"neutral" }
                }
                RowLayout {
                    Layout.fillWidth:true; spacing:12
                    Text { text:"本机端口"; font.pixelSize:15; color:Theme.muted }
                    SwirlTextField { id:portField; objectName:"capturePortField"; text:"8899"; enabled:!captureProvider.running; Layout.preferredWidth:105; validator:IntValidator{bottom:0;top:65535} Accessible.name:"抓包监听端口" }
                    SwirlButton {
                        objectName:"captureStartButton"; text:captureProvider.running?"停止抓包":"开始抓包"; primary:!captureProvider.running; font.pixelSize:15
                        onClicked:{
                            if(captureProvider.running){captureProvider.stop();AppState.addEvent("已停止真实抓包","neutral")}
                            else if(captureProvider.start(Number(portField.text))){AppState.addEvent("开始 HTTP 抓包 · 本机端口 "+captureProvider.port,"success")}
                        }
                    }
                    Text { text:captureProvider.running?"127.0.0.1:"+captureProvider.port:"仅在点击开始后监听"; color:Theme.muted; font.pixelSize:14; Layout.fillWidth:true; elide:Text.ElideRight }
                    SwirlButton { text:"清空"; font.pixelSize:15; onClicked:{captureProvider.clear();page.selectedId=""} }
                    SwirlButton { objectName:"captureExportButton"; text:"导出 HAR"; font.pixelSize:15; enabled:captureProvider.sessions.length>0; onClicked:exportDialog.open() }
                }
                Text {
                    Layout.fillWidth:true; text:captureProvider.error.length?captureProvider.error:"将浏览器或测试工具的 HTTP/HTTPS 代理设为此地址即可捕获；不自动修改系统代理。HTTPS 正文解密和全网卡 PCAP 尚未接入。"
                    color:captureProvider.error.length?Theme.red:Theme.muted; font.pixelSize:14; wrapMode:Text.WordWrap
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:12
            SwirlSearchField { id:filter; Layout.fillWidth:true; placeholderText:"筛选真实会话：域名、方法或状态…" }
            Text { text:captureProvider.sessions.length+" 条 · "+captureProvider.activeCount+" 个活动连接"; color:Theme.muted; font.pixelSize:14 }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:730
                SwirlDataTable {
                    objectName:"captureTable"; anchors.fill:parent; anchors.margins:8
                    textPixelSize:14; headerPixelSize:14
                    rows:page.filteredRows
                    columns:[{key:"method",label:"方法",w:80},{key:"host",label:"目标",w:190},{key:"status",label:"状态",w:65},{key:"protocol",label:"类型",w:110},{key:"duration",label:"耗时",w:90},{key:"size",label:"下载",w:90}]
                    selectedId:page.selectedId
                    onRowSelected:function(row){page.selectedId=row.id}
                }
                Text { visible:captureProvider.sessions.length===0; anchors.centerIn:parent; text:captureProvider.running?"等待应用通过代理发送请求…":"开始抓包后，真实会话会显示在这里。"; color:Theme.muted; font.pixelSize:15 }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:350
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:12
                    Text { text:"会话详情"; color:Theme.text; font.pixelSize:20; font.weight:Font.DemiBold }
                    SwirlSegmentedControl { id:detailTabs; Layout.fillWidth:true; options:["概览","请求","响应"] }
                    ScrollView {
                        Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        TextArea {
                            objectName:"captureDetail"; text:page.detailText(); readOnly:true; selectByMouse:true
                            color:Theme.text; font.family:Theme.fontFamily; font.pixelSize:14; wrapMode:TextEdit.Wrap
                            background:Item{}
                        }
                    }
                }
            }
        }
        Text { Layout.fillWidth:true; text:"敏感认证/Cookie 头和常见 URL 密钥已隐藏；正文预览最多 64 KiB，HTTP 响应上限 2 MiB。导出文件仍可能包含请求正文。"; color:Theme.muted; font.pixelSize:12; wrapMode:Text.WordWrap }
    }
    FileDialog {
        id:exportDialog; title:"导出真实抓包会话"; fileMode:FileDialog.SaveFile
        nameFilters:["HTTP Archive (*.har)"]; defaultSuffix:"har"
        onAccepted:{if(captureProvider.exportHar(selectedFile))AppState.toast="真实会话已导出为 HAR。"}
    }
}
