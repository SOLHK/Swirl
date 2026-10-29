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
    property string selectedTab:"本地映射"
    property var selection:null
    property var entries:[]
    property bool componentReady:false
    property var editorBuffers:({})
    readonly property var visibleRows:entries.filter(function(row){return row.type===page.selectedTab&&(row.name+" "+row.match+" "+row.target).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    function updateBuffer(key,value){if(!componentReady)return;var current=editorBuffers[selectedTab]||{};if(current[key]===value)return;var next=Object.assign({},editorBuffers);next[selectedTab]=Object.assign({},current);next[selectedTab][key]=value;editorBuffers=next}
    Component.onCompleted:componentReady=true
    SwirlArcMotion{id:tabMotion;targetX:["本地映射","远程映射"].indexOf(page.selectedTab)*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("响应映射");description:qsTr("编辑请求匹配与替换目标。");metadata:qsTr("映射服务尚未接入，不会读取文件或重定向请求")
            SwirlStatusBadge{label:qsTr("研发中");tone:"warning"}
        }
        RowLayout{Layout.fillWidth:true;spacing:Theme.gap
            RowLayout{Layout.preferredWidth:Theme.dp(260);spacing:Theme.compactGap;Repeater{model:["本地映射","远程映射"];delegate:SwirlButton{required property string modelData;objectName:"mapSection-"+modelData;text:modelData;quiet:page.selectedTab!==modelData;onClicked:page.selectedTab=modelData}}}
            SwirlSearchField{id:search;Layout.fillWidth:true;placeholderText:qsTr("筛选已保存映射")}
        }
        RowLayout{Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ColumnLayout{Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0
                SwirlDataTable{visible:page.visibleRows.length>0;Layout.fillWidth:true;Layout.fillHeight:true;rows:page.visibleRows;selectedId:page.selection?page.selection.id:"";columns:[{key:"name",label:"映射",w:160},{key:"match",label:"请求 URL",w:260},{key:"target",label:"目标",w:240}];onRowSelected:function(row){page.selection=row;page.updateBuffer("name",row.name);page.updateBuffer("match",row.match);page.updateBuffer("target",row.target)}}
                SwirlEmptyState{Layout.fillWidth:true;Layout.fillHeight:true;visible:page.visibleRows.length===0;headline:qsTr("还没有映射");detail:qsTr("右侧可编辑本地草稿。保存与响应替换将在服务接入后提供。")}
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ScrollView{id:editorScroll;Layout.preferredWidth:Theme.dp(310);Layout.fillHeight:true;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout{width:editorScroll.availableWidth;spacing:Theme.gap

                    SwirlText{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
                    text:page.selectedTab;color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                    SwirlTextField{id:nameField;Layout.fillWidth:true;text:(page.editorBuffers[page.selectedTab]||{}).name||"";onTextChanged:page.updateBuffer("name",text);placeholderText:qsTr("映射名称")}
                    SwirlText{text:qsTr("匹配请求");color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlTextField{id:matchField;objectName:"mapDraftMatch";Layout.fillWidth:true;text:(page.editorBuffers[page.selectedTab]||{}).match||"";onTextChanged:page.updateBuffer("match",text);placeholderText:"https://example.test/*"}
                    SwirlText{text:page.selectedTab==="本地映射"?qsTr("本地文件路径"):qsTr("替换 URL");color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlTextField{id:targetField;Layout.fillWidth:true;text:(page.editorBuffers[page.selectedTab]||{}).target||"";onTextChanged:page.updateBuffer("target",text);placeholderText:page.selectedTab==="本地映射"?"fixtures/response.json":"https://mirror.example.test/"}
                    Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
                    SwirlText{text:qsTr("映射预览");color:Theme.text;font.pixelSize:Theme.bodySize;font.weight:Font.Medium}
                    SwirlText{Layout.fillWidth:true;wrapMode:Text.WrapAnywhere;text:(matchField.text||qsTr("请求 URL"))+"\n↓\n"+(targetField.text||qsTr("替换目标"));color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlButton{Layout.fillWidth:true;text:qsTr("保存映射");primary:true;development:true;enabled:false}
                }
            }
        }
    }
}
