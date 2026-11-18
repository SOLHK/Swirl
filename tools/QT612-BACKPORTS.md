# Qt 6.12.0 local Windows backports

Swirl 0.2.41 retains Qt 6.12.0. The local MinGW kit contains these upstream fixes:

- CVE-2026-116337 / QTBUG-150779: bound incomplete HTTP status lines and response headers. Official advisory: https://www.qt.io/blog/security-issue-cve-2026-116337 . Apply the official 6.12 `0002` patch, then `0001`.
- QTBUG-149512: preserve allocation bits created during QV4 sweeping. Upstream commit `8c92fe01338c76885f412a68fd39238147e21a81` remains applied.

`qt612-backports.lock.json` records exact source commits, patch hashes, compiler and accepted local binaries. This is a separate local build; it does not reuse or relabel the historical MSVC CI artifact. The stock Qt installation remains unchanged. Upgrade to 6.12.1 only after its official release and normal validation.

## Reproduction

Use the official Qt 6.12.0 Windows x64 MinGW kit and its GCC 15.1.0, CMake 4.4.5 and Ninja 1.13.2. QtBase source is commit `025bdad181de241e81bf853c8a2d7bf3d19261a9`; QtDeclarative is `4332fbbb4c340463dc8cee36dda0c85d932122d8`. The corresponding-source archive contains their complete tracked source including the applied patches, original licenses, this recipe and the original patches. The unused test262 gitlink is omitted; it does not participate in these module builds. Unmodified QtSvg, QtTranslations, QtShaderTools and QtTools source archives retain their official 6.12.0 hashes.

In a fresh out-of-source directory, with the MinGW, CMake, Ninja and stock Qt `bin` directories on PATH:

```powershell
cmake -S $QtBaseSource -B $NetworkBuild -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ `
  -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TOOLS_BY_DEFAULT=OFF `
  -DFEATURE_openssl=ON -DFEATURE_openssl_runtime=ON -DFEATURE_openssl_linked=OFF `
  -DFEATURE_dtls=ON -DFEATURE_ocsp=ON `
  -DOPENSSL_INCLUDE_DIR=$OpenSslCompleteHeaders `
  -DOPENSSL_SSL_LIBRARY=$OpenSslBuild/libssl.dll.a `
  -DOPENSSL_CRYPTO_LIBRARY=$OpenSslBuild/libcrypto.dll.a
cmake --build $NetworkBuild --target Network --parallel 4
cmake -S $QtDeclarativeSource -B $QmlBuild -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$StockQtKit `
  -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TOOLS_BY_DEFAULT=OFF
cmake --build $QmlBuild --target Qml BuiltinsOutput --parallel 4
```

Use OpenSSL 3.5.9 development headers (both original and generated headers) and its MinGW import libraries. Do not omit generated configuration headers: that silently removes DTLS/OCSP in a partially configured build. The patched module public feature macros and exported symbol names must match the stock modules. All 2,340 QtNetwork and 4,062 QtQml export names matched in the delivered build.

Copy the full stock kit to a separate directory. Replace only `bin/Qt6Network.dll`, `bin/Qt6Qml.dll`, their `lib/libQt6*.a` import libraries, `qml/builtins.qmltypes`, and `include/QtNetwork/6.12.0/QtNetwork/private/qhttpnetworkreply_p.h` with corresponding build/source outputs. Retain stock Core, Gui, Quick, tools, plugins and compiler runtime. Configure Swirl with this derived kit as `CMAKE_PREFIX_PATH` and build Release. A new build may have different binary hashes; review its provenance and regressions before updating the lock.

## Verification and distribution

`tools/repros/qt612-http-bounds` calls the real QtNetwork DLL through QNetworkAccessManager with a valid response and two bounded malformed responses. The peer deliberately remains open. The stock DLL fails both malformed cases; the patched DLL terminates them naturally. `tools/repros/qt612-popup-gc/sweep.cpp` reports eight live-object/free-list overlaps on stock and zero on the patched Qml DLL. These are DLL-level regressions, not a claim that the upstream private test suite was linked against the distribution DLL.

Stage with `-QtBackportSourceBundle` pointing to the exact archive in the lock. The staging script verifies the configured kit, deployed Qt files and source archive before generating the payload manifest. Original Qt LGPL/GPL notices and a patch receipt are installed in `licenses/qt-backports` and `qt-backports.json`. Modified Qt source is delivered beside the installer. Swirl remains dynamically linked, so users can replace these Qt DLLs with ABI-compatible builds under the applicable Qt license.
