# Proxynas

**ES** | [EN](README.md)

Proxynas crea proxies de vídeo y hace copias de seguridad de carpetas con material audiovisual. La versión distribuida para Windows es portable: se descomprime y se ejecuta, sin instalador.

## Descargar y usar

1. Descarga el ZIP de la [última versión](https://github.com/creatubers/proxynas/releases/latest), donde también está el historial de cambios.
2. Extrae la carpeta completa y abre `Proxynas.exe`.
3. Selecciona la carpeta de origen. Para el backup, elige también una carpeta de destino fuera del origen.

La interfaz está en español e inglés. Si no has elegido idioma o modo claro/oscuro en la aplicación, utiliza los ajustes del sistema al arrancar.

## Requisitos

- **Windows 10 22H2 o Windows 11, de 64 bits Intel/AMD (x64).** Se recomienda Windows 11. La [versión de FFmpeg que se descarga](https://github.com/BtbN/FFmpeg-Builds#ffmpeg-static-auto-builds) fija Windows 10 22H2 como mínimo compatible; Proxynas no se ha validado por separado en Windows 10. No hay una versión nativa ARM64 ni de 32 bits.
- **No necesitas instalar Python** para la versión portable. Para ejecutar desde el código fuente, utiliza Python 3.12 (la versión con la que se genera la release de GitHub) y `requirements.txt`.
- **Una carpeta de la aplicación con permiso de escritura**, espacio suficiente para las herramientas descargadas y los proxies/backups, e internet para la descarga inicial de FFmpeg. Puedes aportar FFmpeg manualmente para trabajar sin conexión; consulta [Dependencias](#dependencias).
- **GPU opcional.** Puedes codificar con CPU; la aceleración requiere una GPU NVIDIA, AMD o Intel compatible y su controlador. La aplicación prueba qué codificadores funcionan en tu equipo.
- **SDK de Blackmagic RAW solo para `.braw`.** Debes obtenerlo e importarlo por tu cuenta; Proxynas no lo incluye ni lo descarga.

## Si Microsoft Defender bloquea Proxynas

Instrucciones contrastadas con la documentación actual de Microsoft el **30 de septiembre de 2026**, para **Windows 11 26H2** ([información de versiones de Microsoft](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information)). El ejecutable portable no está firmado. Si Defender lo detecta, comprueba que el ZIP procede de [las releases de este repositorio](https://github.com/creatubers/proxynas/releases); una detección no permite asegurar que un archivo sea seguro.

### Excluir la carpeta de Proxynas antes de descomprimir

1. Crea una carpeta exclusiva para la aplicación, por ejemplo `C:\Apps\Proxynas`.
2. Abre **Inicio**, busca **Seguridad de Windows** y ábrela.
3. Entra en **Protección contra virus y amenazas**. En **Configuración de protección contra virus y amenazas**, pulsa **Administrar la configuración**.
4. Baja hasta **Exclusiones** y pulsa **Agregar o quitar exclusiones**. Acepta la solicitud de permisos de administrador si aparece.
5. Pulsa **Agregar una exclusión → Carpeta** y selecciona `C:\Apps\Proxynas`.
6. Descomprime el ZIP completo de forma que `Proxynas.exe` y su carpeta `_internal` queden dentro de la carpeta excluida. Después abre `Proxynas.exe`.

Limita la exclusión a esa carpeta de Proxynas: todos los archivos que contenga quedan fuera del análisis en tiempo real de Defender. Mantén activada la protección en tiempo real. Los análisis programados y otros antivirus pueden seguir examinando la carpeta. Si tu organización administra estos ajustes o utilizas otro antivirus, la excepción depende de su administrador o de ese producto.

### Si Defender ya puso en cuarentena o eliminó el ejecutable

1. Abre **Seguridad de Windows → Protección contra virus y amenazas → Historial de protección**.
2. Despliega la detección y comprueba en **Elementos afectados** que corresponde al `Proxynas.exe` descargado.
3. Si indica **Amenaza en cuarentena**, utiliza **Acciones → Restaurar** solo si confías en esta descarga. Microsoft advierte que la restauración puede generar otra detección; si ocurre, revisa esa entrada y elige **Permitir en el dispositivo** para el mismo archivo si corresponde.
4. Si indica **Amenaza bloqueada** y el archivo ya se eliminó, **Acciones → Permitir** se aplica a una futura detección; no recupera el archivo borrado. Añade primero la exclusión de carpeta anterior, vuelve a descargar el ZIP oficial si hace falta y descomprímelo de nuevo.

Si aparece **Windows protegió su PC**, se trata de [SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/), una comprobación de reputación distinta. Excluir una carpeta en Defender no desactiva SmartScreen; una organización también puede impedir que se omitan sus avisos.

Fuentes consultadas el 30 de septiembre de 2026: documentación de Microsoft sobre [exclusiones de Defender](https://support.microsoft.com/es-es/windows/security/threat-malware-protection/virus-and-threat-protection-in-the-windows-security-app) e [historial de protección](https://support.microsoft.com/es-es/windows/security/windows-security/protection-history-in-the-windows-security-app).

## Qué hace

- **Proxies:** crea archivos H.264 o H.265 en una carpeta `Proxy` junto a los vídeos originales. El códec y el uso de CPU o GPU se eligen en la aplicación.
- **Backup:** procesa la carpeta de origen en el destino elegido. Puedes elegir `Todo`, `Solo vídeo`, `Audio + imágenes` u `Otros`, y decidir si el vídeo y el audio se copian o se transcodifican.

## Dependencias

Proxynas necesita `ffmpeg` y `ffprobe`. En Windows intenta descargarlos al arrancar si no están disponibles. También puedes instalarlos en `PATH` o colocarlos en `portable/bin/` junto a la aplicación.

Para procesar archivos `.braw` necesitas descargar el [SDK de Blackmagic RAW](https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows) e importarlo desde Proxynas. El SDK no se incluye en la descarga de la aplicación.

## Ejecutar desde el código fuente

Con Python y las dependencias de `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
python Proxynas.py
```

El modo de línea de comandos permite ejecutar un backup:

```powershell
python Proxynas.py --cli <origen> <destino> [--no-transcode] [--include-braw-originals] [--lang es|en]
```

## Contribuir

Se aceptan contribuciones mediante issues y pull requests. Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para preparar el entorno, ejecutar las comprobaciones y enviar cambios.

El código de Proxynas se distribuye bajo la licencia [MIT](LICENSE). FFmpeg y el SDK de Blackmagic RAW son productos separados con sus propias licencias.
