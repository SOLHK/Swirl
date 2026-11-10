# Follow-up attempt 1: exact axis readback rejected, no metric-model verdict

Commit: `03c34a68a6ad52035097d123a9e5ecd2948e310f`.
Run: <https://github.com/SOLHK/Swirl/actions/runs/39401640475>.
Terminal result: failure. Python succeeded; apple-followup failed; the original
ablation job was skipped by its dependency. Local source tests were 542 with
7 optional skips; the six audit tests passed.

The first font's forward process actually completed all 51 requests from the
17 new height coordinates and three widths. Its 52nd request, appended as the
exact-normalization-grid control, was rejected before glyph measurement:

| Field | Raw value |
| --- | --- |
| Request ID | `followup-x0-y0.828125` |
| HGHT | `53/64 = 0.828125` |
| WDTH | `0` |
| Point size / UPEM | `1000 / 1000` |
| Error | `native_axis_readback_not_exact:HGHT` |
| Completed raw requests | `51` |
| Raw observations including failed request | `52` |
| Admitted forward/reverse pairs | `0` |

The aggregate summary contains zero admitted observations because a complete
font forward/reverse pair is required before admission. It does not mean the
native process measured no glyphs. The first probe did not preserve actual
HGHT in its failure message, so no particular returned coordinate can yet be
asserted. The 51 complete forward records lack reverse replay and do not become
accepted metric evidence by being archived. No hypothesis was refitted from
these partial results.

The exact decoded [native job log](followup-rejected/native-job-118557731103.log)
and derived [summary](followup-rejected/summary.json) are retained. The complete
[raw artifact ZIP](archives/followup-rejected-12254909481.zip) includes the
failed request and its 51 predecessors, plus the original frozen manifest.

## Next diagnostic, without weakening identity

A separate follow-up Swift probe will retain requested and reported axes and
their binary64 bits before throwing the same exact-readback rejection. The
first-stage probe remains unchanged. The original ablation can execute
independently of this synthetic axis issue because stage 1 already completed.

A separately labeled B1 user-axis-unit control will scale only HGHT's fvar
range from [-1,0,1] to [-16384,0,16384], so this same normalized coordinate
becomes the exact integer user coordinate 13568. It must preserve every other
table payload (apart from the necessary head checksum), all normalized requests
and all frozen metric hypotheses. Native user coordinates and normalized
coordinates remain explicit separate fields. Exact readback is still required.

Before interpreting that control, compare common complete raw observations
across the two axis units in direct advance, translation, full witness path and
actual layout; font identity necessarily binds each variant's own fvar bytes.
Also infer normalized coordinates from the witness bounds. Integer axis
readback alone is not evidence that the intended outline instance was selected.

## Full archive preservation

The first-stage raw artifact has now also been downloaded and independently
verified, extending the earlier log-only provenance:

| Artifact | Local bytes | Verified SHA-256 |
| --- | ---: | --- |
| [stage1-native-12254476529.zip](archives/stage1-native-12254476529.zip) | 1,294,040 | `5914f830d48c145db4e164305efc83604d60b7213401b2c09b5670d1063c6c54` |
| [followup-rejected-12254909481.zip](archives/followup-rejected-12254909481.zip) | 204,337 | `c7a106996707a3f25be732aa622c8e27f8abc6ddfb6c88b115be54c9b4d5d47a` |

Both archives match GitHub's reported SHA-256 and pass all ZIP CRC checks.
They contain respectively 163 and 10 entries, with no TTF/TTC/OTF files. The
first preserves all 1,248 raw records, calculation bases and original synthetic
path/layout data. Their bytes are now in this branch, independent of Actions
artifact expiry. No Apple font or private original outline is included.
