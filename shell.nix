{ pkgs ? import <nixpkgs> { } }:
  with pkgs;
  mkShell {
    buildInputs = [
      (python39.withPackages (ps: with ps; [pyqt5]))
      # Krita 5.1 on many platforms is packaged with Python 3.8.
      # However version 3.8 has a broken packages, so closest working one is used.
      # (krita.override{python3Packages = python39Packages;})
      krita
    ];
    shellHook = ''
      # fixes libstdc++ issues and libgl.so issues
      LD_LIBRARY_PATH=${stdenv.cc.cc.lib}/lib/:/run/opengl-driver/lib/
      # fixes xcb issues :
      QT_PLUGIN_PATH=${qt5.qtbase}/${qt5.qtbase.qtPluginPrefix}
    '';
  }
