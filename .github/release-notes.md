Windows 64-bit build. Unzip and run `Proxynas.exe`.

- FFmpeg is downloaded into `portable/bin/` on first launch.
- Blackmagic RAW (`.braw`) support is not bundled and is not downloaded
  automatically. It needs the Blackmagic RAW SDK, which cannot be redistributed:
  put `BlackmagicRawAPI.dll`, `DecoderCUDA.dll`, `DecoderOpenCL.dll` and the
  `InstructionSetServicesAVX*.dll` files from the SDK in `portable/sdk/`, and a
  `braw_decode.exe` in `portable/bin/`. Everything else works without it.
- The build is unsigned, so Windows SmartScreen may warn on first launch.
