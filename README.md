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

Only `.braw` files need it. When Proxynas finds a `.braw` file and the SDK is
missing, it offers to open the download page
(`https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows`),
and then to import the zip you downloaded: the **"Importar SDK BRAW (zip)"**
button in the proxies panel copies `BlackmagicRawAPI.dll`, `DecoderCUDA.dll`,
`DecoderOpenCL.dll` and the `InstructionSetServicesAVX*.dll` files into
`portable/sdk/`. Any recent SDK version works: files are matched by name and the
x64 ones are preferred.

`.braw` also needs `braw_decode.exe` in `portable/bin/`. It is **not** part of
the SDK: it is Proxynas's own decoder, built from
`tools/braw_decode/braw_decode.cpp` against the SDK headers.

Everything else works without it: non-BRAW media is handled by FFmpeg alone.
`python test_braw_sdk_import.py` checks the zip import picks the right files.

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

## License

MIT — see `LICENSE`. FFmpeg and the Blackmagic RAW SDK are separate products
with their own licenses and are not covered by it.
