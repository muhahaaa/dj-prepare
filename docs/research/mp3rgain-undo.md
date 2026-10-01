# mp3rgain undo (`-u`) behavior

Research for issue #16 (wayfinder). Facts only, no app-design decisions.

## Sources and method

- **Primary, read:** the mp3rgain repo <https://github.com/M-Igashi/mp3rgain>, branch `master`, commit `2d53a43fdec80e0e0c8cb11d6e3b90586501147d`, crate version `3.9.1` (`Cargo.toml`). Files: `README.md`, `docs/man/mp3rgain.1`, `docs/migrating-from-mp3gain.md`, `docs/design-decisions.md`, `docs/COMPARISON.md`, `src/lib.rs`, `src/gain.rs`, `src/apply.rs`, `src/ape.rs`, `src/id3v2.rs`, `src/mp4meta.rs`, `src/aac.rs`, `src/adts.rs`, `src/frame.rs`, `src/processors/{apply,undo,utils}.rs`, `src/commands/{undo,tags}.rs`.
- **Empirical, run on 2026-10-01:** the installed `mp3rgain 3.9.1` binary (same version as the source above) plus `mutagen 1.48.1`, on the repo's own test fixtures (`tests/fixtures/test_stereo.mp3`, `test_vbr.mp3`, `test_aac.m4a`). "Audio identical" below means the MP3 frame region (between the ID3v2 and trailing APEv2/ID3v1 tags), or the MP4 `mdat` box, compared byte-for-byte against the original. Marked **[tested]** where a claim rests on these runs; **[source]** where it rests on code/docs; **[inferred]** where it is a reading of the code that was not run.
- Not tested: ADTS `.aac` end to end (source only), aacgain interop, other tag editors than mutagen.

## 1. What undo does

`mp3rgain -u <file>` reverses the `global_gain` rewrite. There is no amount argument: it always reverts the whole cumulative recorded delta. [source: `src/commands/undo.rs`, `src/processors/undo.rs`, `src/lib.rs::undo_gain_auto`]

Mechanism [source: `src/gain.rs::undo_gain`, `src/aac.rs::undo_aac_gain`, `src/id3v2.rs::undo_gain_id3v2`, `src/adts.rs::undo_adts_gain`]:

