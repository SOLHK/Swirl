import QtQuick
import SwirlQuick
Item {
    id: blur
    property url imageSource
    property real strength: Theme.glassBlurStrength
    property int quality: Theme.glassQuality
    readonly property var texture: upCapture
    readonly property int textureExtent: quality===0?512:quality===1?768:1024
    readonly property int textureWidth: textureExtent
    readonly property int textureHeight: Math.max(1,Math.round(textureExtent*(image.implicitHeight||1)/(image.implicitWidth||1)))
    readonly property bool ready: image.status===Image.Ready
    visible:false
    function invalidate() { downCapture.scheduleUpdate();lowCapture.scheduleUpdate();midCapture.scheduleUpdate();upCapture.scheduleUpdate() }
    onStrengthChanged:Qt.callLater(invalidate)
    onQualityChanged:Qt.callLater(invalidate)
    Image { id:image; source:blur.imageSource; asynchronous:true; sourceSize:Qt.size(2048,2048); onStatusChanged:if(status===Image.Ready)Qt.callLater(blur.invalidate) }
    component Pass:ShaderEffect {
        property var source
        property vector2d stepSize
        property real upscale:0
        fragmentShader:"qrc:/swirl/shaders/swirl-blur.frag.qsb"
    }
    Pass {id:down; width:blur.textureWidth/2;height:blur.textureHeight/2;source:image;stepSize:Qt.vector2d(blur.strength/blur.textureWidth,blur.strength/blur.textureHeight)}
    ShaderEffectSource {id:downCapture;sourceItem:down;hideSource:true;live:false;smooth:true;textureSize:Qt.size(down.width,down.height)}
    Pass {id:low;width:blur.textureWidth/4;height:blur.textureHeight/4;source:downCapture;stepSize:Qt.vector2d(blur.strength/down.width,blur.strength/down.height)}
    ShaderEffectSource {id:lowCapture;sourceItem:low;hideSource:true;live:false;smooth:true;textureSize:Qt.size(low.width,low.height)}
    Pass {id:mid;width:down.width;height:down.height;source:lowCapture;upscale:1;stepSize:Qt.vector2d(blur.strength/low.width,blur.strength/low.height)}
    ShaderEffectSource {id:midCapture;sourceItem:mid;hideSource:true;live:false;smooth:true;textureSize:Qt.size(mid.width,mid.height)}
    Pass {id:up;width:blur.textureWidth;height:blur.textureHeight;source:midCapture;upscale:1;stepSize:Qt.vector2d(blur.strength/mid.width,blur.strength/mid.height)}
    ShaderEffectSource {id:upCapture;sourceItem:up;hideSource:true;live:false;smooth:true;textureSize:Qt.size(up.width,up.height)}
}
