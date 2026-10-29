# Reviewed C1 packing reuse for A3/B1/C1 takeover

Exact source branch: `work/vf-rebuild-c1`. Source HEAD:
`c0fe6c47f1a4a0854fcbbde7c9f08b791b44123e` (documentation successor to
validated implementation `75628e3eef45043e88689fd6ee191178ba179622`).

This is a selected file reuse, not a merge of C1 history. The original branch
and every original commit remain intact. Native acceptance and the synthetic
reconstruction engine are not copied or enabled. Original Apple reconstruction
remains unaccepted. The shared converter may call this existing packer on its
internal candidate before its independent native finalization/publication.

| Reused file | Source Git blob | Source SHA-256 | Transfer |
| --- | --- | --- | --- |
| `tools/swirl_vf/tools/ttc_staging_pack.py` | `c9f32ced37c873f7297884fb4c2debcd2a0fa46a` | `9f43c6fdfa71d6d9ba29a4d67f5e8bd3a7403555e4e9f9d15fe2570e01575d0f` | exact bytes |
| `tools/swirl_vf/tools/ttc_staging_binary.py` | `5182453aa4eb18a903d3fafb6161f2dfaf1f7b83` | `a706a03abac2f29b79000b6aea7875dfa9f04f1a05c8236997f1a074920555e2` | exact bytes |
| `tools/swirl_vf/tools/ttc_staging_contract.py` | `d21d92b2240647b437f5340b9f4a52a3a59fb3d4` | `d4bae00a2a307aaaeb4efc939ea2c679959f69567970519613e834bf9b95db89` | exact bytes |
| `tools/swirl_vf/platform/rebuild_c1_fixture.py` | `b969f19a0ba56f0749df80b6c18b3b1d1da5440d` | `24bc8db522cf63fa1189c547f8b935c9dd7ae21c886f4adcbf11d756b2e781b7` | exact bytes |
| `tools/swirl_vf/tests/test_ttc_staging_pack.py` | `d4ce946fff27418b56ed9055f921568279fbdc2d` | `6feb396e3527a74ed42816966f2d6bceb1b7518c5656c5a64a68fd5f9ce0c0dc` | packaging tests reused; one C1-specific validation callback uses existing production table verifier |
| `tools/swirl_vf/tests/test_ttc_staging_binary.py` | `e6b1762d765b4e24ffe1f9e5e6f5bda5f20f662a` | `0223bb60e963e6ead5e5c4bc27b40dbdf10cfe32029d05056447df9c2b5e2e02` | subset: checkpoint-engine recipe test remains on C1; no engine imported |

Only the binary test of the synthetic engine's recipe binding is excluded
from this selected packaging subset, because that synthetic engine is not
imported. All binary corruption tests, including all six padding corruptions,
remain. This is not deletion or weakening of an existing local test.

Primary references re-read before reuse:
[FontTools TTCollection 4.61.1](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/ttCollection.py)
and [OpenType file/collection specification](https://learn.microsoft.com/en-us/typography/opentype/spec/otff).
The packer is the project's previously independently implemented C1 work; no
upstream source is copied. The fixture creates only authored geometric test
fonts and contains no original Apple font or derived outlines.

The packer callback regression is adapted to call existing production
`rebuild.verify_collection_tables` rather than import C1's separate synthetic
output-profile validator. The assertion still runs before publication and
checks exact bytes in all physical faces. No claim of glyph/native semantics
is added. The first selected-subset run exposed this missing optional
validator import (59 passed, 1 import error); this adaptation removes the
unneeded engine/validator dependency while preserving callback coverage.
