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
    // Each vane has a transparent body, an absorptive fold and a short reflected
    // ridge. All three follow the same cubic sweep and remain one vector source.
    Shape {
        id:wings;objectName:"workspaceWingDecoration"
        anchors.fill:parent
        visible:Theme.transparency && !Theme.increaseContrast
        preferredRendererType:Shape.CurveRenderer
        Accessible.ignored:true
        // Orange: a thin root opens into an unequal, tapered vane.
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*-0.09;y1:wings.height*1.08;x2:wings.width*0.98;y2:wings.height*0.17
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.12:0.09)}
                GradientStop {position:0.36;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.18:0.13)}
                GradientStop {position:0.64;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.1:0.065)}
                GradientStop {position:0.84;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.19:0.14)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.065:0.035)}
            }
            startX:wings.width*-0.09;startY:wings.height*1.08
            PathCubic {control1X:wings.width*0.18;control1Y:wings.height*0.91;control2X:wings.width*0.38;control2Y:wings.height*0.54;x:wings.width*0.6;y:wings.height*0.505}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.48;control2X:wings.width*0.94;control2Y:wings.height*0.25;x:wings.width*0.98;y:wings.height*0.17}
            PathCubic {control1X:wings.width*0.94;control1Y:wings.height*0.39;control2X:wings.width*0.81;control2Y:wings.height*0.57;x:wings.width*0.595;y:wings.height*0.552}
            PathCubic {control1X:wings.width*0.38;control1Y:wings.height*0.59;control2X:wings.width*0.18;control2Y:wings.height*0.99;x:wings.width*-0.09;y:wings.height*1.08}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*-0.09;y1:wings.height*1.08;x2:wings.width*0.98;y2:wings.height*0.17
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandOrange,0)}
                GradientStop {position:0.28;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.065:0.035)}
                GradientStop {position:0.6;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.25:0.2)}
                GradientStop {position:0.82;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.3:0.24)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandOrange,Theme.dark?0.18:0.12)}
            }
            startX:wings.width*-0.09;startY:wings.height*1.08
            PathCubic {control1X:wings.width*0.18;control1Y:wings.height*0.94;control2X:wings.width*0.39;control2Y:wings.height*0.575;x:wings.width*0.6;y:wings.height*0.537}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.54;control2X:wings.width*0.94;control2Y:wings.height*0.335;x:wings.width*0.98;y:wings.height*0.17}
            PathCubic {control1X:wings.width*0.94;control1Y:wings.height*0.39;control2X:wings.width*0.81;control2Y:wings.height*0.57;x:wings.width*0.595;y:wings.height*0.552}
            PathCubic {control1X:wings.width*0.38;control1Y:wings.height*0.59;control2X:wings.width*0.18;control2Y:wings.height*0.99;x:wings.width*-0.09;y:wings.height*1.08}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*-0.09;y1:wings.height*1.08;x2:wings.width*0.98;y2:wings.height*0.17
                GradientStop {position:0;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.35;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.61;color:Theme.withAlpha("white",Theme.dark?0.1:0.42)}
                GradientStop {position:0.77;color:Theme.withAlpha("white",Theme.dark?0.25:0.76)}
                GradientStop {position:0.92;color:Theme.withAlpha("white",Theme.dark?0.07:0.22)}
                GradientStop {position:1;color:Theme.withAlpha("white",0)}
            }
            startX:wings.width*-0.09;startY:wings.height*1.08
            PathCubic {control1X:wings.width*0.18;control1Y:wings.height*0.94;control2X:wings.width*0.39;control2Y:wings.height*0.575;x:wings.width*0.6;y:wings.height*0.537}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.54;control2X:wings.width*0.94;control2Y:wings.height*0.335;x:wings.width*0.98;y:wings.height*0.17}
            PathCubic {control1X:wings.width*0.94;control1Y:wings.height*0.3376;control2X:wings.width*0.8;control2Y:wings.height*0.5426;x:wings.width*0.6;y:wings.height*0.5396}
            PathCubic {control1X:wings.width*0.39;control1Y:wings.height*0.5776;control2X:wings.width*0.18;control2Y:wings.height*0.94;x:wings.width*-0.09;y:wings.height*1.08}
        }
        // Red: a thin root opens into an unequal, tapered vane.
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*-0.04;y1:wings.height*1.12;x2:wings.width*0.967;y2:wings.height*0.333
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.12:0.09)}
                GradientStop {position:0.36;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.18:0.13)}
                GradientStop {position:0.64;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.1:0.065)}
                GradientStop {position:0.84;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.19:0.14)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.065:0.035)}
            }
            startX:wings.width*-0.04;startY:wings.height*1.12
            PathCubic {control1X:wings.width*0.22;control1Y:wings.height*0.94;control2X:wings.width*0.4;control2Y:wings.height*0.62;x:wings.width*0.62;y:wings.height*0.602}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.6;control2X:wings.width*0.91;control2Y:wings.height*0.43;x:wings.width*0.967;y:wings.height*0.333}
            PathCubic {control1X:wings.width*0.93;control1Y:wings.height*0.55;control2X:wings.width*0.81;control2Y:wings.height*0.69;x:wings.width*0.61;y:wings.height*0.66}
            PathCubic {control1X:wings.width*0.4;control1Y:wings.height*0.665;control2X:wings.width*0.23;control2Y:wings.height*1.03;x:wings.width*-0.04;y:wings.height*1.12}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*-0.04;y1:wings.height*1.12;x2:wings.width*0.967;y2:wings.height*0.333
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandRed,0)}
                GradientStop {position:0.28;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.065:0.035)}
                GradientStop {position:0.6;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.25:0.2)}
                GradientStop {position:0.82;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.3:0.24)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandRed,Theme.dark?0.18:0.12)}
            }
            startX:wings.width*-0.04;startY:wings.height*1.12
            PathCubic {control1X:wings.width*0.23;control1Y:wings.height*0.985;control2X:wings.width*0.4;control2Y:wings.height*0.65;x:wings.width*0.615;y:wings.height*0.638}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.66;control2X:wings.width*0.925;control2Y:wings.height*0.505;x:wings.width*0.967;y:wings.height*0.333}
            PathCubic {control1X:wings.width*0.93;control1Y:wings.height*0.55;control2X:wings.width*0.81;control2Y:wings.height*0.69;x:wings.width*0.61;y:wings.height*0.66}
            PathCubic {control1X:wings.width*0.4;control1Y:wings.height*0.665;control2X:wings.width*0.23;control2Y:wings.height*1.03;x:wings.width*-0.04;y:wings.height*1.12}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*-0.04;y1:wings.height*1.12;x2:wings.width*0.967;y2:wings.height*0.333
                GradientStop {position:0;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.35;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.61;color:Theme.withAlpha("white",Theme.dark?0.1:0.42)}
                GradientStop {position:0.77;color:Theme.withAlpha("white",Theme.dark?0.25:0.76)}
                GradientStop {position:0.92;color:Theme.withAlpha("white",Theme.dark?0.07:0.22)}
                GradientStop {position:1;color:Theme.withAlpha("white",0)}
            }
            startX:wings.width*-0.04;startY:wings.height*1.12
            PathCubic {control1X:wings.width*0.23;control1Y:wings.height*0.985;control2X:wings.width*0.4;control2Y:wings.height*0.65;x:wings.width*0.615;y:wings.height*0.638}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.66;control2X:wings.width*0.925;control2Y:wings.height*0.505;x:wings.width*0.967;y:wings.height*0.333}
            PathCubic {control1X:wings.width*0.925;control1Y:wings.height*0.5076;control2X:wings.width*0.8;control2Y:wings.height*0.6626;x:wings.width*0.615;y:wings.height*0.6406}
            PathCubic {control1X:wings.width*0.4;control1Y:wings.height*0.6526;control2X:wings.width*0.23;control2Y:wings.height*0.985;x:wings.width*-0.04;y:wings.height*1.12}
        }
        // Blue: a thin root opens into an unequal, tapered vane.
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.015;y1:wings.height*1.16;x2:wings.width*0.951;y2:wings.height*0.49
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.12:0.09)}
                GradientStop {position:0.36;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.18:0.13)}
                GradientStop {position:0.64;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.1:0.065)}
                GradientStop {position:0.84;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.19:0.14)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.065:0.035)}
            }
            startX:wings.width*0.015;startY:wings.height*1.16
            PathCubic {control1X:wings.width*0.25;control1Y:wings.height*0.97;control2X:wings.width*0.43;control2Y:wings.height*0.67;x:wings.width*0.655;y:wings.height*0.685}
            PathCubic {control1X:wings.width*0.8;control1Y:wings.height*0.7;control2X:wings.width*0.92;control2Y:wings.height*0.6;x:wings.width*0.951;y:wings.height*0.49}
            PathCubic {control1X:wings.width*0.91;control1Y:wings.height*0.74;control2X:wings.width*0.81;control2Y:wings.height*0.79;x:wings.width*0.65;y:wings.height*0.756}
            PathCubic {control1X:wings.width*0.44;control1Y:wings.height*0.725;control2X:wings.width*0.27;control2Y:wings.height*1.06;x:wings.width*0.015;y:wings.height*1.16}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.015;y1:wings.height*1.16;x2:wings.width*0.951;y2:wings.height*0.49
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandBlue,0)}
                GradientStop {position:0.28;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.065:0.035)}
                GradientStop {position:0.6;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.25:0.2)}
                GradientStop {position:0.82;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.3:0.24)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.18:0.12)}
            }
            startX:wings.width*0.015;startY:wings.height*1.16
            PathCubic {control1X:wings.width*0.27;control1Y:wings.height*1.025;control2X:wings.width*0.44;control2Y:wings.height*0.71;x:wings.width*0.653;y:wings.height*0.728}
            PathCubic {control1X:wings.width*0.81;control1Y:wings.height*0.76;control2X:wings.width*0.915;control2Y:wings.height*0.69;x:wings.width*0.951;y:wings.height*0.49}
            PathCubic {control1X:wings.width*0.91;control1Y:wings.height*0.74;control2X:wings.width*0.81;control2Y:wings.height*0.79;x:wings.width*0.65;y:wings.height*0.756}
            PathCubic {control1X:wings.width*0.44;control1Y:wings.height*0.725;control2X:wings.width*0.27;control2Y:wings.height*1.06;x:wings.width*0.015;y:wings.height*1.16}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.015;y1:wings.height*1.16;x2:wings.width*0.951;y2:wings.height*0.49
                GradientStop {position:0;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.35;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.61;color:Theme.withAlpha("white",Theme.dark?0.1:0.42)}
                GradientStop {position:0.77;color:Theme.withAlpha("white",Theme.dark?0.25:0.76)}
                GradientStop {position:0.92;color:Theme.withAlpha("white",Theme.dark?0.07:0.22)}
                GradientStop {position:1;color:Theme.withAlpha("white",0)}
            }
            startX:wings.width*0.015;startY:wings.height*1.16
            PathCubic {control1X:wings.width*0.27;control1Y:wings.height*1.025;control2X:wings.width*0.44;control2Y:wings.height*0.71;x:wings.width*0.653;y:wings.height*0.728}
            PathCubic {control1X:wings.width*0.81;control1Y:wings.height*0.76;control2X:wings.width*0.915;control2Y:wings.height*0.69;x:wings.width*0.951;y:wings.height*0.49}
            PathCubic {control1X:wings.width*0.915;control1Y:wings.height*0.6926;control2X:wings.width*0.81;control2Y:wings.height*0.7626;x:wings.width*0.653;y:wings.height*0.7306}
            PathCubic {control1X:wings.width*0.44;control1Y:wings.height*0.7126;control2X:wings.width*0.27;control2Y:wings.height*1.025;x:wings.width*0.015;y:wings.height*1.16}
        }
        // Cyan: a thin root opens into an unequal, tapered vane.
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.095;y1:wings.height*1.15;x2:wings.width*0.931;y2:wings.height*0.647
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.12:0.09)}
                GradientStop {position:0.36;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.18:0.13)}
                GradientStop {position:0.64;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.1:0.065)}
                GradientStop {position:0.84;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.19:0.14)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.065:0.035)}
            }
            startX:wings.width*0.095;startY:wings.height*1.15
            PathCubic {control1X:wings.width*0.31;control1Y:wings.height*1.01;control2X:wings.width*0.5;control2Y:wings.height*0.77;x:wings.width*0.69;y:wings.height*0.787}
            PathCubic {control1X:wings.width*0.82;control1Y:wings.height*0.805;control2X:wings.width*0.91;control2Y:wings.height*0.76;x:wings.width*0.931;y:wings.height*0.647}
            PathCubic {control1X:wings.width*0.91;control1Y:wings.height*0.865;control2X:wings.width*0.82;control2Y:wings.height*0.89;x:wings.width*0.68;y:wings.height*0.838}
            PathCubic {control1X:wings.width*0.5;control1Y:wings.height*0.815;control2X:wings.width*0.33;control2Y:wings.height*1.09;x:wings.width*0.095;y:wings.height*1.15}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.095;y1:wings.height*1.15;x2:wings.width*0.931;y2:wings.height*0.647
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandCyan,0)}
                GradientStop {position:0.28;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.065:0.035)}
                GradientStop {position:0.6;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.25:0.2)}
                GradientStop {position:0.82;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.3:0.24)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandCyan,Theme.dark?0.18:0.12)}
            }
            startX:wings.width*0.095;startY:wings.height*1.15
            PathCubic {control1X:wings.width*0.32;control1Y:wings.height*1.06;control2X:wings.width*0.5;control2Y:wings.height*0.8;x:wings.width*0.684;y:wings.height*0.819}
            PathCubic {control1X:wings.width*0.82;control1Y:wings.height*0.86;control2X:wings.width*0.914;control2Y:wings.height*0.82;x:wings.width*0.931;y:wings.height*0.647}
            PathCubic {control1X:wings.width*0.91;control1Y:wings.height*0.865;control2X:wings.width*0.82;control2Y:wings.height*0.89;x:wings.width*0.68;y:wings.height*0.838}
            PathCubic {control1X:wings.width*0.5;control1Y:wings.height*0.815;control2X:wings.width*0.33;control2Y:wings.height*1.09;x:wings.width*0.095;y:wings.height*1.15}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.095;y1:wings.height*1.15;x2:wings.width*0.931;y2:wings.height*0.647
                GradientStop {position:0;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.35;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.61;color:Theme.withAlpha("white",Theme.dark?0.1:0.42)}
                GradientStop {position:0.77;color:Theme.withAlpha("white",Theme.dark?0.25:0.76)}
                GradientStop {position:0.92;color:Theme.withAlpha("white",Theme.dark?0.07:0.22)}
                GradientStop {position:1;color:Theme.withAlpha("white",0)}
            }
            startX:wings.width*0.095;startY:wings.height*1.15
            PathCubic {control1X:wings.width*0.32;control1Y:wings.height*1.06;control2X:wings.width*0.5;control2Y:wings.height*0.8;x:wings.width*0.684;y:wings.height*0.819}
            PathCubic {control1X:wings.width*0.82;control1Y:wings.height*0.86;control2X:wings.width*0.914;control2Y:wings.height*0.82;x:wings.width*0.931;y:wings.height*0.647}
            PathCubic {control1X:wings.width*0.914;control1Y:wings.height*0.8226;control2X:wings.width*0.82;control2Y:wings.height*0.8626;x:wings.width*0.684;y:wings.height*0.8216}
            PathCubic {control1X:wings.width*0.5;control1Y:wings.height*0.8026;control2X:wings.width*0.32;control2Y:wings.height*1.06;x:wings.width*0.095;y:wings.height*1.15}
        }
        // Green: a thin root opens into an unequal, tapered vane.
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.18;y1:wings.height*1.18;x2:wings.width*0.913;y2:wings.height*0.778
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.12:0.09)}
                GradientStop {position:0.36;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.18:0.13)}
                GradientStop {position:0.64;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.1:0.065)}
                GradientStop {position:0.84;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.19:0.14)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.065:0.035)}
            }
            startX:wings.width*0.18;startY:wings.height*1.18
            PathCubic {control1X:wings.width*0.4;control1Y:wings.height*1.05;control2X:wings.width*0.55;control2Y:wings.height*0.88;x:wings.width*0.725;y:wings.height*0.888}
            PathCubic {control1X:wings.width*0.83;control1Y:wings.height*0.91;control2X:wings.width*0.9;control2Y:wings.height*0.86;x:wings.width*0.913;y:wings.height*0.778}
            PathCubic {control1X:wings.width*0.89;control1Y:wings.height*0.97;control2X:wings.width*0.83;control2Y:wings.height*0.985;x:wings.width*0.72;y:wings.height*0.932}
            PathCubic {control1X:wings.width*0.55;control1Y:wings.height*0.905;control2X:wings.width*0.41;control2Y:wings.height*1.1;x:wings.width*0.18;y:wings.height*1.18}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.18;y1:wings.height*1.18;x2:wings.width*0.913;y2:wings.height*0.778
                GradientStop {position:0;color:Theme.withAlpha(Theme.brandGreen,0)}
                GradientStop {position:0.28;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.065:0.035)}
                GradientStop {position:0.6;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.25:0.2)}
                GradientStop {position:0.82;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.3:0.24)}
                GradientStop {position:1;color:Theme.withAlpha(Theme.brandGreen,Theme.dark?0.18:0.12)}
            }
            startX:wings.width*0.18;startY:wings.height*1.18
            PathCubic {control1X:wings.width*0.41;control1Y:wings.height*1.085;control2X:wings.width*0.55;control2Y:wings.height*0.9;x:wings.width*0.722;y:wings.height*0.915}
            PathCubic {control1X:wings.width*0.83;control1Y:wings.height*0.96;control2X:wings.width*0.893;control2Y:wings.height*0.93;x:wings.width*0.913;y:wings.height*0.778}
            PathCubic {control1X:wings.width*0.89;control1Y:wings.height*0.97;control2X:wings.width*0.83;control2Y:wings.height*0.985;x:wings.width*0.72;y:wings.height*0.932}
            PathCubic {control1X:wings.width*0.55;control1Y:wings.height*0.905;control2X:wings.width*0.41;control2Y:wings.height*1.1;x:wings.width*0.18;y:wings.height*1.18}
        }
        ShapePath {
            strokeWidth:0;strokeColor:"transparent"
            fillGradient:LinearGradient {
                x1:wings.width*0.18;y1:wings.height*1.18;x2:wings.width*0.913;y2:wings.height*0.778
                GradientStop {position:0;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.35;color:Theme.withAlpha("white",0)}
                GradientStop {position:0.61;color:Theme.withAlpha("white",Theme.dark?0.1:0.42)}
                GradientStop {position:0.77;color:Theme.withAlpha("white",Theme.dark?0.25:0.76)}
                GradientStop {position:0.92;color:Theme.withAlpha("white",Theme.dark?0.07:0.22)}
                GradientStop {position:1;color:Theme.withAlpha("white",0)}
            }
            startX:wings.width*0.18;startY:wings.height*1.18
            PathCubic {control1X:wings.width*0.41;control1Y:wings.height*1.085;control2X:wings.width*0.55;control2Y:wings.height*0.9;x:wings.width*0.722;y:wings.height*0.915}
            PathCubic {control1X:wings.width*0.83;control1Y:wings.height*0.96;control2X:wings.width*0.893;control2Y:wings.height*0.93;x:wings.width*0.913;y:wings.height*0.778}
            PathCubic {control1X:wings.width*0.893;control1Y:wings.height*0.9326;control2X:wings.width*0.83;control2Y:wings.height*0.9626;x:wings.width*0.722;y:wings.height*0.9176}
            PathCubic {control1X:wings.width*0.55;control1Y:wings.height*0.9026;control2X:wings.width*0.41;control2Y:wings.height*1.085;x:wings.width*0.18;y:wings.height*1.18}
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
