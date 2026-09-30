<p align="center">
  <img src="proxynas.png" alt="Proxynas icon" width="180">
</p>

<h1 align="center">Proxynas</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/OS-Windows%2010%20%2F%2011-0078D4" alt="OS: Windows 10 / 11"></a>
  <a href="#run-from-source"><img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&amp;logoColor=white" alt="Python: 3.12"></a>
  <a href="https://github.com/creatubers/proxynas/releases/latest"><img src="https://img.shields.io/github/v/release/creatubers/proxynas?color=8A2BE2" alt="Latest release"></a>
  <a href="https://github.com/creatubers/proxynas/releases"><img src="https://img.shields.io/github/downloads/creatubers/proxynas/total?color=F59E0B" alt="Total downloads"></a>
</p>

**EN** | [ES](README.es.md)

Proxynas creates video proxies and backs up folders of audiovisual media. The Windows release is portable: extract it and run it, with no installer.

## Download and use

1. Download the ZIP from the [latest release](https://github.com/creatubers/proxynas/releases/latest), which also includes the changelog.
2. Extract the entire folder and open `Proxynas.exe`.
3. Select a source folder. For backups, also choose a destination outside the source folder.

The interface is available in English and Spanish. Until you choose a language or light/dark mode in the app, it follows your system settings at startup.

## Requirements

- **Windows 10 22H2 or Windows 11, 64-bit Intel/AMD (x64).** Windows 11 is recommended. The downloaded [FFmpeg build](https://github.com/BtbN/FFmpeg-Builds#ffmpeg-static-auto-builds) sets Windows 10 22H2 as its minimum supported version; Proxynas has not been separately validated on Windows 10. There is no native ARM64 or 32-bit release.
- **No Python installation required** for the portable release. To run from source, use Python 3.12 (the version used to build the GitHub release) and `requirements.txt`.
- **A writable app folder**, enough disk space for the downloaded tools and your proxies/backups, and internet access for the initial FFmpeg download. You can provide FFmpeg manually for offline use; see [Dependencies](#dependencies).
- **GPU optional.** CPU encoding is available; GPU encoding requires a compatible NVIDIA, AMD or Intel GPU and its driver. The app tests which encoders work on your machine.
- **Blackmagic RAW SDK only for `.braw`.** Obtain and import it yourself; it is not bundled or downloaded by Proxynas.

## If Microsoft Defender blocks Proxynas

Instructions checked against Microsoft's current documentation on **30 September 2026**, for **Windows 11 26H2** ([Microsoft release information](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information)). The portable executable is unsigned. If Defender flags it, check that your ZIP came from [this repository's releases](https://github.com/creatubers/proxynas/releases); a detection alone does not establish that a file is safe.

### Exclude the Proxynas folder before extracting

1. Create a dedicated folder, for example `C:\Apps\Proxynas`.
2. Open **Start**, search for **Windows Security**, and open it.
3. Select **Virus & threat protection**. Under **Virus & threat protection settings**, select **Manage settings**.
4. Scroll to **Exclusions** and select **Add or remove exclusions**. Approve the administrator prompt if shown.
5. Select **Add an exclusion → Folder**, then choose `C:\Apps\Proxynas`.
6. Extract the entire ZIP so that `Proxynas.exe` and its `_internal` folder are inside that excluded folder, then run `Proxynas.exe`.

Limit the exclusion to the dedicated Proxynas folder: everything inside it is excluded from Defender's real-time scanning. Keep real-time protection enabled. Scheduled scans and other antivirus products can still scan the folder. If your organization manages these settings or another antivirus is active, its administrator or that product must handle the exception.

### If Defender already quarantined or removed the executable

1. Open **Windows Security → Virus & threat protection → Protection history**.
2. Expand the detection and check **Affected items** to confirm it refers to your downloaded `Proxynas.exe`.
3. For **Threat quarantined**, use **Actions → Restore** only if you trust this download. Microsoft notes that restoring can trigger another detection; if it does, review that entry and choose **Allow on device** for the same file if appropriate.
4. For **Threat blocked** with the file already removed, **Actions → Allow** applies to a future detection; it does not restore the deleted file. Add the folder exclusion above, then download the official ZIP again if needed and extract it again.

If Windows instead displays **Windows protected your PC**, that is [SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/), a separate reputation check. A Defender exclusion does not disable SmartScreen; an organization can also prevent bypassing its warnings.

Sources consulted on 30 September 2026: Microsoft's [Defender exclusions documentation](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/virus-and-threat-protection-in-the-windows-security-app) and [Protection history documentation](https://support.microsoft.com/en-us/windows/security/windows-security/protection-history-in-the-windows-security-app).

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
