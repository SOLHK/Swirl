import QtQuick
import SwirlQuick

// Application-scene sampling only. The source must be a sibling scene that
// does not contain this material; this never captures the desktop behind HWND.
Item {
    id:glass
    property Item backdropSource:null
    property real cornerRadius:Theme.sidebarRadius
    property real interaction:0
    property point lightPoint:Qt.point(0.18,0.15)
    property real blurRadius:Theme.dp(7)
    property real refraction:Theme.dp(2.4)
    // A width-changing shell can keep one texture allocation for its maximum
    // envelope while sourceRect and shader geometry follow the live width.
    property real captureWidth:width
    readonly property real samplePadding:Theme.dp(16)
    readonly property bool windowVisible:!Window.window || (Window.window.visible && Window.window.visibility!==Window.Minimized)
    readonly property bool sampled:Theme.effectsSupported && Theme.transparency && !Theme.increaseContrast && backdropSource!==null
    readonly property real captureScale:Math.min(1,Screen.devicePixelRatio*0.6)
    readonly property size captureSize:Qt.size(Math.max(1,Math.ceil((captureWidth+2*samplePadding)*captureScale)),Math.max(1,Math.ceil((height+2*samplePadding)*captureScale)))
    readonly property point sampleOrigin:{glass.x;glass.y;glass.width;glass.height;return backdropSource?glass.mapToItem(backdropSource,-samplePadding,-samplePadding):Qt.point(0,0)}
    readonly property int shaderStatus:material.status
    readonly property string shaderLog:material.log
    readonly property bool captureLive:capture.live
    ShaderEffectSource {
        id:capture
        sourceItem:glass.sampled?glass.backdropSource:null
        sourceRect:Qt.rect(glass.sampleOrigin.x,glass.sampleOrigin.y,glass.width+2*glass.samplePadding,glass.height+2*glass.samplePadding)
        textureSize:glass.captureSize
        live:glass.sampled && glass.visible && glass.windowVisible
        recursive:false
        hideSource:false
        visible:false
        smooth:true
        wrapMode:ShaderEffectSource.ClampToEdge
    }
    ShaderEffect {
        id:horizontalBlur
        width:glass.width+2*glass.samplePadding;height:glass.height+2*glass.samplePadding
        visible:false
        property var source:capture
        property vector2d stepSize:Qt.vector2d(glass.blurRadius/4/Math.max(1,width),0)
        property real upscale:2
        fragmentShader:"qrc:/swirl/shaders/swirl-blur.frag.qsb"
    }
    ShaderEffectSource {
        id:softened
        sourceItem:glass.sampled?horizontalBlur:null
        textureSize:glass.captureSize
        live:capture.live
        visible:false;hideSource:true;smooth:true
        recursive:false;wrapMode:ShaderEffectSource.ClampToEdge
    }
    ShaderEffect {
        id:material;objectName:"sidebarLiquidShader"
        anchors.fill:parent
        visible:glass.sampled
        property var source:softened
        property vector2d surfaceSize:Qt.vector2d(width,height)
        property vector2d textureExtent:Qt.vector2d(glass.captureSize.width,glass.captureSize.height)
        property real padding:glass.samplePadding
        property real cornerRadius:glass.cornerRadius
        property real blurRadius:glass.blurRadius
        property real refraction:glass.refraction
        property real interaction:glass.interaction
        property vector2d lightPoint:Qt.vector2d(glass.lightPoint.x,glass.lightPoint.y)
        property color tintColor:Theme.dark?"#182A40":"#FFFFFF"
        property real tintAmount:Theme.dark?0.28:0.38
        property real darkMode:Theme.dark?1:0
        fragmentShader:"qrc:/swirl/shaders/sidebar-liquid.frag.qsb"
    }
    SwirlShellOutline {
        anchors.fill:parent;visible:!glass.sampled;radius:glass.cornerRadius
        fillColor:Theme.surface
        strokeColor:Theme.increaseContrast?Theme.text:Theme.border
    }
    Accessible.ignored:true
}
