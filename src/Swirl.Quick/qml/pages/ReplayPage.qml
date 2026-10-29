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
    property string selectedRequest:""
    property string requestSection:"Headers"
    property bool componentReady:false
    property var editorBuffers:({Headers:"",Body:"",Cookies:"",Query:""})
    property string resultMessage:qsTr("尚未发送请求。重放服务接入后才会显示真实响应。")
    property var samples:(systemProvider.revision,systemProvider.requests()).slice(0,14)
    property var history:[]
    readonly property var tabs:["Headers","Body","Cookies","Query"]
    function updateBuffer(value){if(!componentReady||editorBuffers[requestSection]===value)return;var next=Object.assign({},editorBuffers);next[requestSection]=value;editorBuffers=next}
    function selectRequest(row){selectedRequest=String(row.id);verb.currentIndex=Math.max(0,verb.model.indexOf(row.method));urlField.text=String(row.url||((row.host||"")+(row.path||"")));editorBuffers={Headers:row.requestHeaders||"",Body:row.requestBody||"",Cookies:"",Query:""}}
    Component.onCompleted:componentReady=true
    SwirlArcMotion{id:tabMotion;targetX:page.tabs.indexOf(page.requestSection)*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout{
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("请求重放");description:qsTr("从本地历史准备请求，分别编辑请求头和正文。");metadata:qsTr("重放服务尚未接入，编辑内容不会发送到网络")
            SwirlButton{text:qsTr("发送请求");primary:true;development:true;enabled:false}
        }
        RowLayout{Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout{Layout.preferredWidth:Theme.dp(230);Layout.fillHeight:true;spacing:Theme.gap
                SwirlText{text:qsTr("本地请求历史");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                SwirlSearchField{id:search;Layout.fillWidth:true;placeholderText:qsTr("筛选请求")}
                ListView{id:requestList;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:Theme.dp(4);pixelAligned:true;reuseItems:true
                    model:page.samples.filter(function(row){return (row.method+" "+row.path).toLowerCase().indexOf(search.text.toLowerCase())>=0})
                    delegate:SwirlButton{required property var modelData;width:requestList.width;implicitHeight:Theme.dp(54);text:modelData.method+"  "+modelData.path;quiet:page.selectedRequest!==String(modelData.id);onClicked:page.selectRequest(modelData)}
                    SwirlEmptyState{anchors.centerIn:parent;width:parent.width;visible:requestList.count===0;headline:qsTr("没有本地请求");detail:qsTr("真实请求记录可在抓包面板查看。")}
                    ScrollBar.vertical:SwirlScrollBar{}
                }
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ColumnLayout{Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;spacing:Theme.gap
                SwirlText{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
                text:qsTr("请求草稿");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                RowLayout{Layout.fillWidth:true;SwirlComboBox{id:verb;model:["GET","POST","PUT","PATCH","DELETE","HEAD"]}SwirlTextField{id:urlField;Layout.fillWidth:true;placeholderText:qsTr("请求 URL")}}
                RowLayout{Layout.fillWidth:true;spacing:Theme.compactGap
                    Repeater{model:page.tabs;delegate:SwirlButton{required property string modelData;objectName:"replaySection-"+modelData;text:modelData;quiet:page.requestSection!==modelData;onClicked:page.requestSection=modelData}}
                }
                ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true
                    SwirlTextArea{id:bodyEditor;objectName:"replayDraftEditor";text:page.editorBuffers[page.requestSection]||"";onTextChanged:page.updateBuffer(text);placeholderText:qsTr("本地请求草稿，不会发送到网络");font.family:Theme.codeFontFamily;font.pixelSize:Theme.captionSize;selectByMouse:true;wrapMode:TextEdit.Wrap;}
                }
                Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
                SwirlText{text:qsTr("响应");color:Theme.text;font.pixelSize:Theme.bodySize;font.weight:Font.Medium}
                SwirlText{Layout.fillWidth:true;text:page.resultMessage;wrapMode:Text.Wrap;color:Theme.muted;font.pixelSize:Theme.captionSize}
                RowLayout{Layout.fillWidth:true;SwirlText{text:qsTr("实际执行 %1 次").arg(page.history.length);color:Theme.muted;font.pixelSize:Theme.captionSize;Layout.fillWidth:true}SwirlButton{text:qsTr("清空当前草稿");onClicked:{page.editorBuffers={Headers:"",Body:"",Cookies:"",Query:""};page.selectedRequest="";urlField.clear()}}}
            }
        }
    }
}
