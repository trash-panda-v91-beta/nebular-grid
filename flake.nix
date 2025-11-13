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
            kustomize
            minijinja
            ntp
            yq-go
          ];

          shellHook = ''
            # Fix neogit "address already in use" error
            # Use /tmp with a unique subdirectory to avoid nix-shell TMPDIR issues
            if [ "$NEOGIT_TMPDIR_SET" = "" ]; then
              export NEOGIT_TMPDIR_SET=1
              export TMPDIR="/tmp/nix-shell-$$"
              mkdir -p "$TMPDIR"
              # Clean up on exit
              trap "rm -rf $TMPDIR" EXIT
            fi
          '';
        };
      }
    );
}
