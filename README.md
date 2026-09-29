# genrefold

A small python script to fold messy music genre tags into a curated whitelist by walking a genre DAG scraped from RateYourMusic.

## Usage

```
python genre.py "tag1, tag2; tag3"
```

Input is split on commas and semicolons. Output is one `;`-separated line.

```
$ python genre.py "chillwave"
Synthwave

$ python genre.py "vaporwave"
Electronic

$ python genre.py "ghazal"
Ghazal; Sufi
```

`chillwave` is remapped to `Synthwave`, which is allowed, so the walk stops there. `vaporwave` is remapped to `Electronic`. `ghazal` is remapped to two seeds, and both are kept.

Unresolved tags go to stderr, so stdout stays pipeable:

```
$ python genre.py "chillwave, zorblax"
Synthwave
unresolved: zorblax
```

### Flags

| Flag     | Effect                                                          |
| -------- | --------------------------------------------------------------- |
| `--all`  | Collect every allowed ancestor instead of only the nearest one. |
| `--json` | Print the result as a JSON array.                               |

### Stdin

With no positional arguments, it reads stdin and treats each non-empty line as one tag set:

```
$ cat tags.txt | python genre.py --json
["Synthwave"]
["Electronic"]
```

## How the script works

For each input tag:

1. Normalize the input.
2. If the tag has a `map` rule, its replacements become the starting points (e.g. Chillwave -> Synthwave). Otherwise the tag itself is.
3. Perform a Breadth First Search (BFS) through the tag's parents in the DAG. Every visited node that is `keep` is collected.
4. In default mode, a path stops at the first kept genre it reaches. A genre marked `stop` is never climbed past in any mode.
5. If the tag has a `block` rule, those nodes are never entered while climbing.
6. In default mode, a result is dropped if another result descends from it, so only the most specific survive.

After all tags are processed:

7. Any result that descends from a `stop` result is dropped. e.g. If `Dream Pop` (stop) and one of its descendants both come out, only `Dream Pop` remains.
8. Preserve input tags that are already kept genres are added back, so an allowed input is never deleted.
9. Sort by depth, deepest first, then alphabetically. Depth is the longest path from a parentless node.

## Files

Both must sit next to `genre.py`.

### config.json

```json
{
  "genres": {
    "Synthwave": { "stop": true },
    "Electronic": {},
    "Folk": { "keep": false, "stop": true }
  },
  "tags": {
    "chillwave": { "map": ["Synthwave"] },
    "emo": { "block": ["punk"] }
  }
}
```

**`genres`**: `{name: {"keep": bool, "stop": bool}}`

| Field  | Default | Meaning                                                           |
| ------ | ------- | ----------------------------------------------------------------- |
| `keep` | `true`  | The genre may appear in output. Only kept genres are whitelisted. |
| `stop` | `false` | The walk never climbs past it, and it absorbs its descendants.    |

`{"keep": false, "stop": true}` is a dead end: tags that reach it climb no further and produce nothing.

**`tags`**: `{input tag: {"map": [...], "block": [...]}}`

| Field   | Meaning                                                                        |
| ------- | ------------------------------------------------------------------------------ |
| `map`   | Replacement starting points. Use for tags the DAG does not know or gets wrong. |
| `block` | Nodes this tag may never climb into.                                           |

Both fields are optional and can be combined on one tag.

`stop` is per node ("do not climb past me"). `block` is per input tag ("if you started from X, never enter Y").

### dag.json

```json
{
  "nodes": {
    "Shoegaze": {
      "parents": ["Alternative Rock"],
      "children": []
    }
  }
}
```

Each node lists its `parents` and/or `children`. Edges from both fields are merged into one child-to-parent map, so an edge declared on only one side still counts. No `roots` field is needed.

Source: [RateYourMusic](https://rateyourmusic.com/genres/)

## Notes

- In default mode, an allowed tag stops at itself and never climbs, so its `block` rule has no effect. Blocks on allowed genres only matter with `--all`. Blocks on non-allowed tags (like `emo`) always apply.
- `map` seeds are queued directly and are not filtered by `block`.
- Depth is recursive, so an extremely deep DAG (1000+ levels) can hit Python's recursion limit.
- Config and DAG load at import time.