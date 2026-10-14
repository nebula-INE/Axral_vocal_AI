# UTAU prefix.map parsing

The \`axral_vocal_ai.prefix_map\` module provides a deterministic parser and
mapper for the pitch-boundary convention used by VO-SE_vocal.

## Example

    from axral_vocal_ai.prefix_map import map_alias, parse_prefix_map

    parsed = parse_prefix_map("C1\t\t_C4\nF4\t\t_F4")
    if parsed.issues:
        print(parsed.issues)  # surface diagnostics for review
    else:
        print(map_alias("あ", 65, parsed.entries))  # あ_F4

## Contract and limitations

- Rows are note boundary + prefix + suffix; legacy two-column rows are treated
  as note boundary + suffix.
- A mapping applies only at or above its declared MIDI boundary. Notes below
  the first boundary remain unmapped.
- Prefix/suffix strings are applied to the complete alias, including VCV aliases.
- Malformed rows are returned as diagnostics, not silently discarded.
- This module does not read files, inspect voicebank directories, resolve
  aliases against oto.ini, or render audio. Filesystem and alias-resolution
  integration remain separate work.
