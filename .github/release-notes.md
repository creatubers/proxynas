Windows 64-bit build (portable, no installer). Unzip it and run `Proxynas.exe`.

FFmpeg is downloaded into the app folder on first launch. The Blackmagic RAW
SDK is not downloaded (Blackmagic does not allow redistributing it) and is only
needed for `.braw` files. Jump to **Install and troubleshooting** below.

---

## Changelog

### v0.1.12

- Spanish and English UI and messages. On first launch, the app follows the
  operating system's language and light/dark mode; manual choices are saved.
- Image backups copy stills unchanged, without requiring an image converter.
- Backups reject a destination inside the source folder to prevent recursive
  copying.
- Release builds exclude the locally imported Blackmagic RAW SDK. The build
  stops if SDK files appear in the package; `.braw` support still requires the
  user to import the SDK separately.

### v0.1.11

- **Stills are copied instead of converted.** `.tiff`, `.rw2`, `.cr2` and
  `.arw` now reach the backup byte for byte, with their original extension.
  This also keeps stills available in `Todo` and `Audio + imágenes` without
  requiring an image converter.

### v0.1.10

- **The backup buttons no longer vanish on a small window.** `Iniciar backup`,
  `Cancelar` and `Salir` sat inside the Backup card, so a window shorter than
  the card pushed them out of view and you had to maximize to start a backup.
  They now live in their own bar under that card and stay put; the card
  content is what gives up the space.
- The version is shown next to the app name, in the header and in the window
  title bar.
- Footer credit: `Hecho con ♥ por Creatubers`, with links to Creatubers and to
  the project's donation page.

### v0.1.9

- **FFmpeg is now really downloaded on first launch.** The download was only
  wired into a code path that the packaged `Proxynas.exe` never runs, so a
  machine without FFmpeg got a "could not download" dialog, a wall of encoder
  errors and no second attempt. The download now starts from the single entry
  point, in the background, and the panel reports it.
- The "FFmpeg is missing" dialog is short and offers to open the download
  page. The proxies panel says `falta FFmpeg` instead of dumping the full path
  and the WinError that produced it.
- The FFmpeg download gives up after a while instead of hanging forever.
- The install notes below were rewritten: the old antivirus advice did not
  work.

### v0.1.8

- Decoder rebuilt against the Blackmagic RAW SDK 6.0 interfaces. SDK 6.0 had
  added an audio buffer in the middle of the vtable, which made `braw_decode`
  die with `3221225477` (access violation).
- Restoring the window from the notification area no longer flashes white.

### v0.1.7

- Every proxy codec now writes the same bit depth (10-bit), so an H.265 and an
  H.264 proxy of the same clip match.
- Proxies panel layout tidied.

### v0.1.6

- The proxies panel picks the codec (H.265 / H.264) and the acceleration
  (GPU / CPU); hardware is only offered when an encoder for that codec was
  validated on this machine.
- Encoder detection runs each candidate against a real clip instead of
  trusting `ffmpeg -encoders`, which lists encoders the machine cannot use.
- `ffmpeg` lookup shared with the proxy generator, so the GUI and the worker
  no longer disagree about where FFmpeg is.

### v0.1.5

- Windows build trimmed to lower Defender and SmartScreen false positives: no
  UPX compression, and a version resource embedded in the exe.

### v0.1.4

- `braw_decode.exe` is now installed where the app actually looks for it.

### v0.1.3

- A missing FFmpeg is no longer reported as a missing BRAW SDK.
- The BRAW SDK importer understands Blackmagic's MSI-based zip.

### v0.1.2

- The scan that looks for `.braw` files is depth-capped, so pointing the app at
  a whole archive is cheap.

### v0.1.1

- The BRAW SDK prompt only appears for folders that really contain `.braw`.

### v0.1.0

- First public release: proxies from Blackmagic RAW, video, RAW stills and
  audio, plus a portable AV1 backup.
- Child `ffmpeg` / `ffprobe` / `braw_decode` processes no longer flash console
  windows.

