{
  description = "Hive Browser dev environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    paradedb.url = "github:paradedb/paradedb";
  };

  outputs = { self, nixpkgs, flake-utils, paradedb }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pg_search = paradedb.packages.${system}.pg_search-pg16;
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Python
            python312
            uv

            # JavaScript
            bun

            # Database
            postgresql_16
            pg_search

            # Bioinformatics
            blast
            mafft

            # System
            openssl
            pkg-config
          ];

          shellHook = ''
            echo "hive-browser dev shell"
          '';
        };
      });
}
