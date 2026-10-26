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
    property string tab:"Tasks"
    property var selected:null
    property var jobs:[]
    readonly property var tabs:["Tasks","History","Conditions"]
    SwirlArcMotion{id:tabMotion;targetX:page.tabs.indexOf(page.tab)*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("自动化");description:qsTr("整理触发条件和动作草稿。");metadata:qsTr("任务服务未接入，当前不会监听事件或执行动作")
            SwirlStatusBadge{label:qsTr("研发中");tone:"warning"}
        }
        RowLayout{Layout.fillWidth:true;spacing:Theme.compactGap;Repeater{model:page.tabs;delegate:SwirlButton{required property string modelData;objectName:"automationSection-"+modelData;text:AppState.zh(modelData);quiet:page.tab!==modelData;onClicked:page.tab=modelData}}Item{Layout.fillWidth:true}}
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout {
                Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0
                                SwirlDataTable{visible:page.tab==="Tasks"&&page.jobs.length>0;Layout.fillWidth:true;Layout.fillHeight:true;rows:page.jobs;fillEmptyRows:false;columns:[{key:"name",label:"任务",w:220},{key:"trigger",label:"触发条件",w:160},{key:"state",label:"状态",w:100}];onRowSelected:function(row){page.selected=row}}
                SwirlEmptyState{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
Layout.fillWidth:true;Layout.fillHeight:true;visible:page.tab!=="Tasks"||page.jobs.length===0;headline:page.tab==="History"?qsTr("还没有执行历史"):page.tab==="Conditions"?qsTr("触发服务待接入"):qsTr("还没有自动化任务");detail:page.tab==="History"?qsTr("只有实际执行后的任务才会进入历史。"):qsTr("右侧可编辑本地草稿。保存与任务执行将在服务接入后提供。")}
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ScrollView {
                id:editorScroll;Layout.preferredWidth:Theme.dp(300);Layout.fillHeight:true;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout{width:editorScroll.availableWidth;spacing:Theme.gap
                    SwirlText{text:qsTr("任务草稿");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                    SwirlTextField{Layout.fillWidth:true;placeholderText:qsTr("任务名称")}
                    SwirlText{text:qsTr("触发条件");color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlComboBox{Layout.fillWidth:true;model:[qsTr("定时"),qsTr("网络变化"),qsTr("HTTP 事件"),qsTr("DNS 事件"),qsTr("错误事件")]}
                    SwirlTextField{Layout.fillWidth:true;placeholderText:qsTr("定时表达式或事件筛选")}
                    SwirlText{text:qsTr("动作");color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlComboBox{Layout.fillWidth:true;model:[qsTr("刷新配置"),qsTr("选择代理"),qsTr("记录日志"),qsTr("运行脚本"),qsTr("通知")]}
                    SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:qsTr("草稿不会修改网络配置，也不会运行脚本。");color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlButton{Layout.fillWidth:true;text:qsTr("保存任务");primary:true;development:true;enabled:false}
                }
            }
        }
    }
}
