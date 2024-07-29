{
  stdenv,
  lib,
  kernel,
  nvidia_x11,
  broken ? false,
}:

let
  nvidiaDriverArch =
    if stdenv.hostPlatform.system == "x86_64-linux" then
      "x86_64"
    else if stdenv.hostPlatform.system == "aarch64-linux" then
      "aarch64"
    else
      throw "nvidia-open does not support platform ${stdenv.hostPlatform.system}";
in
stdenv.mkDerivation (
  {
    pname = "nvidia-open";
    version = "${kernel.version}-${nvidia_x11.version}";

    # use kernel-open directory of runfile
    src = nvidia_x11.src;
    unpackCmd = "sh $curSrc -x";
    sourceRoot = "NVIDIA-Linux-${nvidiaDriverArch}-${nvidia_x11.version}/kernel-open";

    nativeBuildInputs = kernel.moduleBuildDependencies;

    makeFlags = kernel.makeFlags ++ [
      "SYSSRC=${kernel.dev}/lib/modules/${kernel.modDirVersion}/source"
      "SYSOUT=${kernel.dev}/lib/modules/${kernel.modDirVersion}/build"
      "MODLIB=$(out)/lib/modules/${kernel.modDirVersion}"
      {
        aarch64-linux = "TARGET_ARCH=aarch64";
        x86_64-linux = "TARGET_ARCH=x86_64";
      }
      .${stdenv.hostPlatform.system}
    ];

    installTargets = [ "modules_install" ];
    enableParallelBuilding = true;

    meta = with lib; {
      description = "NVIDIA Linux Open GPU Kernel Module";
      homepage = "https://github.com/NVIDIA/open-gpu-kernel-modules";
      license = with licenses; [
        gpl2Plus
        mit
      ];
      platforms = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      inherit broken;
    };
  }
  // lib.optionalAttrs stdenv.hostPlatform.isAarch64 {
    env.NIX_CFLAGS_COMPILE = "-fno-stack-protector";
  }
)
