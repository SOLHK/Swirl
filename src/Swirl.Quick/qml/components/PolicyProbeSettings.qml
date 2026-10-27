pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

ColumnLayout {
    id:settings
    property var value:({})
    property bool editable:true
    property bool toleranceVisible:false
    readonly property bool acceptableInput:intervalField.acceptableInput&&timeoutField.acceptableInput&&statusField.acceptableInput&&successField.acceptableInput&&failureField.acceptableInput&&cooldownField.acceptableInput&&(!toleranceVisible||toleranceField.acceptableInput)&&urlField.text.trim().length>0
    signal edited(var probe)
    function numeric(text,scale) {return /^\d+(\.\d{1,3})?$/.test(text)?Math.round(Number(text)*scale):text}
    function publish() {
        const probe=Policy.copy(value);probe.url=urlField.text.trim();probe.interval_ms=numeric(intervalField.text,1000);probe.timeout_ms=numeric(timeoutField.text,1)
        probe.expected_status=numeric(statusField.text,1);probe.success_threshold=numeric(successField.text,1);probe.failure_threshold=numeric(failureField.text,1)
        probe.switch_cooldown_ms=numeric(cooldownField.text,1000);probe.tolerance_ms=toleranceVisible?numeric(toleranceField.text,1):0;edited(probe)
    }
    spacing:Theme.dp(10)
    SwirlText {text:qsTr("健康检测地址");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
    SwirlTextField {id:urlField;objectName:"policyProbeUrl";Layout.fillWidth:true;text:String(settings.value.url||"");enabled:settings.editable;placeholderText:"https://…";Accessible.name:qsTr("健康检测地址");onTextEdited:settings.publish()}
    GridLayout {
        Layout.fillWidth:true;columns:2;columnSpacing:Theme.dp(12);rowSpacing:Theme.dp(8)
        SwirlText {text:qsTr("检测间隔（秒）");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:intervalField;objectName:"policyProbeInterval";Layout.fillWidth:true;text:String(Number(settings.value.interval_ms)/1000);enabled:settings.editable;validator:DoubleValidator {bottom:1;top:3600;decimals:3;notation:DoubleValidator.StandardNotation}Accessible.name:qsTr("检测间隔，秒");onTextEdited:settings.publish()}
        SwirlText {text:qsTr("超时（毫秒）");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:timeoutField;objectName:"policyProbeTimeout";Layout.fillWidth:true;text:String(settings.value.timeout_ms);enabled:settings.editable;validator:IntValidator {bottom:100;top:30000}Accessible.name:qsTr("检测超时，毫秒");onTextEdited:settings.publish()}
        SwirlText {text:qsTr("成功状态码");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:statusField;objectName:"policyProbeExpectedStatus";Layout.fillWidth:true;text:String(settings.value.expected_status);enabled:settings.editable;validator:IntValidator {bottom:200;top:299}Accessible.name:qsTr("检测成功 HTTP 状态码");onTextEdited:settings.publish()}
        SwirlText {text:qsTr("连续成功次数");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:successField;objectName:"policyProbeSuccessThreshold";Layout.fillWidth:true;text:String(settings.value.success_threshold);enabled:settings.editable;validator:IntValidator {bottom:1;top:10}Accessible.name:qsTr("连续成功次数");onTextEdited:settings.publish()}
        SwirlText {text:qsTr("连续失败次数");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:failureField;objectName:"policyProbeFailureThreshold";Layout.fillWidth:true;text:String(settings.value.failure_threshold);enabled:settings.editable;validator:IntValidator {bottom:1;top:10}Accessible.name:qsTr("连续失败次数");onTextEdited:settings.publish()}
        SwirlText {text:qsTr("切换冷却（秒）");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:cooldownField;objectName:"policyProbeCooldown";Layout.fillWidth:true;text:String(Number(settings.value.switch_cooldown_ms)/1000);enabled:settings.editable;validator:DoubleValidator {bottom:0;top:3600;decimals:3;notation:DoubleValidator.StandardNotation}Accessible.name:qsTr("切换冷却时间，秒");onTextEdited:settings.publish()}
        SwirlText {visible:settings.toleranceVisible;text:qsTr("切换耗时差（毫秒）");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlTextField {id:toleranceField;objectName:"policyProbeTolerance";visible:settings.toleranceVisible;Layout.fillWidth:true;text:String(settings.value.tolerance_ms);enabled:settings.editable;validator:IntValidator {bottom:0;top:10000}Accessible.name:qsTr("自动测速切换的最小耗时差，毫秒");onTextEdited:settings.publish()}
    }
    SwirlText {Layout.fillWidth:true;text:qsTr("失效出口不会因冷却而继续使用；没有健康候选时阻止新连接。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
}
