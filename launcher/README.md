# Recomp Launcher

A profile-driven launcher for ReXGlue recomp projects. One executable,
any game: everything the launcher needs to know about a specific recomp
lives in a small `launcher.json` sitting next to the game.

Features: graphics/display settings, a Profile tab (gamertag + online
username), a Mods manager, a profile creator for new games, and a banner
image in the header.

## What it does

- **Adjust settings before launch** — resolution, fullscreen, monitor,
  internal resolution scale, anisotropic filtering, post-process effects,
  vsync, audio/input options, language, logging.
- **Profile & online username** — a Profile tab with the player name and an
  online username, written as cvars (`profile_name`, `online_username` by
  default — configurable per game). Recomps that implement the synthetic
  profile (see the Puzzle Fighter recomp's `docs/synthetic_profile.md`) read
  `profile_name` and show your name in-game; `online_username` is reserved
  for online features.
- **Mods** — enable/disable mod folders per game; the launcher stages a
  modded copy of the game data on launch (see below).
- **Launches the game** with the arguments the recomp needs
  (`--gpu_plugin xenos`, quoted `--game_data_root`, plus extra args).
- **Stays in sync with the in-game settings dialog** — both edit the same
  cvar TOML the runtime reads (`<game exe folder>\<exe name>.toml`, e.g.
  `puzzlefighter.toml`). Comments and unknown keys in the file are preserved.
- **Profile creator** — File → New profile generates a launcher.json for a
  new recomp (points at the exe and data, copies the banner, writes the
  standard settings tabs).

## Layout

```
recomp_launcher\
  launcher.json     Puzzle Fighter profile (the per-game part)
  banner.jpg        header image (referenced by the profile)
  build.ps1         builds publish\RecompLauncher.exe
  src\RecompLauncher\  the WPF app (game-agnostic)
  mods\             drop mod folders here (created on demand)
  publish\          build output
```

## Build

Requires the .NET SDK (10+):

```
.\build.ps1            # release -> publish\RecompLauncher.exe (self-contained single file)
.\build.ps1 -Debug     # fast debug build
```

`RecompLauncher.exe` looks for a profile in this order:

1. `--profile <path>` command-line argument
2. `launcher.json` next to `RecompLauncher.exe`
3. `launcher.json` in the working directory
4. the last profile you opened (stored in `%APPDATA%\RecompLauncher\recent.json`)

## Mods

Put each mod in its own folder inside `mods\` (or add folders from anywhere
via *Add mod folder...*). A mod is any folder of files — its contents are
overlaid onto the game data with the same paths (e.g. a mod containing
`TEXT\STR_EN_error_message.TXT` replaces/adds that file in the game).

On launch with mods enabled, the launcher:

1. Builds a staged copy of the game data using **hard links** (fast, and
   the original data is never modified — deleting a link doesn't touch the
   source),
2. Copies the enabled mods' files over the links (mods higher in the list
   win conflicts), into `mods\.staging`,
3. Launches the game with `--game_data_root` pointing at the staging folder.

The stage is cached: it's rebuilt only when the enabled mod set or the game
data changes. Untick all mods (or Reset) to launch against the real data.

Why not the runtime's `update_data_root`? The ReXGlue runtime mounts it as a
separate `update:` device — verified empirically that it does **not** layer
over `game:\` paths, so it can't be used for file-replacement mods.

## Using it with another recomp

Either run **File → New profile...** (fills in everything for you), or copy
`RecompLauncher.exe` + a hand-written `launcher.json` into the new game's
folder. Only the `game` block changes:

```json
{
  "schema": 1,
  "game": {
    "name": "My Other Game",
    "subtitle": "Xbox 360 recomp (ReXGlue)",
    "exe": "out/build/win-amd64-release/mygame.exe",
    "gameDataRoot": "../extracted_game_data",
    "args": [ "--gpu_plugin", "xenos" ],
    "banner": "banner.jpg",
    "usernameCvar": "profile_name",
    "onlineUsernameCvar": "online_username"
  },
  "tabs": [ "...standard ReXGlue tabs..." ]
}
```

- `exe` / `gameDataRoot` / `banner` are relative to the `launcher.json` file.
- `args` are fixed command-line arguments always passed to the exe.
- `config` (optional) overrides the cvar TOML location; it defaults to
  `<exe folder>\<exe name>.toml` (ReXGlue convention).
- `usernameCvar` / `onlineUsernameCvar` add the Profile tab with those two
  text fields. Any cvar name works — the recomp reads it when it's ready.
- `modsDir` (optional) overrides the mods folder location (default `mods`).
- The `tabs` block is a settings schema: each item is a cvar with a UI type
  (`bool`, `int`, `double`, `text`, `choice`, `resolution`, `string`),
  optional `min`/`max`, `choices`, `presets`, `hint`, `advanced`. ReXGlue
  recomps share the same cvars, so the standard tabs work as-is.

### Notes on defaults

Settings you never touch are never written to the config file, so the
runtime's compiled-in default always wins while a value is absent. The
`default` in the profile is only what the UI *shows* for an absent value
(and what "Reset to defaults" restores to). "Reset to defaults" removes the
launcher-managed keys entirely, returning the game to factory behavior.

### Extra launch arguments

The Advanced tab has a free-text box appended to the launch command
(e.g. `--user_data_root "D:\saves"`), remembered per profile in
`%APPDATA%\RecompLauncher\recent.json`.

## In-game overlays (ReXGlue runtime)

| Key          | Action              |
|--------------|---------------------|
| F3           | Debug overlay       |
| F4           | Settings dialog     |
| ` (backtick) | Console             |
| F7           | Achievements overlay|
