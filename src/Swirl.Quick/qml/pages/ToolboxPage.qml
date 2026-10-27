pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:true
    property string tool:"DNS 查询"
    property string result:qsTr("此工具尚未接入执行服务。上方网络诊断使用真实测量。")
    property var tools:["DNS 查询","TCP 连通性","Traceroute","HTTP 请求","TLS 证书检查","端口检查","IP 地址查询","Whois","连接测试","网络接口信息"]
    property string networkType:""
    property bool componentReady:false
    function refreshNetwork(){networkType=systemProvider.currentNetwork().type||""}
    Component.onCompleted:{componentReady=true;refreshNetwork()}
    Connections{target:page.componentReady?page:null;function onVisibleChanged(){if(page.visible)page.refreshNetwork()}}
    readonly property bool measuring:engineController.telemetry.measurementState==="正在测量"
    readonly property string measurementPhase:page.measuring?"pending":/^\d+ ms$/.test(engineController.telemetry.latencies.internet||"")?"succeeded":engineController.telemetry.measurementState==="测量完成"?"failed":"idle"
    SwirlArcMotion{id:tabMotion;targetX:Math.max(0,page.tools.indexOf(page.tool))*SwirlMotion.pageDistance;duration:SwirlMotion.selectionDuration;bend:SwirlMotion.pageArc;motionEnabled:page.visible}
    ColumnLayout{
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("网络诊断");description:qsTr("分别查看 HTTPS 请求、网关 ICMP 与 DNS 查询耗时。");metadata:qsTr("各项分别采样，HTTPS 请求耗时包含连接、TLS 与目标响应")
            SwirlButton{objectName:"toolboxMeasure";text:page.measuring?qsTr("检测中…"):qsTr("开始检测");primary:true;enabled:!page.measuring;onClicked:{page.refreshNetwork();engineController.telemetry.measureNetwork();if(engineController.selectedNodeId.length&&!engineController.tests.busy)engineController.testSelectedNode(engineController.selectedNodeId,"https://www.gstatic.com/generate_204")}}
        }
        RowLayout{Layout.fillWidth:true;spacing:Theme.gap
            SwirlFlow{Layout.preferredWidth:Theme.dp(48);Layout.preferredHeight:Theme.dp(20);phase:page.measurementPhase}
            SwirlText{text:engineController.telemetry.measurementState||qsTr("尚未检测");color:Theme.muted;font.pixelSize:Theme.captionSize;Layout.fillWidth:true}
            SwirlText{text:qsTr("外部 IP：%1").arg(engineController.telemetry.externalIp||qsTr("未检测"))+" · "+page.networkType;color:Theme.muted;font.pixelSize:Theme.captionSize}
        }
        GridLayout{Layout.fillWidth:true;columns:3;columnSpacing:Theme.sectionGap
            Repeater{model:[{label:qsTr("HTTPS 请求"),key:"internet"},{label:qsTr("网关 ICMP"),key:"router"},{label:qsTr("DNS 查询"),key:"dns"}]
                ColumnLayout{required property var modelData;Layout.fillWidth:true;Layout.minimumWidth:0;spacing:Theme.dp(6)
                    SwirlText{text:modelData.label;color:Theme.muted;font.pixelSize:Theme.captionSize}
                    SwirlText{text:engineController.telemetry.latencies[modelData.key]||qsTr("未采集");color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight}
                }
            }
        }
        Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
        RowLayout{Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.sectionGap
            ListView{id:toolList;Layout.preferredWidth:Theme.dp(220);Layout.fillHeight:true;pixelAligned:true;clip:true;spacing:Theme.dp(4);model:page.tools
                delegate:SwirlButton{required property string modelData;width:toolList.width;text:modelData;quiet:page.tool!==modelData;onClicked:page.tool=modelData}
                ScrollBar.vertical:SwirlScrollBar{}
            }
            Rectangle{Layout.fillHeight:true;Layout.preferredWidth:Theme.dp(1);color:Theme.border}
            ColumnLayout{Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;spacing:Theme.gap
                SwirlText{transform:Translate{x:tabMotion.position.x-tabMotion.targetX;y:tabMotion.position.y}
                text:page.tool;color:Theme.text;font.pixelSize:Theme.sectionTitleSize;font.weight:Font.DemiBold}
                SwirlText{Layout.fillWidth:true;wrapMode:Text.Wrap;text:qsTr("当前可编辑检查目标，执行服务尚未接入。");color:Theme.muted;font.pixelSize:Theme.captionSize}
                SwirlTextField{id:target;Layout.fillWidth:true;placeholderText:page.tool==="网络接口信息"?qsTr("网卡名称"):page.tool==="HTTP 请求"?"https://example.test/path":"example.test"}
                RowLayout{Layout.fillWidth:true
                    SwirlComboBox{visible:page.tool==="HTTP 请求";model:["GET","POST","PUT","DELETE","HEAD"]}
                    SwirlTextField{visible:page.tool==="端口检查"||page.tool==="TCP 连通性";Layout.preferredWidth:Theme.dp(150);placeholderText:qsTr("端口（443）");validator:IntValidator{bottom:1;top:65535}}
                    Item{Layout.fillWidth:true}
                    SwirlButton{text:qsTr("运行工具");primary:true;development:true;enabled:false}
                }
                ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true
                    SwirlTextArea{readOnly:true;selectByMouse:true;text:page.result;font.pixelSize:Theme.captionSize;wrapMode:TextEdit.Wrap;}
                }
            }
        }
    }
}
