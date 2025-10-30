{
  description = "Development environment for Nebular Grid";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            helmfile-wrapped
            gum
            just
            kubernetes-helm-wrapped
            minijinja
            ntp
            yq-go
          ];

          shellHook = ''
            echo "🚀 Nix dev environment loaded!"
          '';
        };
      }
    );
}
