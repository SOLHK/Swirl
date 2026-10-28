pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id: canvas
    property var targetWindow: Window.window
    property real contentLeft: 0
    property real contentWidth: width
    property bool homeVisible: true
    readonly property Item decorationSource: decoration
    readonly property bool presenting: homeVisible && visible && Theme.transparency && !Theme.increaseContrast
        && (!targetWindow || (targetWindow.visible && targetWindow.visibility !== Window.Minimized))
    readonly property bool entering: entrance.running
    property bool initialized: false

    function present() {
        if (!initialized) return
        entrance.stop()
        visual.opacity = presenting ? Theme.wingOpacity : 0
        visual.scale = 1
        visual.y = 0
        if (presenting && !SwirlMotion.reduced) entrance.start()
    }
    onPresentingChanged: present()
    Component.onCompleted: { initialized = true; present() }
    Connections {
        target: SwirlMotion
        function onReducedChanged() { if (SwirlMotion.reduced) canvas.present() }
    }
    Connections {
        target: Theme
        function onDarkChanged() { canvas.present() }
    }

    SwirlGlassMaterial { anchors.fill: parent; targetWindow: canvas.targetWindow }
    Item {
        id: decoration
        objectName: "workspaceWingDecoration"
        anchors.fill: parent
        Accessible.ignored: true
        Item {
            id: footprint
            objectName: "apecWingFootprint"
            width: canvas.contentWidth * 0.85
            height: width * 0.76
            x: canvas.contentLeft + (canvas.contentWidth - width) / 2
            y: canvas.height - height - Theme.dp(12)
            Item {
                id: visual
                objectName: "apecWingVisual"
                width: footprint.width; height: footprint.height
                transformOrigin: Item.Bottom
                opacity: 0
                // Fixed paths retain their proportions at every window size and DPR.
                // Only this parent's transform and opacity participate in entry.
                Shape {
                    objectName: "apecFlatWingPaths"
                    width: 1200; height: 912
                    scale: footprint.width / 1200
                    transformOrigin: Item.TopLeft
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeWidth: 0; strokeColor: "transparent"
                        fillRule: ShapePath.WindingFill
                        fillGradient: LinearGradient {
                            x1: 200; y1: 600; x2: 620; y2: 900
                            GradientStop { position: 0; color: Theme.withAlpha(Theme.wingGold, 0.36) }
                            GradientStop { position: 0.28; color: Theme.withAlpha(Theme.wingOrange, 0.48) }
                            GradientStop { position: 0.60; color: Theme.withAlpha(Theme.wingCoral, 0.72) }
                            GradientStop { position: 1; color: Theme.wingRose }
                        }
                        PathSvg { path: "M 40 12 C 4 282 225 642 618 891 C 342 668 130 326 40 12 Z
M 124 132 C 111 324 283 594 583 856 C 380 650 255 389 124 132 Z
M 166 272 C 180 443 331 661 568 840 C 395 681 278 469 166 272 Z
M 207 410 C 235 541 380 713 580 851 C 433 726 330 566 207 410 Z
M 249 532 C 290 653 428 780 604 875 C 473 786 376 657 249 532 Z
M 107 431 C 126 535 238 641 383 723 C 270 633 189 522 107 431 Z
M 170 579 C 224 693 347 774 490 829 C 373 759 278 664 170 579 Z
M 275 719 C 326 788 423 839 523 867 C 444 818 364 758 275 719 Z
M 355 756 C 497 827 624 902 784 865 C 701 917 585 909 505 871 C 441 840 396 792 355 756 Z
M 545 804 C 629 840 719 853 844 823 C 751 877 647 867 579 831 Z" }
                    }
                    ShapePath {
                        strokeWidth: 0; strokeColor: "transparent"
                        fillRule: ShapePath.WindingFill
                        fillGradient: LinearGradient {
                            x1: 600; y1: 880; x2: 1162; y2: 3
                            GradientStop { position: 0; color: Theme.wingCyan }
                            GradientStop { position: 0.45; color: Theme.withAlpha(Theme.wingTeal, 0.62) }
                            GradientStop { position: 1; color: Theme.withAlpha(Theme.wingGreen, 0.36) }
                        }
                        PathSvg { path: "M 1162 3 C 1211 280 990 632 600 880 C 883 657 1086 330 1162 3 Z
M 1082 137 C 1080 332 918 606 643 856 C 826 659 977 400 1082 137 Z
M 1037 279 C 1009 454 860 660 650 834 C 808 667 934 476 1037 279 Z
M 990 424 C 952 559 826 715 642 851 C 776 714 889 574 990 424 Z
M 944 550 C 894 677 778 782 626 874 C 737 775 841 654 944 550 Z
M 1101 435 C 1076 551 959 652 819 728 C 927 636 1017 523 1101 435 Z
M 1030 588 C 971 704 851 783 716 831 C 824 759 930 671 1030 588 Z
M 921 727 C 866 796 772 847 681 869 C 753 821 838 761 921 727 Z
M 767 768 C 697 825 638 852 558 865 C 631 880 709 844 767 768 Z" }
                    }
                }
            }
        }
    }
    ParallelAnimation {
        id: entrance
        OpacityAnimator { target: visual; from: 0; to: Theme.wingOpacity; duration: SwirlMotion.ms(620); easing.type: Easing.OutCubic }
        ScaleAnimator { target: visual; from: 0.955; to: 1; duration: SwirlMotion.ms(760); easing.type: Easing.OutCubic }
        YAnimator { target: visual; from: Theme.dp(8); to: 0; duration: SwirlMotion.ms(760); easing.type: Easing.OutCubic }
    }
}
