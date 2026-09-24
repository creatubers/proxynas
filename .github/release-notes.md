Windows 64-bit build. Unzip and run `Proxynas.exe`.

- FFmpeg is downloaded into `portable/bin/` on first launch.
- Blackmagic RAW (`.braw`) support needs the Blackmagic RAW SDK, which cannot be
  redistributed: drop `BlackmagicRawAPI.dll`, `DecoderCUDA.dll`,
  `DecoderOpenCL.dll` and the `InstructionSetServicesAVX*.dll` files from the SDK
  into `portable/bin/` next to `Proxynas.exe`. Everything else works without it.
- The build is unsigned, so Windows SmartScreen may warn on first launch.
