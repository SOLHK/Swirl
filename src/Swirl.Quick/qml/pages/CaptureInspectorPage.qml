pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    required property var captureProvider
    property string selectedId:""
    property string query:""
    readonly property var filteredRows:page.captureProvider.sessions.filter(function(row){var q=page.query.trim().toLowerCase();return String(row.url).toLowerCase().indexOf(q)>=0||String(row.method).toLowerCase().indexOf(q)>=0||String(row.statusText).toLowerCase().indexOf(q)>=0})
    readonly property var selected:page.captureProvider.sessions.find(function(row){return row.id===page.selectedId})||null
    function detailText() {
        if (!page.selected) return "选择请求查看请求与响应。\n\nHTTPS CONNECT 只显示目标和流量，没有解密 TLS。"
        if (detailTabs.currentIndex === 0)
            return page.selected.method + " " + page.selected.url + "\n" + page.selected.status + " · " + page.selected.statusText + "\n" + page.selected.time + " · " + page.selected.duration + "\n上传 " + page.selected.upBytes + " B · 下载 " + page.selected.downBytes + " B\n\n" + (page.selected.tunnel ? "这是 HTTPS 隧道元数据，不能查看加密正文。" : "明文 HTTP 会话。") + (page.selected.truncated ? "\n正文预览超过 64 KiB 或响应达到限制。" : "")
        if (detailTabs.currentIndex === 1) return page.selected.requestHeaders + "\n\n" + (page.selected.requestBody || "无请求正文")
        return page.selected.responseHeaders + "\n\n" + (page.selected.responseBody || "无响应正文")
    }
    SwirlArcMotion{id:tabMotion;targetX:detailTabs.currentIndex*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout{
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("HTTP 请求");description:qsTr("%1 条会话，%2 个活动连接").arg(page.captureProvider.sessions.length).arg(page.captureProvider.activeCount)
            SwirlButton{text:qsTr("清空");enabled:page.captureProvider.sessions.length>0;onClicked:{page.captureProvider.clear();page.selectedId=""}}
            SwirlButton{objectName:"captureExportButton";text:qsTr("导出 HAR");enabled:page.captureProvider.sessions.length>0;onClicked:exportDialog.open()}
        }
        RowLayout{Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout{Layout.preferredWidth:Theme.dp(205);Layout.fillHeight:true;spacing:Theme.gap
                SwirlText{text:qsTr("捕获监听");font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold;color:Theme.text}
                RowLayout{Layout.fillWidth:true;SwirlFlow{Layout.preferredWidth:Theme.dp(40);Layout.preferredHeight:Theme.dp(18);phase:page.captureProvider.error.length?"failed":page.captureProvider.running?"succeeded":"idle"}SwirlStatusBadge{label:page.captureProvider.running?qsTr("监听中"):qsTr("未启动");tone:page.captureProvider.running?"success":"neutral"}}
                SwirlText{text:qsTr("本机端口");font.pixelSize:Theme.captionSize;color:Theme.muted}
                SwirlTextField{id:portField;objectName:"capturePortField";Layout.fillWidth:true;text:"8899";enabled:!page.captureProvider.running;validator:IntValidator{bottom:0;top:65535}Accessible.name:qsTr("抓包监听端口")}
                SwirlButton{objectName:"captureStartButton";Layout.fillWidth:true;text:page.captureProvider.running?qsTr("停止抓包"):qsTr("开始抓包");primary:!page.captureProvider.running;onClicked:{if(page.captureProvider.running){page.captureProvider.stop();AppState.addEvent("已停止真实抓包","neutral")}else if(page.captureProvider.start(Number(portField.text)))AppState.addEvent("开始 HTTP 抓包 · 本机端口 "+page.captureProvider.port,"success")}}
                SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:page.captureProvider.running?"127.0.0.1:"+page.captureProvider.port:qsTr("开始后启用本机监听地址。");font.pixelSize:Theme.captionSize;color:Theme.muted}
                SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:page.captureProvider.error||qsTr("将客户端代理指向捕获端口。配置 CA 与 MitM 主机名后可解密 HTTPS 正文。");font.pixelSize:Theme.captionSize;color:page.captureProvider.error.length?Theme.red:Theme.muted}
                Item{Layout.fillHeight:true}
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ColumnLayout{Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;spacing:Theme.gap
                SwirlSearchField{Layout.fillWidth:true;placeholderText:qsTr("筛选域名、方法或状态");onTextChanged:page.query=text}
                Item{Layout.fillWidth:true;Layout.fillHeight:true
                    SwirlDataTable{id:captureTable;objectName:"captureTable";anchors.fill:parent;incrementalRows:true;animateRowChanges:false;rows:page.filteredRows;selectedId:page.selectedId;textPixelSize:12;headerPixelSize:11;columns:[{key:"method",label:"方法",w:80},{key:"host",label:"目标",w:190},{key:"status",label:"状态",w:65},{key:"protocol",label:"类型",w:110},{key:"duration",label:"耗时",w:90},{key:"size",label:"下载",w:90}];onRowSelected:function(row){page.selectedId=row.id}}
                    Item{anchors.fill:parent;anchors.topMargin:captureTable.headerHeight+Theme.dp(8);visible:page.filteredRows.length===0
                        SwirlEmptyState{anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(20));iconName:parent.height<Theme.dp(120)?"":"search";headline:page.query.length?qsTr("没有匹配会话"):qsTr("等待请求");detail:page.captureProvider.running?qsTr("通过捕获端口发送真实请求后，会话会显示在此处。"):qsTr("开始抓包后，请求会显示在此处。")}
                    }
                }
                Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
                RowLayout{Layout.fillWidth:true;SwirlText{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
                text:qsTr("请求详情");font.pixelSize:Theme.bodySize;font.weight:Font.Medium;color:Theme.text;Layout.fillWidth:true}SwirlSegmentedControl{id:detailTabs;options:[qsTr("概览"),qsTr("请求"),qsTr("响应")];Layout.preferredWidth:Theme.dp(228)}}
                ScrollView{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(150);clip:true
                    SwirlTextArea{objectName:"captureDetail";text:page.detailText();readOnly:true;selectByMouse:true;font.pixelSize:Theme.captionSize;wrapMode:TextEdit.Wrap;}
                }
            }
        }
        SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:qsTr("认证、Cookie 与常见 URL 密钥已隐藏。正文预览最多 64 KiB，HTTP 响应上限 2 MiB；HAR 文件仍可能包含请求正文。");color:Theme.muted;font.pixelSize:Theme.captionSize}
    }
    FileDialog{id:exportDialog;title:qsTr("导出真实抓包会话");fileMode:FileDialog.SaveFile;nameFilters:["HTTP Archive (*.har)"];defaultSuffix:"har";onAccepted:if(page.captureProvider.exportHar(selectedFile))AppState.toast=qsTr("真实会话已导出为 HAR。")}
}
