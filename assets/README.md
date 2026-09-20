# Assets

Binary files that give Bonfire its face outside the code: icons, avatars, banners. Anything a person uploads to Discord, GitHub or a README header lives here, so there is one place to look and one copy of each file.

## What goes where

| Kind of file | Home |
|---|---|
| Project identity: icon, Discord application avatar, social or README banner | `assets/brand/` |
| Identity for one game (for example a Valheim-themed avatar) | `assets/brand/<game>/` |
| Diagrams | Not here. Write them as Mermaid inside the document that explains them (`docs/`) |
| Screenshots that illustrate one document | `docs/img/`, next to the document, not here |
| Anything code loads at run time | With that code, not here |

If a new kind of asset fits none of the rows, add a directory under `assets/` and a row to this table in the same PR.

## Rules

- **Names:** lowercase kebab-case, `bonfire-<what>[-<variant>].<ext>`, for example `bonfire-icon.png`, `bonfire-icon-512.png`, `bonfire-banner-dark.png`.
- **Formats:** SVG when a vector source exists; otherwise PNG with transparency. No JPEG for identity images.
- **Size:** keep each file under 1 MB. Git keeps every version forever, so replace a file only when the image really changed, and never commit working files (`.psd`, `.xcf`, exports in several sizes "just in case").
- **Derivatives:** commit the largest clean original. Add a resized or cropped copy only when a consumer needs exact dimensions (Discord avatars are square, 512 × 512 or larger), and list it in the inventory.
- **Provenance:** every file gets an inventory row saying where it came from and where it is used. For generated images, record the tool; for third-party material, the licence.
- **Third-party marks:** logos of other companies or games inside an image are their owners' trademarks. Fine for this private project's avatar; revisit before using the image anywhere public or commercial.
- **No secrets in pixels:** no screenshots showing IPs, tokens, player IDs or webhook URLs.

## Inventory

| File | What | Origin | Used in |
|---|---|---|---|
| `brand/bonfire-icon.png` | Project icon: campfire under a server cloud, with a game controller, a Viking helmet and an Azure mark, in a green ring. 1320 × 720 RGBA, the round icon centred on a transparent canvas | Provided by the owner, 2026-09-20 | Not referenced yet |