---

## Install and troubleshooting

### Running it

Unzip the whole folder (do not run `Proxynas.exe` from inside the zip) and
start `Proxynas.exe`. No installer needed, no admin rights.

### FFmpeg

On Windows, Proxynas downloads a current FFmpeg build into `portable\bin\`
inside the app folder the first time it runs (about 170 MB). If your network
blocks GitHub it cannot, and the app says so and offers to open the download
page: download the zip by hand and copy `ffmpeg.exe` and `ffprobe.exe` from
the `bin\` folder inside it into `portable\bin\`, next to `Proxynas.exe`.

Nothing is downloaded if you already have `ffmpeg` and `ffprobe` on `PATH`.

### Blackmagic RAW

`.braw` support is not bundled and is not downloaded: Blackmagic does not allow
redistributing the SDK. Everything except `.braw` works without it. When you
point Proxynas at a folder that contains `.braw`, it offers to open

  https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows

and to import the zip you downloaded, with the **"Importar SDK BRAW (zip)"**
button. The decoder itself (`braw_decode.exe`) is already in the build, but it
is compiled against the SDK 6.0 interfaces, so import a current SDK (6.0 or
newer) or it will refuse to load an older one.

### Antivirus, SmartScreen and Chrome

`Proxynas.exe` is unsigned, so any of these three can get in the way. All three
are false positives. Only a code-signing certificate removes them for good.

**1. Windows Defender deletes `Proxynas.exe` while you unzip it.** The usual
verdict is a `Wacatac` heuristic, something like `Trojan:Win32/Wacatac.H!ml`:
Defender's machine-learning model firing on an unsigned PyInstaller executable.
The build already drops UPX and embeds a version resource, which lowers the
odds but does not remove them.

Fix it by excluding the folder **before** you extract, because once Defender has
quarantined the exe, allowing the detection does not bring it back:

    Windows Security -> Virus & threat protection -> Virus & threat protection
    settings -> Manage settings -> Exclusions -> Add or remove exclusions ->
    Add -> Folder -> the folder where you are going to extract

    Seguridad de Windows -> Protección contra amenazas y virus ->
    Configuración de Protección contra amenazas y virus -> Administrar la
    configuración -> Exclusiones -> Agregar o quitar exclusiones -> Agregar ->
    Carpeta -> la carpeta donde vas a descomprimir

Then extract, and run it from there. Two notes: an exclusion covers Defender's
real-time scan only, so a scheduled scan can still flag the file; and if you
run a third-party antivirus, the pages above are not the ones you will see --
add the same folder exclusion in that product, and do not switch it off.

**2. SmartScreen: "Windows protected your PC".** Click *More info* -> *Run
anyway*. You can also drop the flag that triggers it before running it:
right-click the zip -> Properties -> tick *Unblock* (Spanish: *Desbloquear*) ->
OK, or from PowerShell:

    Unblock-File .\Proxynas-win64.zip

If you already extracted before unblocking, clear the mark on the extracted
tree instead:

    Get-ChildItem .\Proxynas -Recurse | Unblock-File

**3. Chrome blocks the download.** Chrome refuses files it cannot vouch for
("dangerous" or an "uncommon file") and it may delete the file before you can
react. Open `chrome://downloads` and use the blocked item's ⋮ menu to keep it,
but that option is not always offered, so the dependable route is to skip Safe
Browsing entirely:

    curl.exe -L -o Proxynas-win64.zip https://github.com/creatubers/proxynas/releases/latest/download/Proxynas-win64.zip

Use `curl.exe`, with the extension. Windows PowerShell 5.1 aliases `curl` to
`Invoke-WebRequest`, so the same command written as `curl` stops with
`No se encuentra ningún parámetro que coincida con el nombre del parámetro 'L'`
and downloads nothing -- which is why the antivirus notes that used to be on
this page did not work.

If Defender keeps flagging a file you are sure about, report the false positive
to Microsoft: <https://www.microsoft.com/en-us/wdsi/filesubmission>
