pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string pageId:"dashboard"
    property var features: ({
        processes:["进程名称","活动连接","上传 / 下载","进程策略"],
        requestlogs:["请求时间","目标地址","HTTP 方法","响应状态","匹配规则"],
        dashboard:["速率历史","连接趋势","Latency","最近请求","域名排行","应用排行","策略使用情况"],
        profiles:["本地配置","远程配置","Editor","Import","导出","Backup","Versions"],
        policies:["手动选择","自动选择","Failover","负载均衡","SSID","策略详情","Relationships"],
        subscriptions:["Providers","Update","Scheduling","Quota","节点数量","History","Errors"],
        rules:["规则列表","Type","Target","Priority","Editor","Hits","规则测试"],
        dns:["Resolvers","DoH","DoT","DoQ","查询日志","Cache","Hosts","Fake-IP","IPv6","Tests"],
        traffic:["时间范围","Trends","节点流量","域名流量","进程流量","Protocols","上传 / 下载"],
        tls:["TLS 开关","证书状态","解密域名","排除域名","Sessions","Certificates","信任与撤销"],
        rewrite:["URL","Headers","Body","Redirect","Reject","响应","Editor","命中次数"],
        map:["本地文件","远程 URL","Mappings","Editor","Enable","Preview"],
        breakpoint:["Rules","暂停队列","Headers","Body","Continue","Drop","修改并继续"],
        replay:["请求历史","Editor","Parameters","Response","Compare","执行历史"],
        modules:["Installed","Marketplace","Import","远程模块","Parameters","Versions","Updates"],
        automation:["定时任务","网络触发","Conditions","Actions","History","Editor"],
        api:["本地 API","Permissions","State","CLI","Examples","访问日志"],
        gateway:["Devices","Gateway","DHCP","端口转发","远程设备","Interfaces"],
        logs:["Level","Search","Filters","Details","Timeline","Clear","导出"]
    })

    readonly property var featureList:features[pageId]||[]
    property string selected:""
    property var records:[]
    property var editorBuffers:({})
    property bool componentReady:false
    function regenerate(){records=[];selected=""}
    function updateBuffer(value){if(!componentReady||editorBuffers[selected]===value)return;var next=Object.assign({},editorBuffers);next[selected]=value;editorBuffers=next}
    Component.onCompleted:{componentReady=true;regenerate()}
    onPageIdChanged:if(componentReady)regenerate()
    SwirlArcMotion{id:tabMotion;targetX:Math.max(0,page.featureList.indexOf(page.selected))*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout{
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:AppState.page(page.pageId).title+qsTr("工作区");description:qsTr("选择功能，整理本地编辑草稿。");metadata:qsTr("实际服务尚未接入，草稿不会修改系统或网络")
            SwirlStatusBadge{label:qsTr("研发中");tone:"warning"}
        }
        RowLayout{Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout{Layout.preferredWidth:Theme.dp(230);Layout.fillHeight:true;spacing:Theme.gap
                SwirlText{text:qsTr("功能区域");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                SwirlSearchField{id:search;Layout.fillWidth:true;placeholderText:qsTr("筛选功能")}
                ListView{id:featureListView;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:Theme.dp(4);pixelAligned:true;model:page.featureList.filter(function(name){return String(name).toLowerCase().indexOf(search.text.toLowerCase())>=0})
                    delegate:SwirlButton{required property string modelData;width:featureListView.width;text:modelData;quiet:page.selected!==modelData;onClicked:page.selected=modelData}
                    ScrollBar.vertical:SwirlScrollBar{}
                }
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ColumnLayout{Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;spacing:Theme.gap
                SwirlText{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
                text:page.selected||qsTr("本地草稿");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:page.selected?qsTr("当前功能的编辑内容分别保留在页面中。"):qsTr("从左侧选择功能后编辑草稿。");color:Theme.muted;font.pixelSize:Theme.captionSize}
                ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true
                    SwirlTextArea{text:page.editorBuffers[page.selected]||"";onTextChanged:page.updateBuffer(text);enabled:page.selected.length>0;placeholderText:qsTr("输入本地功能草稿");selectByMouse:true;wrapMode:TextEdit.Wrap;font.family:Theme.codeFontFamily;font.pixelSize:Theme.captionSize;}
                }
                RowLayout{Layout.fillWidth:true;SwirlStatusBadge{label:qsTr("服务未接入");tone:"warning"}Item{Layout.fillWidth:true}SwirlButton{text:qsTr("应用");primary:true;development:true;enabled:false}}
            }
        }
    }
}
