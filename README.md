# Proxynas

**EN** | [ES](README.es.md)

Proxynas creates video proxies and backs up folders of audiovisual media. The Windows release is portable: extract it and run it, with no installer.

## Download and use

1. Download the ZIP from the [latest release](https://github.com/creatubers/proxynas/releases/latest), which also includes the changelog.
2. Extract the entire folder and open `Proxynas.exe`.
3. Select a source folder. For backups, also choose a destination outside the source folder.

The interface is available in English and Spanish. Until you choose a language or light/dark mode in the app, it follows your system settings at startup.

## What it does

- **Proxies:** creates H.264 or H.265 files in a `Proxy` folder next to the original videos. You can choose the codec and CPU or GPU encoding in the app.
- **Backup:** processes the source folder into the chosen destination. You can select all files, video only, audio and images, or other files, and choose whether to copy or transcode video and audio.

## Dependencies

Proxynas needs `ffmpeg` and `ffprobe`. On Windows, it tries to download them at startup if they are unavailable. You can also install them on `PATH` or place them in `portable/bin/` next to the app.

To process `.braw` files, download the [Blackmagic RAW SDK](https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows) and import it in Proxynas. The SDK is not included with the app.

## Run from source

With Python and the dependencies in `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
python Proxynas.py
```

The command-line mode can run a backup:

```powershell
python Proxynas.py --cli <source> <destination> [--no-transcode] [--include-braw-originals] [--lang es|en]
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) (in Spanish) to set up the project, run checks, and submit changes.

Proxynas source code is released under the [MIT license](LICENSE). FFmpeg and the Blackmagic RAW SDK are separate products with their own licenses.
