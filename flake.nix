# This is based on the nix-installer flake.nix.
# I'm no Nix expert, please let me know how this could be improved.
{
  description = "The Nixsa standalone nix tarball";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1.0.tar.gz";

    fenix = {
      url = "https://flakehub.com/f/nix-community/fenix/0.1.1584.tar.gz";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    naersk = {
      url = "github:nix-community/naersk";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix = {
      url = "github:NixOS/nix/38bfbb297c380f8b07d8a20ffdeb72da71c1567c";
      # url = "https://flakehub.com/f/DeterminateSystems/nix/=2.23.3.tar.gz";
    };
  };

  outputs =
    { self
    , nixpkgs
    , fenix
    , naersk
    , nix
    }:
    let
      version = (builtins.fromTOML (builtins.readFile nixsa-bin/Cargo.toml)).package.version;

      supportedSystems = [ "i686-linux" "x86_64-linux" "aarch64-linux" ];

      forAllSystems = f: nixpkgs.lib.genAttrs supportedSystems (system: (forSystem system f));

      forSystem = system: f: f rec {
        inherit system;
        pkgs = import nixpkgs { inherit system; overlays = [ self.overlays.default ]; };
        lib = pkgs.lib;
      };

      fenixToolchain = system: with fenix.packages.${system};
        combine ([
          stable.clippy
          stable.rustc
          stable.cargo
          stable.rustfmt
          stable.rust-src
        ] ++ nixpkgs.lib.optionals (system == "x86_64-linux") [
          targets.x86_64-unknown-linux-musl.stable.rust-std
        ] ++ nixpkgs.lib.optionals (system == "i686-linux") [
          targets.i686-unknown-linux-musl.stable.rust-std
        ] ++ nixpkgs.lib.optionals (system == "aarch64-linux") [
          targets.aarch64-unknown-linux-musl.stable.rust-std
        ]);

    in
    {
      overlays.default = final: prev:
        let
          toolchain = fenixToolchain final.stdenv.system;
          naerskLib = final.callPackage naersk {
            cargo = toolchain;
            rustc = toolchain;
          };
          sharedAttrs = {
            name = "nixsa-bin";
            inherit version;
            src = builtins.path {
              name = "nixsa-bin-source";
              path = ./nixsa-bin;
              filter = (path: type: baseNameOf path != "nix" && baseNameOf path != ".github");
            };

            nativeBuildInputs = [ ];

            doCheck = true;
            cargoTestOptions = f: f ++ [ "--all" ];

            override = { preBuild ? "", ... }: {
              preBuild = preBuild + ''
                # logRun "cargo clippy --all-targets --all-features -- -D warnings"
              '';
            };
          };
        in
        {
          nixsa-bin = naerskLib.buildPackage sharedAttrs;
        } // nixpkgs.lib.optionalAttrs (prev.stdenv.system == "x86_64-linux") rec {
          default = nixsa-bin-static;
          nixsa-bin-static = naerskLib.buildPackage
            (sharedAttrs // {
              CARGO_BUILD_TARGET = "x86_64-unknown-linux-musl";
            });
        } // nixpkgs.lib.optionalAttrs (prev.stdenv.system == "i686-linux") rec {
          default = nixsa-bin-static;
          nixsa-bin-static = naerskLib.buildPackage
            (sharedAttrs // {
              CARGO_BUILD_TARGET = "i686-unknown-linux-musl";
            });
        } // nixpkgs.lib.optionalAttrs (prev.stdenv.system == "aarch64-linux") rec {
          default = nixsa-bin-static;
          nixsa-bin-static = naerskLib.buildPackage
            (sharedAttrs // {
              CARGO_BUILD_TARGET = "aarch64-unknown-linux-musl";
            });
        };


      devShells = forAllSystems ({ system, pkgs, ... }:
        let
          toolchain = fenixToolchain system;
          check = import ./nix/check.nix { inherit pkgs toolchain; };
        in
        {
          default = pkgs.mkShell {
            name = "nixsa-shell";

            RUST_SRC_PATH = "${toolchain}/lib/rustlib/src/rust/library";

            nativeBuildInputs = [ ];
            buildInputs = [
              toolchain
              pkgs.rust-analyzer
              pkgs.cacert
              pkgs.cargo-outdated
              pkgs.cargo-audit
              pkgs.cargo-watch
              pkgs.nixpkgs-fmt
              check.check-rustfmt
              check.check-spelling
              check.check-nixpkgs-fmt
              check.check-editorconfig
              check.check-semver
              check.check-clippy
            ];
          };
        });

      checks = forAllSystems ({ system, pkgs, ... }:
        let
          toolchain = fenixToolchain system;
          check = import ./nix/check.nix { inherit pkgs toolchain; };
        in
        {
          check-rustfmt = pkgs.runCommand "check-rustfmt" { buildInputs = [ check.check-rustfmt ]; } ''
            cd ${./nixsa-bin}
            check-rustfmt
            touch $out
          '';
          check-spelling = pkgs.runCommand "check-spelling" { buildInputs = [ check.check-spelling ]; } ''
            cd ${./nixsa-bin}
            check-spelling
            touch $out
          '';
          check-nixpkgs-fmt = pkgs.runCommand "check-nixpkgs-fmt" { buildInputs = [ check.check-nixpkgs-fmt ]; } ''
            cd ${./nixsa-bin}
            check-nixpkgs-fmt
            touch $out
          '';
          check-editorconfig = pkgs.runCommand "check-editorconfig" { buildInputs = [ pkgs.git check.check-editorconfig ]; } ''
            cd ${./nixsa-bin}
            check-editorconfig
            touch $out
          '';
          check-ruff = pkgs.runCommand "check-ruff" { buildInputs = [ check.check-ruff ]; } ''
            cd ${./nixsa-build}
            check-ruff
            touch $out
          '';
        });

      packages = forAllSystems
        ({ system, pkgs, ... }:
          rec {
            inherit (pkgs) nixsa-bin nixsa-bin-static;
            closureInfo = pkgs.buildPackages.closureInfo {
              rootPaths = [
                nix.packages."${system}".nix
                nix.inputs.nixpkgs.legacyPackages."${system}".cacert
                nixsa-bin-static
              ];
            };
            nixsa-dir = pkgs.stdenv.mkDerivation {
              pname = "nixsa-dir";
              inherit version;
              src = ./nixsa-build;
              buildInputs = [ pkgs.python3 pkgs.bubblewrap ];
              buildPhase = ''
                set -x
                python3 nixsa_build.py ${closureInfo} output
                set +x
              '';
              installPhase = ''
                cp -a output $out
              '';
            };
            nixsa-tarball = pkgs.stdenv.mkDerivation {
              pname = "nixsa-tarball";
              inherit version;
              src = ./nixsa-build;
              buildInputs = [ pkgs.xz ];
              buildPhase = ''
                dir=nixsa
                fn=nixsa-${version}-${system}.tar.xz
                mkdir $dir
                cp -a ${nixsa-dir}/* $dir/
                chmod -R u+w $dir
                chmod -R u-w $dir/nix/store/*
                tar -cvJf $fn --owner=0 --group=0 --mtime='1970-01-01' --absolute-names --hard-dereference $dir
              '';
              installPhase = ''
                mkdir $out
                cp $fn $out/
              '';
            };
            default = nixsa-tarball;
          });

      # hydraJobs = {
      #   vm-test = import ./nix/tests/vm-test {
      #     inherit forSystem;
      #     inherit (nixpkgs) lib;

      #     binaryTarball = nix.tarballs_indirect;
      #   };
      #   container-test = import ./nix/tests/container-test {
      #     inherit forSystem;

      #     binaryTarball = nix.tarballs_indirect;
      #   };
      # };
    };
}
