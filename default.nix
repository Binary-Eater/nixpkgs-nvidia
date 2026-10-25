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
    version = "595.112.07";
    sha256_64bit = "sha256-Gjjs1Tii2mIypzMBhAY69Z6fyUbJCMylVb0HkJhIufA=";
    sha256_aarch64 = "sha256-7qQuOKX9xS/wpKa+bEOqsS2euJjJu182vl+6UU6bxR0=";
    inherit kernel kernelModuleMakeFlags;
  };

  new_feature = generic {
    version = "615.78.08";
    sha256_64bit = "sha256-Pj9t3cLudnoIGFMAr3vjyyhuznZpjS3eNSRZl4LQf/4=";
    sha256_aarch64 = "sha256-UHYBE1AYHoGgMfD9AS/jX+S+N8eCDWUft6qolK9Eejc=";
    inherit kernel kernelModuleMakeFlags;
  };

  beta = generic {
    version = "595.45.04";
    sha256_64bit = "sha256-zUllSSRsuio7dSkcbBTuxF+dN12d6jEPE0WgGvVOj14=";
    sha256_aarch64 = "sha256-jl6lQWsgF6ya22sAhYPpERJ9r+wjnWzbGnINDpUMzsk=";
    inherit kernel kernelModuleMakeFlags;
  };
}
