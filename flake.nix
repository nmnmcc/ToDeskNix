{
  description = "ToDesk — pre-built binaries from dl.todesk.com (via archive.org)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      versions = builtins.fromJSON (builtins.readFile ./versions.json);

      systems = [ "x86_64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;

      splitVer = v: builtins.filter builtins.isString (builtins.split "\\." v);

      latestOf = vers:
        builtins.foldl'
          (a: b: if builtins.compareVersions a b >= 0 then a else b)
          (builtins.head vers)
          (builtins.tail vers);

      mkTodesk = pkgs: version: info:
        let
          system = pkgs.stdenv.hostPlatform.system;
          platInfo = info.${system} or null;
        in
        if platInfo == null then null
        else
          let
            todesk-unwrapped = pkgs.stdenv.mkDerivation {
              pname = "todesk-unwrapped";
              inherit version;
              src = pkgs.fetchurl {
                url = platInfo.url;
                hash = platInfo.hash;
              };
              nativeBuildInputs = [ pkgs.rpm pkgs.cpio ];
              unpackPhase = ''
                rpm2cpio $src | cpio -idmv 2>/dev/null
              '';
              installPhase = ''
                mkdir -p $out/{bin,lib,opt/todesk,share}
                cp -r opt/todesk/* $out/opt/todesk/
                mv $out/opt/todesk/bin/* $out/bin/
                rmdir $out/opt/todesk/bin
                cp $out/bin/libmfx.so.1 $out/lib/ 2>/dev/null || true
                cp $out/bin/libglut.so.3 $out/lib/ 2>/dev/null || true
                cp "${pkgs.libayatana-appindicator}/lib/libayatana-appindicator3.so.1" \
                   "$out/bin/libappindicator3.so.1" 2>/dev/null || true
                mkdir -p $out/opt/todesk/{config,bin}
                cp -r usr/share/* $out/share/ 2>/dev/null || true
                cp -r etc $out/etc 2>/dev/null || true
              '';
            };
          in
          pkgs.buildFHSEnv {
            pname = "todesk";
            inherit version;
            targetPkgs = p: [
              todesk-unwrapped
              p.pulseaudio
              p.nspr
              p.kmod
              p.libxi
              p.systemdMinimal
              p.glib
              p.libz
              p.bash
              p.coreutils
              p.libx11
              p.libxext
              p.libxrandr
              p.glibc
              p.libdrm
              p.libGL
              p.procps
              p.cairo
              p.libxcomposite
              p.libxdamage
              p.libxfixes
              p.libxtst
              p.nss
              p.libxxf86vm
              p.gtk3
              p.gdk-pixbuf
              p.pango
              p.libva
            ];
            extraBwrapArgs = [
              "--tmpfs /opt/todesk"
              "--bind /var/lib/todesk /opt/todesk/config"
              "--bind ${todesk-unwrapped}/bin /opt/todesk/bin"
              "--bind /var/lib/todesk /etc/todesk"
            ];
            runScript = pkgs.writeShellScript "todesk.sh" ''
              export LIBVA_DRIVER_NAME=iHD
              export LIBVA_DRIVERS_PATH=${todesk-unwrapped}/bin
              if [ "''${1}" = 'service' ]; then
                /opt/todesk/bin/ToDesk_Service
              else
                /opt/todesk/bin/ToDesk
              fi
            '';
            extraInstallCommands = ''
              mkdir -p "$out/share/applications" "$out/share/icons"
              cp ${todesk-unwrapped}/share/applications/todesk.desktop $out/share/applications/
              cp -rf ${todesk-unwrapped}/share/icons/* $out/share/icons/
              substituteInPlace "$out/share/applications/todesk.desktop" \
                --replace-fail '/opt/todesk/bin/ToDesk' "$out/bin/todesk desktop" \
                --replace-fail '/opt/todesk/bin' "${todesk-unwrapped}/lib"
            '';
            meta = with pkgs.lib; {
              description = "ToDesk ${version} — Remote Desktop Application (pre-built binary)";
              homepage = "https://www.todesk.com/linux.html";
              sourceProvenance = [ sourceTypes.binaryNativeCode ];
              license = licenses.unfree;
              platforms = [ "x86_64-linux" ];
              mainProgram = "todesk";
            };
          };

      mkAllPackages = pkgs:
        let
          lib = nixpkgs.lib;
          system = pkgs.stdenv.hostPlatform.system;
          allVers = builtins.filter
            (ver: builtins.hasAttr system versions.versions.${ver})
            (builtins.attrNames versions.versions);
          mk = ver: mkTodesk pkgs ver versions.versions.${ver};

          parts = builtins.listToAttrs (map (ver: {
            name = ver;
            value = splitVer ver;
          }) allVers);

          exact = map (ver: {
            name = "todesk_${builtins.concatStringsSep "_" parts.${ver}}";
            value = mk ver;
          }) allVers;

          minorPairs = lib.mapAttrsToList (slug: vers: {
            name = "todesk_${slug}";
            value = mk (latestOf vers);
          }) (lib.groupBy (ver:
            let p = parts.${ver};
            in "${builtins.elemAt p 0}_${builtins.elemAt p 1}"
          ) allVers);

          majorPairs = lib.mapAttrsToList (slug: vers: {
            name = "todesk_${slug}";
            value = mk (latestOf vers);
          }) (lib.groupBy (ver:
            builtins.elemAt parts.${ver} 0
          ) allVers);

          latestPair =
            if allVers != []
            then [{ name = "todesk"; value = mk (latestOf allVers); }]
            else [];

          defaultPair =
            if allVers != []
            then [{ name = "default"; value = mk (latestOf allVers); }]
            else [];

        in
        builtins.listToAttrs (exact ++ minorPairs ++ majorPairs ++ latestPair ++ defaultPair);

    in
    {
      packages = eachSystem (system:
        mkAllPackages nixpkgs.legacyPackages.${system}
      );

      overlays.default = final: _prev: {
        todesk = (mkAllPackages final).todesk;
      };

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.todesk;
          todeskPkg = self.packages.${pkgs.stdenv.hostPlatform.system}.todesk;
        in {
          options.services.todesk = {
            enable = lib.mkEnableOption "ToDesk remote desktop service";
            package = lib.mkOption {
              type = lib.types.package;
              default = todeskPkg;
              description = "The ToDesk package to use.";
            };
          };
          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ cfg.package ];
            systemd.services.todeskd = {
              description = "ToDesk Daemon";
              after = [ "network.target" ];
              wantedBy = [ "multi-user.target" ];
              serviceConfig = {
                Type = "simple";
                ExecStart = "${cfg.package}/bin/todesk service";
                Restart = "on-failure";
              };
              preStart = ''
                mkdir -p /var/lib/todesk
              '';
            };
          };
        };
    };
}
