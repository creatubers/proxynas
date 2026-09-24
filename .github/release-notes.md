Windows 64-bit build. Unzip and run `Proxynas.exe`.

- FFmpeg is downloaded into `portable/bin/` on first launch.
- Blackmagic RAW (`.braw`) support is not bundled and is not downloaded
  automatically: the SDK cannot be redistributed. When a `.braw` file is found
  without it, Proxynas offers to open the Blackmagic download page
  (https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows)
  and to import the downloaded zip with the "Importar SDK BRAW (zip)" button.
  The decoder itself (`braw_decode.exe`) is already included. Everything else
  works without the SDK.
- The build is unsigned, so Windows SmartScreen warns on first launch, and
  Windows Defender or Chrome may flag `Proxynas.exe` as a trojan (usually
  `Trojan:Win32/Wacatac.H!ml`). It is a false positive: that verdict is
  Defender's machine-learning heuristic firing on unsigned PyInstaller
  executables, not a real detection. This build drops UPX compression and
  embeds a version resource to lower the odds, but only a code-signing
  certificate removes it for good. To run the app anyway:
  - Chrome: open `chrome://downloads` and choose "Keep dangerous file".
  - Defender: Windows Security -> Protection history -> select the detection
    -> Allow, or add an exclusion for the unzipped folder.
  - `curl -L -o Proxynas-win64.zip <url>` skips the browser-side block.
