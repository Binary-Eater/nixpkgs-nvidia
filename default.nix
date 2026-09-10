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
    version = "595.99.02";
    sha256_64bit = "sha256-6HR3lYv3YwcFSTJL1a1slI66btIQ5EAFs+/4SUD24ew=";
    sha256_aarch64 = "sha256-CCqHZTN2KNOZ4yZp2rDcuRJp9pHfRw47k4m4dWnS/2w=";
    inherit kernel kernelModuleMakeFlags;
  };

  new_feature = generic {
    version = "615.71.09";
    sha256_64bit = "sha256-zc7tIrvrYSSNGm3qvCWWZz46ZQFpjucayNL9wo87cP4=";
    sha256_aarch64 = "sha256-IbekQhE7cFfmnPZaLY9NDYcF7CoNZ+2Qb7sRd4EOgWM=";
    inherit kernel kernelModuleMakeFlags;
  };

  beta = generic {
    version = "595.45.04";
    sha256_64bit = "sha256-zUllSSRsuio7dSkcbBTuxF+dN12d6jEPE0WgGvVOj14=";
    sha256_aarch64 = "sha256-jl6lQWsgF6ya22sAhYPpERJ9r+wjnWzbGnINDpUMzsk=";
    inherit kernel kernelModuleMakeFlags;
  };
}
