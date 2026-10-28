import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id:canvas
    property var targetWindow:Window.window
    property Item glassSurface:null
    property bool glassSampled:false
    readonly property Item decorationSource:wings
    readonly property bool splitDecoration:glassSampled && Theme.effectsSupported
    readonly property rect glassBounds:{
        if(!glassSurface)return Qt.rect(0,0,0,0)
        glassSurface.x;glassSurface.y;glassSurface.width;glassSurface.height
        const origin=glassSurface.mapToItem(canvas,0,0)
        return Qt.rect(origin.x,origin.y,glassSurface.width,glassSurface.height)
    }
    SwirlGlassMaterial {anchors.fill:parent;targetWindow:canvas.targetWindow}
    // Five tapered vanes share a swept root and progressively open toward the
    // tip. This is one vector scene, seen directly or through the glass lens.
    Shape {
        id:wings;objectName:"workspaceWingDecoration"
        anchors.fill:parent
        visible:Theme.transparency && !Theme.increaseContrast
        preferredRendererType:Shape.CurveRenderer
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {x1:0;y1:wings.height;x2:wings.width;y2:0;GradientStop {position:0;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.29:0.22)} GradientStop {position:1;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.26:0.19)}}
            startX:-wings.width*.08;startY:wings.height*1.08
            PathCubic {control1X:wings.width*.20;control1Y:wings.height*.88;control2X:wings.width*.34;control2Y:wings.height*.52;x:wings.width*.60;y:wings.height*.50}
            PathCubic {control1X:wings.width*.82;control1Y:wings.height*.48;control2X:wings.width*.91;control2Y:wings.height*.24;x:wings.width*.98;y:wings.height*.18}
            PathCubic {control1X:wings.width*.92;control1Y:wings.height*.39;control2X:wings.width*.80;control2Y:wings.height*.56;x:wings.width*.59;y:wings.height*.55}
            PathCubic {control1X:wings.width*.35;control1Y:wings.height*.57;control2X:wings.width*.19;control2Y:wings.height*.94;x:-wings.width*.08;y:wings.height*1.08}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent";fillColor:Theme.withAlpha(Theme.brandRed,Theme.dark?0.24:0.17)
            startX:-wings.width*.04;startY:wings.height*1.11
            PathCubic {control1X:wings.width*.23;control1Y:wings.height*.93;control2X:wings.width*.39;control2Y:wings.height*.58;x:wings.width*.63;y:wings.height*.57}
            PathCubic {control1X:wings.width*.82;control1Y:wings.height*.56;control2X:wings.width*.92;control2Y:wings.height*.38;x:wings.width*.96;y:wings.height*.34}
            PathCubic {control1X:wings.width*.92;control1Y:wings.height*.52;control2X:wings.width*.80;control2Y:wings.height*.64;x:wings.width*.62;y:wings.height*.62}
            PathCubic {control1X:wings.width*.40;control1Y:wings.height*.63;control2X:wings.width*.22;control2Y:wings.height*.99;x:-wings.width*.04;y:wings.height*1.11}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent";fillColor:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.24:0.16)
            startX:wings.width*.02;startY:wings.height*1.12
            PathCubic {control1X:wings.width*.27;control1Y:wings.height*.98;control2X:wings.width*.43;control2Y:wings.height*.65;x:wings.width*.66;y:wings.height*.65}
            PathCubic {control1X:wings.width*.81;control1Y:wings.height*.66;control2X:wings.width*.92;control2Y:wings.height*.53;x:wings.width*.94;y:wings.height*.49}
            PathCubic {control1X:wings.width*.90;control1Y:wings.height*.68;control2X:wings.width*.81;control2Y:wings.height*.72;x:wings.width*.65;y:wings.height*.70}
            PathCubic {control1X:wings.width*.45;control1Y:wings.height*.69;control2X:wings.width*.26;control2Y:wings.height*1.03;x:wings.width*.02;y:wings.height*1.12}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent";fillColor:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.26:0.18)
            startX:wings.width*.11;startY:wings.height*1.10
            PathCubic {control1X:wings.width*.34;control1Y:wings.height*.97;control2X:wings.width*.49;control2Y:wings.height*.73;x:wings.width*.70;y:wings.height*.73}
            PathCubic {control1X:wings.width*.84;control1Y:wings.height*.75;control2X:wings.width*.92;control2Y:wings.height*.65;x:wings.width*.92;y:wings.height*.64}
            PathCubic {control1X:wings.width*.89;control1Y:wings.height*.80;control2X:wings.width*.82;control2Y:wings.height*.81;x:wings.width*.69;y:wings.height*.78}
            PathCubic {control1X:wings.width*.50;control1Y:wings.height*.76;control2X:wings.width*.34;control2Y:wings.height*1.02;x:wings.width*.11;y:wings.height*1.10}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent";fillColor:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.24:0.17)
            startX:wings.width*.20;startY:wings.height*1.12
            PathCubic {control1X:wings.width*.41;control1Y:wings.height*1.00;control2X:wings.width*.55;control2Y:wings.height*.82;x:wings.width*.73;y:wings.height*.82}
            PathCubic {control1X:wings.width*.83;control1Y:wings.height*.85;control2X:wings.width*.89;control2Y:wings.height*.80;x:wings.width*.91;y:wings.height*.76}
            PathCubic {control1X:wings.width*.88;control1Y:wings.height*.92;control2X:wings.width*.81;control2Y:wings.height*.91;x:wings.width*.72;y:wings.height*.87}
            PathCubic {control1X:wings.width*.56;control1Y:wings.height*.85;control2X:wings.width*.41;control2Y:wings.height*1.05;x:wings.width*.20;y:wings.height*1.12}
        }
    }

    ShaderEffectSource {
        id:wingTexture
        sourceItem:canvas.splitDecoration?wings:null
        hideSource:canvas.splitDecoration;visible:false
        live:canvas.visible && (!canvas.targetWindow || canvas.targetWindow.visibility!==Window.Minimized)
        smooth:true
        textureSize:Qt.size(Math.max(1,Math.ceil(canvas.width)),Math.max(1,Math.ceil(canvas.height)))
    }
    ShaderEffect {
        anchors.fill:parent;visible:canvas.splitDecoration && wings.visible
        property var source:wingTexture
        property vector2d surfaceSize:Qt.vector2d(width,height)
        property vector4d glassRect:Qt.vector4d(canvas.glassBounds.x,canvas.glassBounds.y,canvas.glassBounds.width,canvas.glassBounds.height)
        property real cornerRadius:Theme.sidebarRadius
        property real glassActive:1
        fragmentShader:"qrc:/swirl/shaders/workspace-wing.frag.qsb"
    }
}
