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
    version = "595.71.05";
    sha256_64bit = "sha256-NiA7iWC35JyKQva6H1hjzeNKBek9KyS3mK8G3YRva4I=";
    sha256_aarch64 = "sha256-XzKloS00dFKTd4ATWkTIhm9eG/OzR/Sim6MboNZWPu8=";
    inherit kernel kernelModuleMakeFlags;
  };

  new_feature = generic {
    version = "590.48.01";
    sha256_64bit = "sha256-ueL4BpN4FDHMh/TNKRCeEz3Oy1ClDWto1LO/LWlr1ok=";
    sha256_aarch64 = "sha256-FOz7f6pW1NGM2f74kbP6LbNijxKj5ZtZ08bm0aC+/YA=";
    inherit kernel kernelModuleMakeFlags;
  };

  beta = generic {
    version = "595.45.04";
    sha256_64bit = "sha256-zUllSSRsuio7dSkcbBTuxF+dN12d6jEPE0WgGvVOj14=";
    sha256_aarch64 = "sha256-jl6lQWsgF6ya22sAhYPpERJ9r+wjnWzbGnINDpUMzsk=";
    inherit kernel kernelModuleMakeFlags;
  };
}
