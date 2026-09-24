# Proxynas

Desktop tool for camera media workflows: generates lightweight proxies from
Blackmagic RAW, video, RAW stills and audio, and can transcode a folder into a
portable AV1 backup. Windows and Linux (the UI is in Spanish).

Hardware encoders used when available: `av1_nvenc`, `av1_qsv`, `av1_amf`,
`hevc_nvenc`, `hevc_qsv`, `hevc_amf`, falling back to `libx265` / software AV1.

## Requirements

- Python 3.10+
- FFmpeg (see below)
- For `.braw` files only: the Blackmagic RAW SDK (see below)

```
pip install -r requirements.txt
```

## Run

```
python Proxynas.py                                              # GUI
python Proxynas.py --cli <source_dir> <dest_dir> [--no-transcode]
```

## FFmpeg

On Windows, Proxynas downloads a current FFmpeg build into `portable/bin/` on
first launch. Otherwise put `ffmpeg` and `ffprobe` on `PATH`, or drop the
binaries in `portable/bin/`.

## Blackmagic RAW

The Blackmagic RAW SDK is **not** included in this repository and is **not**
downloaded automatically: Blackmagic does not allow redistributing it and the
download requires accepting their license.

Only `.braw` files need it. When you point Proxynas at a folder that contains
`.braw` files and the SDK is missing, it shows a dialog with the download page
(`https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows`) and
offers to import the zip you downloaded. Folders without `.braw` are never
checked, so it does not nag over FFmpeg-only material. That check only looks a
few levels deep (camera cards are shallow) to avoid walking a whole archive; if
it misses a deeply nested `.braw`, the proxy or transcode run that needs it
shows the same dialog. Importing copies `BlackmagicRawAPI.dll`,
`DecoderCUDA.dll`, `DecoderOpenCL.dll` and the `InstructionSetServicesAVX*.dll`
files into `portable/sdk/`; the **"Importar SDK BRAW (zip)"** button in the
proxies panel does the same thing by hand. Any recent SDK version works: files
are matched by name and the x64 ones are preferred.

The Windows download is a zip of `.msi` installers rather than loose DLLs, so
Proxynas extracts them with `msiexec /a` (nothing is installed) and takes the
x64 copies, never the ARM64 ones.

`.braw` also needs `braw_decode.exe` in `portable/bin/`. It is **not** part of
the SDK: it is Proxynas's own decoder (source in `tools/braw_decode/`, built
against the SDK headers), and the Windows builds already include it.

Everything else works without it: non-BRAW media is handled by FFmpeg alone.
`python test_braw_sdk_import.py` checks the zip import and the folder warning.

## Diagnostics

`Ejecutar diagnostico encoders.bat` (or `python encoder_diagnostics.py`) probes
which hardware encoders actually work on this machine and writes a report into
`diagnosticos/`.

## Build

```
./build_proxynas.ps1
```

Produces `dist/Proxynas/`. `portable/` and `vendor/` are bundled into the build
when present.

## Antivirus

The Windows build is unsigned. SmartScreen warns on first launch, and Windows
Defender or Chrome may flag `Proxynas.exe` as `Trojan:Win32/Wacatac.H!ml`.
That is a false positive: it is Defender's machine-learning heuristic firing
on unsigned PyInstaller executables, not a real detection. The build avoids
UPX and embeds a version resource to lower the odds, but only a code-signing
certificate removes it for good.

- Chrome: open `chrome://downloads` and choose "Keep dangerous file".
- Defender: Windows Security -> Protection history -> select the detection ->
  Allow, or add an exclusion for the unzipped folder.
- `curl -L -o Proxynas-win64.zip <release url>` skips the browser-side block.

False positives can also be reported to Microsoft:
<https://www.microsoft.com/en-us/wdsi/filesubmission>.

## License

MIT — see `LICENSE`. FFmpeg and the Blackmagic RAW SDK are separate products
with their own licenses and are not covered by it. Proxynas is not
affiliated with or endorsed by Blackmagic Design, and Blackmagic RAW is a
trademark of Blackmagic Design Pty. Ltd.
