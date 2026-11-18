# Qt source and notices

Qt copyright and license notices are retained in each original source archive.
The `notices/` directory in the accompanying source bundle and the installed
`licenses/qt/` directory also contain copies of the module license texts and
identified vendored-source notices. The complete original source trees remain
available in the bundle, including notices embedded in source files.

The runtime modules are QtBase, QtDeclarative, QtSvg and QtTranslations.
QtTools and QtShaderTools are included as build-tool source dependencies.
The module files and third-party components within those modules can have
different license identifiers; the retained files and attribution metadata
must be consulted for the particular component. Copying this notice does not
replace those terms.

QtDeclarative includes the allocator-sweep modification from official commit
`8c92fe01338c76885f412a68fd39238147e21a81` and the JIT SetLookup accumulator repair
from `4c1054b0f997f2977a54d42523856805b309db9a`. Both patches, the exact modified
source, file manifest and original build recipe are included. The standalone
JIT regression fixture retains its separate GPL-3.0-only notice and license;
it is build evidence and is not linked into Swirl or the Qt runtime. QtNetwork also
contains the two recorded HTTP parser bounds backports. Its complete modified
QtBase source, both patches, source manifest and build evidence are supplied
separately from the unmodified QtBase archive. No additional Qt
commercial license or special permission is asserted here.

Primary references:

- [Qt 6 licensing](https://doc.qt.io/qt-6/licensing.html)
- [Qt open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations)
- [GNU Lesser General Public License version 3](https://www.gnu.org/licenses/lgpl-3.0.html)
- [GNU General Public License version 3](https://www.gnu.org/licenses/gpl-3.0.html)

The accompanying source package and file-identity checks are engineering
delivery evidence. They are not an assertion that every distribution or
licensing question for the complete Swirl product has been resolved.
