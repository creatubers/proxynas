# Proxynas

Proxynas crea proxies de vídeo y hace copias de seguridad de carpetas con material audiovisual. La versión distribuida para Windows es portable: se descomprime y se ejecuta, sin instalador.

## Descargar y usar

1. Descarga el ZIP de la [última versión](https://github.com/creatubers/proxynas/releases/latest), donde también está el historial de cambios.
2. Extrae la carpeta completa y abre `Proxynas.exe`.
3. Selecciona la carpeta de origen. Para el backup, elige también una carpeta de destino fuera del origen.

La interfaz está en español e inglés. Si no has elegido idioma o modo claro/oscuro en la aplicación, utiliza los ajustes del sistema al arrancar.

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

El código de Proxynas se distribuye bajo la licencia [MIT](LICENSE). FFmpeg y el SDK de Blackmagic RAW son productos separados con sus propias licencias.
