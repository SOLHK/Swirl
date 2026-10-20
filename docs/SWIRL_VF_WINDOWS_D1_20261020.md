# D1 Windows axis precision checkpoint — 2026-10-20

Branch: `work/vf-windows-d1`. Verified integration parent:
`e505326486202ad4c8e98bb8b66a17b4547c559f`.

## Stage 1: executable experiment, native outcome pending

The dedicated workflow `swirl-vf-windows-d1.yml` runs actual Windows Server
2022/2025 with Qt 6.10.3 and MSVC 2022. Its source and result identities are
recorded separately. Windows 11 desktop, original PingFang, original TTC
installation, regional typography, real Swirl UI and physical display clarity
remain **NOT_RUN**. No qualified original `Swirl-VF.ttc` exists in this task.

No changes are made to the Apple algorithm, Rust Core, QML, FontManager or
FontAxisPolicy. The experiment uses independently authored abstract geometry
and its own file names, workflow and tests.

### Predeclared input experiment

The distinct decimal requests `499.006199` and `499.006201` both become
binary32 `499.006195068359375`, bit pattern `0x43f980cb`; local binary32 ULP is
`0.000030517578125`. Their nearest 16.16 encoding is also the same, `32702870`.
These are numerical calculations, not native rendering evidence.

The DirectWrite axis field is `FLOAT`. Qt's public setter also accepts `float`.
The file representation of `fvar` bounds as 16.16 does not by itself prove
that the Windows runtime first rounds every user request to 16.16.

Two original synthetic fonts and 28 frozen requests separately test the
input collision, nearby binary32 values, broad axis controls and narrow avar
intervals. Below 128 the fixture contains distinct binary32 requests that
round to the same declared 16.16 value. The amplified fixture distinguishes
predeclared continuous, user16, normalized16 and normalized14 hypotheses;
the predictions are not substituted for measured Windows values.

### Independent native observables

DirectWrite records requested decimals, binary32 values/bits, native API
readback, complete outline operations with unrounded coordinate bits,
integer design metrics, natural fractional glyph placement and eight actual
alpha rasters per position. It compares complete payloads in reversed order,
not only API readback or hashes. Forward/reverse executable processes and
file/system-collection modes are separate. Actual installed resources must
match the source table bytes.

Qt records QFont requested-axis storage explicitly as request storage. It
independently measures QRawFont paths/advances, QTextLayout runs, font
metrics and QPainter pixels, at multiple point sizes, logical DPIs and DPRs.
Private-font remove/reload, missing-load handling, reversed requests and
actual-font table identity are checked. Both `windows:fontengine=native`
and `windows:fontengine=freetype` are requested. Qt 6.10.3 does not recognize
`fontengine=directwrite`; that spelling would not establish a backend.

### Validation completed before native execution

12/12 original-fixture Python tests passed locally with fontTools 4.61.1.
These include serialized table consistency, HVAR/phantom consistency,
deterministic font bytes and 18 saved static-instance checks. The Linux
DirectWrite placeholder was compiled and correctly returned 77/NOT_RUN;
it is not a Windows result. Native compile/run results must be appended
with the exact pushed source SHA and actual Actions run/job links.

## Primary references reviewed before implementation

- [Microsoft axis value type](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/ns-dwrite_3-dwrite_font_axis_value)
- [Microsoft arbitrary-axis face creation](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface)
- [Microsoft glyph placement](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextanalyzer-getglyphplacements)
- [Microsoft DWriteCore design and font selection examples](https://github.com/microsoft/WindowsAppSDK/blob/main/specs/dwritecore/DWriteCore.md)
- [Qt 6.10.3 DirectWrite font database](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/windows/qwindowsdirectwritefontdatabase.cpp)
- [Qt 6.10.3 QFont implementation](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfont.cpp)
- [Qt 6.10.3 Windows platform parameter parsing](https://github.com/qt/qtbase/blob/v6.10.3/src/plugins/platforms/windows/qwindowsintegration.cpp)

These references informed API use; the D1 experiment code and font geometry
are original. No proprietary font payload is committed or uploaded.
