Windows 64-bit build. Unzip and run `Proxynas.exe`.

- FFmpeg is downloaded into `portable/bin/` on first launch.
- Blackmagic RAW (`.braw`) support is not bundled and is not downloaded
  automatically: the SDK cannot be redistributed. When a `.braw` file is found
  without it, Proxynas offers to open the Blackmagic download page
  (https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows)
  and to import the downloaded zip with the "Importar SDK BRAW (zip)" button.
  Everything else works without it.
- The build is unsigned, so Windows SmartScreen may warn on first launch.
