{
  lib,
  callPackage,
  stdenv,
  pkgsi686Linux,
  kernel ? null,
  kernelModuleMakeFlags ? null,
}:

let
  generic =
    args:
    let
      imported = import ./generic.nix args;
    in
    callPackage imported {
      lib32 =
        (pkgsi686Linux.callPackage imported {
          libsOnly = true;
          kernel = null;
        }).out;
    };

  selectHighestVersion = a: b: if lib.versionOlder a.version b.version then b else a;
in
rec {
  mkDriver = generic;

  # Official Unix Drivers - https://www.nvidia.com/en-us/drivers/unix/
  # Branch/Maturity data - http://people.freedesktop.org/~aplattner/nvidia-versions.txt

  # Policy: use the highest stable version as the default (on our master).
  latest = selectHighestVersion production new_feature;

  bleeding_edge = selectHighestVersion latest beta;

  production = generic {
    version = "595.80";
    sha256_64bit = "sha256-PVTIP+B/01c/8M66hXTAYTLg9T2Hy9u1gq43K7TF1Hg=";
    sha256_aarch64 = "sha256-62uqbRsF+dizUqvXhBfmVFeV2gg4BH6f7kOta+uMMuk=";
    inherit kernel kernelModuleMakeFlags;
  };

  new_feature = generic {
    version = "610.43.02";
    sha256_64bit = "sha256-MDSgVLtM33dS/43CclZMsQVROAS/9TU4lFkBsWyndGM=";
    sha256_aarch64 = "sha256-isWTnokUA/dzWocFBLalnk4+O5gSExVjs3dVpdYTU88=";
    inherit kernel kernelModuleMakeFlags;
  };

  beta = generic {
    version = "595.45.04";
    sha256_64bit = "sha256-zUllSSRsuio7dSkcbBTuxF+dN12d6jEPE0WgGvVOj14=";
    sha256_aarch64 = "sha256-jl6lQWsgF6ya22sAhYPpERJ9r+wjnWzbGnINDpUMzsk=";
    inherit kernel kernelModuleMakeFlags;
  };
}
