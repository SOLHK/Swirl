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
    property string tab:"API 管理"
    property var routes:[]
    readonly property var tabs:["API 管理","命令行指令","Permissions","访问日志"]
    SwirlArcMotion{id:tabMotion;targetX:page.tabs.indexOf(page.tab)*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("本地控制 API");description:qsTr("准备请求草稿，查看接口接入状态。");metadata:qsTr("API 服务尚未启动")
            SwirlStatusBadge{label:qsTr("研发中");tone:"warning"}
        }
        RowLayout{Layout.fillWidth:true;spacing:Theme.compactGap;Repeater{model:page.tabs;delegate:SwirlButton{required property string modelData;objectName:"apiSection-"+modelData;text:AppState.zh(modelData);quiet:page.tab!==modelData;onClicked:page.tab=modelData}}Item{Layout.fillWidth:true}}
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout {
                Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;spacing:Theme.gap
                                SwirlDataTable{visible:page.tab==="API 管理"&&page.routes.length>0;Layout.fillWidth:true;Layout.fillHeight:true;rows:page.routes;fillEmptyRows:false;columns:[{key:"method",label:"方法",w:80},{key:"path",label:"端点",w:240},{key:"permission",label:"权限",w:150}];onRowSelected:function(row){pathInput.text=row.path;methodInput.currentIndex=Math.max(0,methodInput.model.indexOf(row.method))}}
                SwirlEmptyState{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
Layout.fillWidth:true;Layout.fillHeight:true;visible:page.tab!=="API 管理"||page.routes.length===0;headline:page.tab==="访问日志"?qsTr("没有访问日志"):page.tab==="Permissions"?qsTr("尚未授予访问权限"):page.tab==="命令行指令"?qsTr("命令行接口待接入"):qsTr("接口目录待接入");detail:page.tab==="访问日志"?qsTr("API 服务启动后才会生成真实访问记录。"):page.tab==="Permissions"?qsTr("当前没有可用的外部访问授权。"):page.tab==="命令行指令"?qsTr("当前没有可执行的命令行指令。"):qsTr("请求编辑仅保存在当前页面，不会建立监听或发送请求。")}
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ColumnLayout {
                Layout.preferredWidth:Theme.dp(280);Layout.fillHeight:true;spacing:Theme.gap
                SwirlText{text:qsTr("请求草稿");font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold;color:Theme.text}
                SwirlText{text:qsTr("请求方法");color:Theme.muted;font.pixelSize:Theme.captionSize}
                SwirlComboBox{id:methodInput;Layout.fillWidth:true;model:["GET","POST","PUT","DELETE"]}
                SwirlText{text:qsTr("接口路径");color:Theme.muted;font.pixelSize:Theme.captionSize}
                SwirlTextField{id:pathInput;Layout.fillWidth:true;text:"/v1/status";placeholderText:"/v1/status"}
                Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
                SwirlText{text:qsTr("响应");color:Theme.text;font.pixelSize:Theme.bodySize;font.weight:Font.Medium}
                SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:qsTr("尚未发送请求。服务接入后才会显示真实响应。");color:Theme.muted;font.pixelSize:Theme.captionSize}
                Item{Layout.fillHeight:true}
                SwirlButton{text:qsTr("发送请求");primary:true;development:true;enabled:false;Layout.fillWidth:true}
            }
        }
    }
}
