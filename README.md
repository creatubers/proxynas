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

The Blackmagic RAW SDK is **not** included in this repository, since it is not
redistributable. For `.braw` support, get the SDK from Blackmagic Design and
place `BlackmagicRawAPI.dll`, `DecoderCUDA.dll`, `DecoderOpenCL.dll` and the
`InstructionSetServicesAVX*.dll` files in `portable/bin/`, along with a
`braw_decode` binary (`tools/braw_decode/braw_decode.cpp` shows how it is
built).

Everything else works without it: non-BRAW media is handled by FFmpeg alone.

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
