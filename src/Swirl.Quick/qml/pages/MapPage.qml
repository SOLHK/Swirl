import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string selectedTab:"本地映射"
    property var selection:null
    property var entries:[
        {id:"m1",name:"用户配置示例",match:"https://api.example.test/user",target:"fixtures/user.json",type:"本地映射",status:"Enabled"},
        {id:"m2",name:"静态资源",match:"https://cdn.example.test/*",target:"C:/fixtures/assets/",type:"本地映射",status:"Enabled"},
        {id:"m3",name:"旧版 API 镜像",match:"https://api.example.test/v1/*",target:"https://mirror.example.test/v2/",type:"远程映射",status:"Disabled"}
    ]
    readonly property var visibleRows:entries.filter(function(r){return r.type===selectedTab &&
        (r.name+" "+r.match+" "+r.target).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"响应映射 · 演示"; tone:"accent" }
            Text { text:"不会读取文件或重定向实际请求"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"新建映射"; primary:true; onClicked:newDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["本地映射","远程映射"]
                SwirlButton { text:modelData; quiet:page.selectedTab!==modelData; onClicked:{page.selectedTab=modelData;page.selection=null} }
            }
            Item { Layout.fillWidth:true }
            SwirlSearchField { id:search; implicitWidth:260; placeholderText:"筛选映射 URL" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.visibleRows
                    selectedId:page.selection?page.selection.id:""
                    columns:[{key:"name",label:"MAPPING",w:180},{key:"match",label:"请求 URL",w:280},
                             {key:"target",label:"REPLACEMENT",w:270},{key:"status",label:"STATE",w:105}]
                    onRowSelected:function(r){page.selection=r;nameField.text=r.name;matchField.text=r.match;targetField.text=r.target}
                }
                SwirlEmptyState { visible:page.visibleRows.length===0; anchors.centerIn:parent; headline:"暂无映射" }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:313; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:12
                    Text { text:"映射详情"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.selectedTab; color:Theme.muted; font.pixelSize:11 }
                    Text { text:"显示名称"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { id:nameField; Layout.fillWidth:true; placeholderText:"映射名称" }
                    Text { text:"匹配请求 URL"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { id:matchField; Layout.fillWidth:true; placeholderText:"https://example.test/*" }
                    Text { text:page.selectedTab==="本地映射"?"替换文件或目录":"远程替换 URL"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { id:targetField; Layout.fillWidth:true; placeholderText:page.selectedTab==="本地映射"?"fixtures/file.json":"https://mirror.example.test/" }
                    Text { text:"PREVIEW"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        Text {
                            anchors.fill:parent; anchors.margins:12
                            text:(matchField.text||"原始 URL")+"\n  ↓\n"+(targetField.text||"替换目标")+
                                 "\n\nNo network or filesystem operation is performed."
                            color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:11; wrapMode:Text.WrapAnywhere
                        }
                    }
                    SwirlButton {
                        text:"保存演示映射"; primary:true
                        enabled:page.selection&&matchField.text.trim().length>0&&targetField.text.trim().length>0
                        onClicked:{
                            var id=page.selection.id
                            page.entries=page.entries.map(function(r){return r.id===id?
                                {id:r.id,name:nameField.text,match:matchField.text,target:targetField.text,type:r.type,status:r.status}:r})
                            AppState.notice("保存映射")
                        }
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"创建响应映射"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"请求 URL 匹配表达式"; color:Theme.text }
            SwirlTextField { id:urlInput; Layout.fillWidth:true; placeholderText:"https://example.test/api/*" }
            Text { text:page.selectedTab==="本地映射"?"本地模拟文件路径":"远程替换 URL"; color:Theme.text }
            SwirlTextField { id:destination; Layout.fillWidth:true; placeholderText:page.selectedTab==="本地映射"?"fixtures/response.json":"https://mirror.example.test/" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:newDialog.close() }
                SwirlButton {
                    text:"添加演示"; primary:true
                    enabled:urlInput.text.startsWith("https://")&&destination.text.trim().length>0
                    onClicked:{
                        page.entries=page.entries.concat([{id:"m"+Date.now(),name:"新建映射",
                            match:urlInput.text.trim(),target:destination.text.trim(),type:page.selectedTab,status:"Enabled"}])
                        urlInput.text="";destination.text="";newDialog.close()
                    }
                }
            }
        }
    }
}