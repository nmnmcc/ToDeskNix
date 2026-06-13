# ToDeskNix

将 dl.todesk.com 上 ToDesk 的预构建二进制打包为 Nix flake。

ToDesk 官方下载站有 CDN 机器人防护，且 nixpkgs 中的版本较旧。本 flake 通过
archive.org 获取官方 `.deb` 发布包，解压后用 FHS 环境包装所有运行时依赖。

## 包含内容

ToDesk Linux 远程桌面客户端，从官方 x86_64 deb 打包。包含多个历史版本。

支持的系统：`x86_64-linux`。

## 版本层级

ToDesk 提供四个粒度级别：

| 包名 | 解析为 |
| --- | --- |
| `todesk` | 最新稳定版 |
| `todesk_4` | 最新 4.x.y.z |
| `todesk_4_8` | 最新 4.8.y.z |
| `todesk_4_8_6_2` | 精确 4.8.6.2 |

## 快速开始

直接运行：

```sh
NIXPKGS_ALLOW_UNFREE=1 nix run github:nmnmcc/ToDeskNix --impure
```

或构建：

```sh
NIXPKGS_ALLOW_UNFREE=1 nix build github:nmnmcc/ToDeskNix --impure
./result/bin/todesk
```

## Flake 配置

添加为 flake 输入：

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

## NixOS 模块

本 flake 提供 NixOS 模块，自动配置 ToDesk systemd 服务：

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

这将创建 `todeskd` systemd 服务，并将 `todesk` 命令添加到
`environment.systemPackages`。

## 使用 overlay

```nix
{
  nixpkgs.overlays = [
    todesk.overlays.default
  ];

  environment.systemPackages = [ pkgs.todesk ];
}
```

## 锁定版本

通过版本层级控制更新粒度：

```nix
# 始终使用最新版
todesk.packages.${system}.todesk

# 锁定 4.x 主版本
todesk.packages.${system}.todesk_4

# 锁定 4.8 次版本
todesk.packages.${system}.todesk_4_8

# 精确版本，永不变化
todesk.packages.${system}.todesk_4_8_6_2
```

## 更新

如果你的系统使用本 flake 作为输入，像其他输入一样更新即可：

```sh
nix flake update todesk
```

本仓库通过 GitHub Actions 每 12 小时自动更新。更新脚本爬取
`todesk.com/linux.html` 和 archive.org CDX API，将新版 deb 归档到
archive.org，计算 SHA256 校验和，并将变更提交到 `versions.json`。

使用 `python3 update.py --backfill` 可收集 archive.org 上所有历史版本。

## 工作原理

1. `update.py` 爬取 ToDesk Linux 下载页面并查询 archive.org CDX API
   获取所有已归档版本。
2. 新版本归档到 archive.org（原始 URL 受腾讯 EdgeOne CDN 机器人防护）。
3. 下载 deb 并计算其 Nix SRI 格式的 SHA256 哈希。
4. `flake.nix` 读取 `versions.json`，使用 `dpkg` 解压 deb，并用
   `buildFHSEnv` 包装所有运行时依赖（GTK、X11、PulseAudio 等）。

## 故障排查

ToDesk 是专有软件，需要在 Nix 配置中设置 `allowUnfree = true`，或在运行 Nix
命令时使用 `NIXPKGS_ALLOW_UNFREE=1 --impure`。

`todeskd` 服务需要 `/var/lib/todesk` 目录存在。NixOS 模块会自动创建该目录。
如果手动运行，请先创建：

```sh
sudo mkdir -p /var/lib/todesk
```

查看可用的包：

```sh
NIXPKGS_ALLOW_UNFREE=1 nix flake show github:nmnmcc/ToDeskNix --impure
```

## 许可

ToDesk 是专有软件。本 flake 将官方二进制文件重新打包供 Nix/NixOS 使用。
