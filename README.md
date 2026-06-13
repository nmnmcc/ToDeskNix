# ToDeskNix

Nix flake for ToDesk — pre-built binaries from dl.todesk.com.

Translations: [简体中文](README.zh-CN.md).

The official ToDesk download site is behind CDN bot protection, and
nixpkgs ships an older version. This flake fetches the `.deb` release
via archive.org, extracts it, and wraps it in an FHS environment with
all required dependencies.

## What you get

The ToDesk remote desktop client for Linux, packaged from the official
x86_64 deb. Multiple historical versions are available.

Supported systems: `x86_64-linux`.

## Version hierarchy

ToDesk is available at four granularity levels:

| Package | Resolves to |
| --- | --- |
| `todesk` | latest stable version |
| `todesk_4` | latest 4.x.y.z |
| `todesk_4_8` | latest 4.8.y.z |
| `todesk_4_8_6_2` | exactly 4.8.6.2 |

## Quick start

Run directly:

```sh
NIXPKGS_ALLOW_UNFREE=1 nix run github:nmnmcc/ToDeskNix --impure
```

Or build:

```sh
NIXPKGS_ALLOW_UNFREE=1 nix build github:nmnmcc/ToDeskNix --impure
./result/bin/todesk
```

## Flake setup

Add as a flake input:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    todesk.url = "github:nmnmcc/ToDeskNix";
  };

  outputs = { nixpkgs, todesk, ... }: {
    devShells.x86_64-linux.default = let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in pkgs.mkShell {
      packages = [
        todesk.packages.x86_64-linux.todesk
      ];
    };
  };
}
```

## NixOS module

This flake provides a NixOS module that sets up the ToDesk systemd
service:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    todesk.url = "github:nmnmcc/ToDeskNix";
  };

  outputs = { nixpkgs, todesk, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        todesk.nixosModules.default
        {
          nixpkgs.config.allowUnfree = true;
          services.todesk.enable = true;
        }
      ];
    };
  };
}
```

This creates a `todeskd` systemd service and adds the `todesk` command
to `environment.systemPackages`.

### Client-only mode (security hardening)

To prevent this machine from being remotely controlled while still
allowing you to control other machines:

```nix
{
  services.todesk = {
    enable = true;
    allowBeControlled = false;
  };
}
```

This strips the `ToDesk_Session` binary from the package. The daemon
can still run and you can initiate outgoing connections, but incoming
control sessions will fail because the session handler does not exist.

A standalone `todesk-client` package is also available:

```sh
NIXPKGS_ALLOW_UNFREE=1 nix run github:nmnmcc/ToDeskNix#todesk-client --impure
```

## Using the overlay

```nix
{
  nixpkgs.overlays = [
    todesk.overlays.default
  ];

  environment.systemPackages = [ pkgs.todesk ];
}
```

## Pinning a version

Use the version hierarchy to control how aggressively you track updates:

```nix
# Always the latest
todesk.packages.${system}.todesk

# Stay on the 4.x major track
todesk.packages.${system}.todesk_4

# Pin to the 4.8 minor track
todesk.packages.${system}.todesk_4_8

# Exact version, never changes
todesk.packages.${system}.todesk_4_8_6_2
```

## Updating

If your system uses this flake as an input, update like any other:

```sh
nix flake update todesk
```

This repository is updated automatically every 12 hours via GitHub
Actions. The update script scrapes `todesk.com/linux.html` and the
archive.org CDX API, archives new deb releases, computes SHA256
checksums, and commits the changes to `versions.json`.

Use `python3 update.py --backfill` to collect all historical versions
from archive.org.

## How it works

1. `update.py` scrapes the ToDesk Linux download page and queries the
   archive.org CDX API for all archived versions.
2. New versions are archived on archive.org (the original URL is behind
   Tencent EdgeOne CDN bot protection).
3. The deb is downloaded and its SHA256 hash is computed in Nix SRI
   format.
4. `flake.nix` reads `versions.json`, extracts the deb with `dpkg`,
   and wraps the result in a `buildFHSEnv` with all required runtime
   dependencies (GTK, X11, PulseAudio, etc.).

## Troubleshooting

ToDesk is proprietary software. You must set `allowUnfree = true` in
your Nix configuration, or use `NIXPKGS_ALLOW_UNFREE=1 --impure` when
running Nix commands.

When using `nix run`, configuration state is ephemeral by default.
To persist settings across runs, create `/var/lib/todesk`:

```sh
sudo mkdir -p /var/lib/todesk
```

The NixOS module creates this directory automatically.

To see available packages:

```sh
NIXPKGS_ALLOW_UNFREE=1 nix flake show github:nmnmcc/ToDeskNix --impure
```

## License

ToDesk is proprietary software. This flake repackages the official
binaries for use with Nix/NixOS.
