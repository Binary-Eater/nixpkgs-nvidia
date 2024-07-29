{
  version,
  kernel ? null,
  url ? null,
  sha256_32bit ? null,
  sha256_64bit,
  sha256_aarch64 ? null,
  extractGSP ? true,
  settingsSha256 ? null,
  settingsVersion ? version,
  useGLVND ? true,
  useProfiles ? true,
  preferGtk2 ? false,
  ibtSupport ? false,

  prePatch ? null,
  postPatch ? null,
  patchFlags ? null,
  patches ? [ ],
  preInstall ? null,
  postInstall ? null,
  broken ? false,
  brokenOpen ? broken,
}@args:

{
  lib,
  stdenv,
  callPackage,
  pkgs,
  pkgsi686Linux,
  fetchurl,
  fetchzip,
  perl,
  nukeReferences,
  which,
  libarchive,
  # Whether to build the libraries only (i.e. not the kernel module or
  # nvidia-settings).  Used to support 32-bit binaries on 64-bit
  # Linux.
  libsOnly ? false,
  # don't include the bundled 32-bit libraries on 64-bit platforms,
  # even if it’s in downloaded binary
  disable32Bit ? stdenv.hostPlatform.system == "aarch64-linux",
  # 32 bit libs only version of this package
  lib32 ? null,
  # Whether to extract the GSP firmware, datacenter drivers needs to extract the
  # firmware
  firmware ? extractGSP,
  # Whether the user accepts the NVIDIA Software License
  config,
  acceptLicense ? config.nvidia.acceptLicense or false,
}:

with lib;

assert !libsOnly -> kernel != null;

let
  nameSuffix = optionalString (!libsOnly) "-${kernel.version}";
  pkgSuffix = optionalString (versionOlder version "304") "-pkg0";
  i686bundled = versionAtLeast version "391" && !disable32Bit;

  libPathFor =
    pkgs:
    lib.makeLibraryPath (
      with pkgs;
      [
        libdrm
        xorg.libXext
        xorg.libX11
        xorg.libXv
        xorg.libXrandr
        xorg.libxcb
        zlib
        stdenv.cc.cc
        wayland
        mesa
        libGL
        openssl
        dbus # for nvidia-powerd
      ]
    );

  # maybe silly since we've ignored this previously and just unfree..
  throwLicense = throw ''
    Use of NVIDIA Software requires license acceptance of the license:

      - License For Customer Use of NVIDIA Software [1]

    You can express acceptance by setting acceptLicense to true your nixpkgs.config.
    Example:

      configuration.nix:
        nixpkgs.config.allowUnfree = true;
        nixpkgs.config.nvidia.acceptLicense = true;

      config.nix:
        allowUnfree = true;
        nvidia.acceptLicense = true;

    [1]: https://www.nvidia.com/content/DriverDownloads/licence.php?lang=us
  '';

  self = stdenv.mkDerivation {
    name = "nvidia-x11-${version}${nameSuffix}";

    builder = ./builder.sh;

    src =
      if !acceptLicense && (openSha256 == null) then
        throwLicense
      else if stdenv.hostPlatform.system == "x86_64-linux" then
        fetchurl {
          urls =
            if args ? url then
              [ args.url ]
            else
              [
                "https://us.download.nvidia.com/XFree86/Linux-x86_64/${version}/NVIDIA-Linux-x86_64-${version}${pkgSuffix}.run"
                "https://download.nvidia.com/XFree86/Linux-x86_64/${version}/NVIDIA-Linux-x86_64-${version}${pkgSuffix}.run"
              ];
          sha256 = sha256_64bit;
        }
      else if stdenv.hostPlatform.system == "aarch64-linux" && sha256_aarch64 != null then
        fetchurl {
          urls =
            if args ? url then
              [ args.url ]
            else
              [
                "https://us.download.nvidia.com/XFree86/aarch64/${version}/NVIDIA-Linux-aarch64-${version}${pkgSuffix}.run"
                "https://download.nvidia.com/XFree86/Linux-aarch64/${version}/NVIDIA-Linux-aarch64-${version}${pkgSuffix}.run"
              ];
          sha256 = sha256_aarch64;
        }
      else
        throw "nvidia-x11 does not support platform ${stdenv.hostPlatform.system}";

    patches = if libsOnly then null else patches;
    inherit prePatch postPatch patchFlags;
    inherit preInstall postInstall;
    inherit version useGLVND useProfiles;
    inherit (stdenv.hostPlatform) system;
    inherit i686bundled;

    outputs =
      [ "out" ]
      ++ optional i686bundled "lib32"
      ++ optional (!libsOnly) "bin"
      ++ optional (!libsOnly && firmware) "firmware";
    outputDev = if libsOnly then null else "bin";

    kernel = if libsOnly then null else kernel.dev;
    kernelVersion = if libsOnly then null else kernel.modDirVersion;

    makeFlags = optionals (!libsOnly) (
      kernel.makeFlags
      ++ [
        "IGNORE_PREEMPT_RT_PRESENCE=1"
        "NV_BUILD_SUPPORTS_HMM=1"
        "SYSSRC=${kernel.dev}/lib/modules/${kernel.modDirVersion}/source"
        "SYSOUT=${kernel.dev}/lib/modules/${kernel.modDirVersion}/build"
      ]
    );

    hardeningDisable = [
      "pic"
      "format"
    ];

    dontStrip = true;
    dontPatchELF = true;

    libPath = libPathFor pkgs;
    libPath32 = optionalString i686bundled (libPathFor pkgsi686Linux);

    nativeBuildInputs = [
      perl
      nukeReferences
      which
      libarchive
    ] ++ optionals (!libsOnly) kernel.moduleBuildDependencies;

    disallowedReferences = optionals (!libsOnly) [ kernel.dev ];

    passthru = {
      open = callPackage ./open.nix {
        inherit kernel;
        nvidia_x11 = self;
        broken = brokenOpen;
      };
      settings = null;
      persistenced = null;
      compressFirmware = false;
      ibtSupport = ibtSupport || (lib.versionAtLeast version "530");
    } // optionalAttrs (!i686bundled) { inherit lib32; };

    meta = with lib; {
      homepage = "https://www.nvidia.com/object/unix.html";
      description = "X.org driver and kernel module for NVIDIA cards";
      license = licenses.unfreeRedistributable;
      platforms = [ "x86_64-linux" ] ++ optionals (sha256_aarch64 != null) [ "aarch64-linux" ];
      priority = 4; # resolves collision with xorg-server's "lib/xorg/modules/extensions/libglx.so"
      inherit broken;
    };
  };
in
self
