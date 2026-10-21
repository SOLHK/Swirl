# P8 private local DirectWrite gate

This wrapper reuses `platform/run_directwrite_probe.ps1` and its existing C++
probe. It adds no font conversion or shaping engine. Its input, native logs,
nominal cmap records and raster PNGs are private; do not upload this output
directory or an Apple-derived font to GitHub/CI artifacts.

The local cloud host is macOS 26.3. No installed Windows VM application or
QEMU/Wine/PowerShell command was found in the bounded readiness check.
Original-derived Windows native testing and Windows 11 remain **NOT_RUN**.
Authored protocol tests are not Windows runtime evidence.

The separate `swirl-vf-p8-windows-local.yml` workflow creates a fresh exact-SHA
checkout, virtual environment, authored one-face/seven-GID TTC and native output
under `D:\Codex`. It explicitly maps the existing raster sheet's mixed CJK/Latin
code points to its own rectangles/curve, compiles the existing C++ probe and
requires all 62 positions, 186 strict axis comparisons and 10 raster captures.
It uploads only `public/summary.json`, never fonts, native logs or PNGs. Its
Windows Server/authored scope cannot grant original-derived or Windows 11
acceptance. The workflow's actual run result must be checked separately.

On an authorized Windows machine with the checkout and candidate already under
`D:\Codex`, use Python with fontTools 4.61.1, PowerShell 7, CMake and the existing
Visual Studio C++/Windows SDK prerequisites. The wrapper keeps generated output
and compiler temporary files under `D:\Codex`; it does not transfer or install
fonts. Choose a fresh output directory.

```powershell
Set-Location D:\Codex\Swirl
python tools\swirl_vf\platform\p8_windows_local.py `
  --font D:\Codex\Swirl-VF-private\candidate.ttc `
  --expected-sha256 <exact-candidate-SHA256> `
  --font-scope original_derived_candidate `
  --expected-faces 1 --expected-glyphs 47102 `
  --output D:\Codex\Swirl-VF-private\P8\candidate-first-run
```

The expected SHA is mandatory. The static gate checks the exact container,
physical face/glyph counts, nominal `WDTH/wght/HGHT` axes and cmap. Native
validation checks the locked input SHA, physical face indices, all 17 nominal
Latin/CJK mappings against fontTools, complete 62-position three-axis matrix,
finite outline/metric observations, actual axis movement, terminal counts and
all 10 five-DPI/theme raster files. Strict input/readback equality is explicitly
binary32 because DirectWrite's axis API takes `FLOAT`. This does not certify
binary64 source-axis mapping or post-avar coordinate equality.

The existing raster path draws nominal glyph runs at 12/16/24/36 DIP and
96/120/144/168/192 DPI. It is not shaping, pixel-equivalence or clarity approval.
The wrapper observes Windows product type and requires both a Windows 11 client
caption and matching client/build observations before labelling that native
scope. Windows Server results remain separate. Every successful report retains
`font_only_equivalence_accepted=false`, original HVF parity **NOT_RUN**, Qt/Swirl
**NOT_RUN**, and installation **NOT_RUN**.

Portable authored regressions:

```sh
python -m unittest discover -s tools/swirl_vf/tests -p test_p8_windows_local.py -v
```

Primary references reviewed before implementation: Microsoft's
[custom font sets sample](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/DirectWriteCustomFontSets)
([sample documentation](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/directwrite-custom-font/)),
[CreateFontFace](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface),
[GetFontAxisValues](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontface5-getfontaxisvalues),
[GetGlyphIndices](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getglyphindices),
[GetGlyphRunOutline](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getglyphrunoutline),
and [OSVERSIONINFOEX product types](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-osversioninfoexw).
Existing project code is reused; no upstream implementation was copied.
