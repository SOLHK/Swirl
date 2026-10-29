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
    property var records:[]
    property var selected:null
    property string tab:"Headers"
    property string payload:""
    property bool componentReady:false
    property var editorBuffers:({Headers:"",Body:"",Query:""})
    readonly property var tabs:["Headers","Body","Query"]
    function updateBuffer(value){if(!componentReady||editorBuffers[tab]===value)return;var next=Object.assign({},editorBuffers);next[tab]=value;editorBuffers=next}
    Component.onCompleted:componentReady=true
    SwirlArcMotion{id:tabMotion;targetX:page.tabs.indexOf(page.tab)*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("断点");description:qsTr("查看暂停队列，准备请求编辑草稿。");metadata:qsTr("实时拦截未接入，当前不会暂停浏览器请求")
            SwirlStatusBadge{label:qsTr("研发中");tone:"warning"}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout {
                Layout.preferredWidth:Theme.dp(280);Layout.fillHeight:true;spacing:Theme.gap
                SwirlText{text:qsTr("暂停队列");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                SwirlDataTable{visible:page.records.length>0;Layout.fillWidth:true;Layout.fillHeight:true;rows:page.records;selectedId:page.selected?page.selected.id:"";columns:[{key:"method",label:"方法",w:80},{key:"url",label:"请求",w:240}];onRowSelected:function(row){page.selected=row}}
                SwirlEmptyState{Layout.fillWidth:true;Layout.fillHeight:true;visible:page.records.length===0;headline:qsTr("没有暂停的请求");detail:qsTr("拦截服务接入后，真实暂停的请求才会显示在此处。")}
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ColumnLayout {
                Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;spacing:Theme.gap
                SwirlText{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
                text:qsTr("本地请求草稿");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                SwirlSegmentedControl{objectName:"breakpointLocalTabs";Layout.fillWidth:true;options:[qsTr("请求头"),qsTr("正文"),qsTr("查询参数")];currentIndex:page.tabs.indexOf(page.tab);onActivated:function(index){page.tab=page.tabs[index]}}
                ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true
                    SwirlTextArea{id:editor;objectName:"breakpointLocalEditor";text:page.editorBuffers[page.tab]||"";onTextChanged:page.updateBuffer(text);placeholderText:page.tab==="Headers"?qsTr("编辑请求头草稿"):page.tab==="Body"?qsTr("编辑请求正文草稿"):qsTr("编辑查询参数草稿");font.family:Theme.codeFontFamily;font.pixelSize:Theme.captionSize;selectByMouse:true;wrapMode:TextEdit.Wrap;}
                }
                SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:qsTr("不同页签分别保留内容。当前草稿不会进入实际网络。");color:Theme.muted;font.pixelSize:Theme.captionSize}
                RowLayout{Layout.fillWidth:true;SwirlButton{text:qsTr("继续请求");primary:true;development:true;enabled:false}SwirlButton{text:qsTr("丢弃请求");danger:true;development:true;enabled:false}Item{Layout.fillWidth:true}}
            }
        }
    }
}
