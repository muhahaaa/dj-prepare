# DJ Prepare

A personal tool for taking downloaded songs through loudness normalization, tag review/validation, renaming, and genre-based filing before they enter the DJ library.

## Language

**Track**:
A single audio file being prepared, in one of the six Supported Formats, moving through the Pipeline Stages.
_Avoid_: Song, file (when referring to the domain object rather than the OS-level file)

**Pipeline Stage**:
One of the four ordered steps a Track passes through: Normalize, Tag, Rename, File.
_Avoid_: Step, phase

**Supported Format**:
One of the six file types this effort handles: mp3, aac, m4a, flac, wav, ogg. "aac" means MP4-container-wrapped AAC audio specifically (the same handling path as m4a); bare elementary-stream AAC (raw ADTS/ADIF, no container) is out of scope.

**Normalizable Format**:
The subset of Supported Formats — mp3, aac, m4a — that mp3rgain can adjust gain for. A Track in a non-Normalizable Format skips the Normalize stage entirely.

**Tag Field**:
One of the seven metadata fields the Tag stage manages for a Track: Title, Artist, Album, Genre, Year, Comment, Picture. Album is free text per Track, same shape as Title/Artist (not a closed list like Genre/Comment).
_Avoid_: Metadata (when a specific field is meant)

**Genre List**:
The user's fixed, closed set of allowed Genre values, managed via the app's UI. Each Track has exactly one Genre, selected from this list.
_Avoid_: Genre tags, genres (when referring to the registry itself rather than a Track's value)

**Comment List**:
The user's fixed, closed set of allowed Comment values, managed the same way as the Genre List. Each Track has exactly one Comment, selected from this list.

**Validation Rule**:
A user-configured check against a Track's Tag Fields, instantiated from one of the three built-in Rule Types, used to flag Tracks with incomplete or invalid tags. Carries a Block Severity, configured independently.
_Avoid_: Constraint, requirement

**Rule Type**:
One of the three built-in, finite kinds of Validation Rule a rule can be instantiated from: **Required** (the target field must be non-empty — used for Picture, Title, Artist), **OneOf** (the target field's value must be on a list — Genre on the Genre List, Comment on the Comment List; inherently fails on an empty value, so no separate Required is needed alongside it), and **YearRange** (Year must fall within a configured min/max).

**Not Applicable**:
A Validation Rule outcome distinct from pass/fail: the rule doesn't apply to this Track at all and is excluded from its Readiness. Currently only arises for the Picture rule on ogg Tracks, since embedded pictures aren't supported for that format.

**Readiness**:
Whether a Track currently passes every active Validation Rule that applies to it (Not Applicable rules are excluded, not counted as passing or failing).
_Avoid_: Status, state (too generic — Readiness is specifically about Validation Rule outcomes)

**Genre Folder Mapping**:
The config associating a Genre (an exact value, or a trailing-`*` wildcard pattern) with a destination folder, consulted by the File stage to place a finished Track. Exact entries take priority over wildcard entries.

**Inbox**:
The single fixed folder the tool scans for Tracks. A Track leaves the Inbox once it has been Filed; Inbox contents are exactly the set of not-yet-finished Tracks.

**Block Severity**:
Whether a Validation Rule is Hard (failing it blocks the Rename and File stages for that Track) or Soft (failing it is shown as a warning only). Configured independently per rule.