1. Read the undo tag (a stored integer number of gain steps; one step is 1.505 dB).
2. Apply that delta to every `global_gain` field in the bitstream.
3. Delete the undo tag, the minmax tags, and the `REPLAYGAIN_*` values (the latter are stale residuals of the gained audio, issue #306 in the mp3rgain repo).
4. Write the result to a temp file and rename it over the original (atomic). A failure leaves the original untouched.

Undo does not consult `MP3GAIN_MINMAX` or anything else about the audio: the only input is the stored delta. [source: no read of minmax in those functions]

If the stored delta is `0,0`, undo returns "no changes to undo" (exit 0) and returns before removing any tags. [source: `src/gain.rs` early `return Ok(0)`]

## 2. Where the undo information is stored

| File type | Container | Key | Notes |
|---|---|---|---|
| MP3, default layout (`TagLayout::Split`) | **APEv2** tag at end of file (footer at EOF-32, or EOF-160 when an ID3v1 block trails) | `MP3GAIN_UNDO` (+ `MP3GAIN_MINMAX`) | `REPLAYGAIN_*` go to ID3v2 `TXXX` instead. |
| MP3, `-s a` | APEv2 | same | Everything in APEv2, "byte-for-byte mp3gain behaviour". |
| MP3, `-s i` | **ID3v2 `TXXX`** frames | `MP3GAIN_UNDO` (+ `MP3GAIN_MINMAX`) | Everything in ID3v2. `MP3GAIN_ALBUM_MINMAX` is APEv2 only. The man page calls `-s i` "not fully supported, falls back to APEv2", but the source and test below show it writes ID3v2 `TXXX`. |
| AAC in M4A/MP4 | **MP4 iTunes freeform atom** (`----` in `moov/udta/meta/ilst`, mean `com.apple.iTunes`) | `mp3rgain_undo` (+ `mp3rgain_minmax`) | Lowercase names. Reads are case-insensitive. Written alongside `replaygain_*` freeform atoms. |
| Raw ADTS `.aac` | ID3v2 `TXXX` at stream start | `MP3GAIN_UNDO` | MP3 sign convention. Since 3.7.0 (issue #330). `-s a` / `-s i` do not apply. |
| ALAC, DRM `.m4p` | none | | Recognized, reported as skipped, not adjustable. |

Sources: `docs/man/mp3rgain.1` (FILES, SUPPORTED FORMATS, `-s`), `docs/migrating-from-mp3gain.md` (tag placement table, "Undo information is stored in MP4 freeform metadata"), `docs/design-decisions.md`, `src/lib.rs` (`TagLayout` docs), `src/mp4meta.rs` (`UNDO_TAG`, `MINMAX_TAG`).

[tested] After `mp3rgain -r -d 3` on `a.m4a`, mutagen lists `----:com.apple.iTunes:mp3rgain_undo = b'+004,+004,N'` and `----:com.apple.iTunes:mp3rgain_minmax = b'108,179'` (data type `IMPLICIT`). On an MP3 (default layout), `mp3rgain -s c` shows `MP3GAIN_UNDO: +035,+035,N`, and the file ends in an `APETAGEX` footer. Under `-s i`, mutagen shows `TXXX:MP3GAIN_UNDO` and `TXXX:MP3GAIN_MINMAX`.

### Value format and sign convention

- Format `+LLL,+RRR,W|N`: signed left and right channel step counts, then a wrap flag (`W` = `-w` wrap mode, `N` = saturating). Example `+035,+035,N`. [source: `src/ape.rs::format_undo_value`]
- MP3 (APEv2 and ID3v2) and raw ADTS store the **undo delta** (negative of the applied gain; applied as-is on undo). M4A/MP4 stores the cumulative **applied** gain (negated on undo). Both are "load-bearing on-disk formats". [source: `src/ape.rs`, `docs/design-decisions.md`]
  - [tested] The m4a above, `-r -d 3` applied +4 steps, stored `+004`. The MP3 applied -35 steps, stored `+035`.
- Compatibility with mp3gain: MP3 undo tags are bidirectionally compatible with classic mp3gain, as of the fix for issue #210. mp3rgain ≤ 2.8.x wrote the opposite sign; undoing such a file with a current version "would double the gain". [source: `docs/migrating-from-mp3gain.md`]
- aacgain: `docs/COMPARISON.md` says "both mp3rgain and aacgain store undo data in iTunes freeform metadata tags". Whether the atom names match aacgain's was not verified.

### Accumulation

Every tagged apply updates the same tag cumulatively, so a single `-u` undoes all tagged applies since the original. MP3 subtracts the applied steps from the stored delta; AAC adds them to the stored applied gain. An apply of zero steps writes no undo tag. [source: `src/gain.rs::apply_gain_with_undo_impl_to_path`, `src/aac.rs::apply_aac_gain_with_undo_to_path_with_analysis`, `src/apply.rs`]

[tested] MP3 `-g -2` then `-g -3` then `-u`: audio identical to the original. M4A `-g 2` then `-g 3`: tag `+005`, `-u` restores `mdat` byte-identical.

The undo tag is not written at all with `-s s` (skip stored tags) or `--tags-only` (no audio change). [source: `src/processors/apply.rs` `write_undo = stored_tag_mode != Skip`; `docs/migrating-from-mp3gain.md`]

## 3. Survival of tag edits, rename, move

The undo information is a bare integer tag. It carries no path, hash or file identity. [source]

- **Rename/move:** [tested] an MP3 renamed to a name with a space, and moved to another directory, undid correctly (audio identical). Nothing in the source ties the tag to a path.
- **mutagen, MP3, default layout:** [tested] `mutagen.mp3.MP3` adding `TIT2` and a `TXXX`, saved with `v2_version=3, v1=2` (which appends an ID3v1 block after the APEv2 tag): `MP3GAIN_UNDO` still readable, undo succeeded, audio identical, user's ID3 frames kept, APEv2 gone afterwards. mp3rgain explicitly finds the APE footer at EOF-160 when an ID3v1 block trails. [source: `src/ape.rs::find_ape_footer`]
- **mutagen, MP3, tag wipe:** [tested] `MP3.delete()` followed by `save()` removes ID3v2 and ID3v1 but left the APEv2 tag; undo still worked. In the same wipe, with `-s i` (undo in ID3v2 `TXXX`), the undo information was destroyed and `mp3rgain -u` failed with `No APE tag found - cannot undo` (exit 1).
- **mutagen, `-s i` layout:** [tested] adding a frame and saving preserved the `TXXX:MP3GAIN_*` frames; undo then worked.
- **mutagen, M4A:** [tested] adding `©nam` (long) and a custom freeform atom, then `MP4.save()`: the `mp3rgain_undo` / `mp3rgain_minmax` atoms survived (order changed), undo succeeded, `mdat` byte-identical to the original (file as a whole differs only through the mutagen-edited `moov`). Deleting only the `replaygain_*` keys left undo working. `MP4.delete()` (clearing all tags) removed the undo atoms, and `mp3rgain -u` failed with `No MP3GAIN_UNDO tag found - cannot undo` (exit 1).
- In short: undo survives any edit that leaves the specific container key in place and is lost when the tool removes that key or wipes that container.

## 4. Failure behavior and reliability

**No undo tag present (never normalized by mp3rgain/mp3gain, or normalized by another tool):** [tested] `-u` on an untouched MP3 prints `No APE tag found - cannot undo`; on an untouched M4A `No MP3GAIN_UNDO tag found - cannot undo`; on an MP3 whose only gain info is a `REPLAYGAIN_TRACK_GAIN` TXXX written by mutagen, the same `No APE tag found`. All exit 1, file audio untouched; with `-o json` the file gets `"status": "error"`. [source: `src/error.rs` `NoApeTag`, `NoUndoTag`, `NoId3v2UndoTag`; `src/processors/utils.rs::report_file_error`]

**`-u -n` (dry run) does not check for an undo tag:** [tested] it reports "would undo" and exits 0 on a file that has none. [source: `src/processors/undo.rs` returns before calling undo]

**Second undo:** [tested] once undone, the tags are gone, so a repeat `-u` errors (exit 1) and changes nothing.

**Clipping capping (`-k`):** the cap is resolved before the apply, and the tag records the steps actually applied, not the requested ones. [source: `src/apply.rs::check_clipping` returns `actual_steps`; the undo tag is written from `actual_steps`] [tested] M4A, `-r -k -d 20` with the message "gain reduced from 15 to 9 steps to prevent clipping": tag `+009`, undo restored `mdat` byte-identical. Without `-k` the tag was `+015` and undo also restored identically. `-k` can yield a negative step count when the source already clips; the code treats that as normal attenuation recorded in the tag. [source: comment in `check_clipping`, issue #173]

**Track altered by another tool after mp3rgain (or by a change not recorded in the tag):** the stored delta is applied blindly, with no audio verification. [source: only the delta is read] [tested, simulated with mp3rgain itself] M4A `-g 3` (tagged), then `-s s -g 4` (change made without updating the tag): tag still `+003`; `-u` reported success and left the audio 4 steps off the original. A re-encode or another gain tool that does not update the same tag would behave the same way [inferred]. Conversely, a track normalized only by tags-only tools (rsgain/loudgain style) has nothing to undo, as above.

**Lossy cases (the "lossless and reversible" claim has limits):**

- MP3 saturating mode clamps `global_gain` at 0..255. mp3rgain prints a warning when this happens ("N gain value(s) clamped at 255/0 ... saturated gain is not losslessly reversible"), and its source says the frames "can no longer be byte-restored by undo". [source: `src/processors/apply.rs::emit_saturation_warning`] [tested] `-g -255` on `test_vbr.mp3` clamped 160 values at 0; `-u` reported success (40 frames restored) but the audio differed from the original. `-g 2` on `test_stereo.mp3` (gain field already 255) warned about 156 clamped values. The source comment says ReplayGain (`-r`) adjustments "never get near this range", so the warning mainly fires for extreme manual `-g`/`-l`.
- AAC apply clamps at 0..255 as well and skips locations whose gain is 0, in both apply and undo; the saturation tally is MP3 only, so no warning is shown for AAC. [source: `src/aac.rs::apply_aac_gain_to_data`, `src/frame.rs::adjust_gain_value`, comment in `src/apply.rs`: "AAC clamps in its own path and isn't tallied here"] Non-reversibility on a clamped AAC value is [inferred] from this.
- AAC undo doc comment: "functionally equivalent to the original but may not be bit-for-bit identical due to MP4 container restructuring." [source: `src/aac.rs`] [tested] In the m4a round trips above, the whole file came back byte-identical when nothing else had edited it (the `mdat` was identical in every test).
- MP3 round trips: the audio frames were byte-identical in every non-saturating test; the ID3v2 tag is rewritten (its size changed) and the APEv2 tag removed. The mp3gain docs note mp3gain leaves empty APEv2 tags after undo, and mp3rgain removes them. [source: `docs/migrating-from-mp3gain.md`]
- Wrap mode (`-w`, `W` flag) and per-channel (`-l`, unequal L/R values) have dedicated undo paths: equal L/R uses the whole-file path honoring `W`; unequal values are undone per channel, always saturating. [source: `src/gain.rs::apply_undo_to_data`]

**Cross-container fallback (MP3):** undo reads the undo tag from the container the layout selects and falls back to the other one, so a file tagged under a different `-s` layout still undoes. [source: `src/lib.rs::undo_gain_auto`]

**`-s d` and `-u`:** deleting stored tags alone destroys the undo information. Combined `-u -s d` undoes first, then deletes; if the undo fails for any reason other than "no undo tag", the delete is skipped so the info survives. [source: `docs/man/mp3rgain.1`, `src/commands/tags.rs`, issue #305]

**Timestamps:** undo restores the original mtime only when `-p` is given. [source: `src/processors/utils.rs::save_original_mtime`]

**Exit status:** any per-file failure (including "no undo tag") makes the run exit 1. Unsupported formats (ALAC, M4P) are reported as skipped and do not. [source: `docs/man/mp3rgain.1` EXIT STATUS, `src/processors/utils.rs`]

## 5. One-line answers to the ticket

- **Where stored:** MP3: APEv2 `MP3GAIN_UNDO` (default; `-s i` puts it in ID3v2 TXXX). M4A/MP4: iTunes freeform atom `mp3rgain_undo` (lowercase). Raw ADTS `.aac`: ID3v2 TXXX `MP3GAIN_UNDO`. Value is `+L,+R,W|N` in 1.505 dB gain steps; MP3 and ADTS store the undo delta, M4A stores the applied gain.
- **Survives mutagen?** Yes, unless the edit removes that key or wipes that container: MP3 default (APEv2) survives all mutagen ID3 operations tested including `MP3.delete()`; `-s i` (ID3v2) and M4A (`MP4.delete()`) do not survive a tag wipe. **Rename/move:** survives; nothing path-bound.
- **Normalized by another tool:** nothing to undo and `-u` errors (exit 1), unless that tool wrote an mp3gain-compatible tag. If the audio changed after mp3rgain wrote its tag, undo applies the stale delta without detecting it.
- **With `-k`:** the capped step count is what is recorded and undone; round trip verified.
- **Reliability:** exact for ordinary `-r` use in all tests; not exact when `global_gain` saturated (MP3 warns at apply time, AAC does not), or when the tag is stale or missing. No verification step exists in undo itself.
