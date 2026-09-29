# Proxynas

Proxynas crea proxies de vídeo y hace copias de seguridad de carpetas con material audiovisual. La versión distribuida para Windows es portable: se descomprime y se ejecuta, sin instalador.

## Descargar y usar

1. Descarga el ZIP de la [última versión](https://github.com/creatubers/proxynas/releases/latest).
2. Extrae la carpeta completa y abre `Proxynas.exe`.
3. Selecciona la carpeta de origen. Para el backup, elige también una carpeta de destino fuera del origen.

La interfaz está en español e inglés. Si no has elegido idioma o modo claro/oscuro en la aplicación, utiliza los ajustes del sistema al arrancar.

## Qué hace

- **Proxies:** crea archivos H.264 o H.265 en una carpeta `Proxy` junto a los vídeos originales. El códec y el uso de CPU o GPU se eligen en la aplicación.
- **Backup:** copia o transcodifica vídeo y audio según las opciones elegidas. Las imágenes `.tiff`, `.rw2`, `.cr2` y `.arw` se copian sin convertirlas ni modificar su contenido.
- **BRAW:** para procesar archivos `.braw` necesitas importar por separado el SDK de Blackmagic RAW. Proxynas muestra la opción de importación cuando hace falta.

## Dependencias

Proxynas necesita `ffmpeg` y `ffprobe`. En Windows intenta descargarlos al arrancar si no están disponibles. También puedes instalarlos en `PATH` o colocarlos en `portable/bin/` junto a la aplicación.

El SDK propietario de Blackmagic RAW **no está incluido** en el repositorio ni en el ZIP de la release. Si trabajas con `.braw`, descárgalo desde [Blackmagic Design](https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows) e importa el ZIP desde la aplicación. El decodificador `braw_decode.exe` incluido en la versión Windows es parte de Proxynas, no del SDK.

## Ejecutar desde el código fuente

Con Python 3.12 y las dependencias de `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
python Proxynas.py
```

El modo de línea de comandos permite ejecutar un backup:

```powershell
python Proxynas.py --cli <origen> <destino> [--no-transcode] [--include-braw-originals] [--lang es|en]
```

Para crear el paquete de Windows, ejecuta `./build_proxynas.ps1`. El build no empaqueta el directorio `portable/` local y se detiene si encuentra archivos del SDK en el resultado.

## Estado de la distribución

Los ejecutables de Windows no están firmados digitalmente. Windows o el navegador pueden mostrar avisos o bloquear una descarga; la firma digital y la reputación del archivo son asuntos pendientes. Consulta el [changelog y las descargas](https://github.com/creatubers/proxynas/releases) para cada versión.

El código de Proxynas se distribuye bajo la licencia [MIT](LICENSE). FFmpeg y el SDK de Blackmagic RAW son productos separados con sus propias licencias.
