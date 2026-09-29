# Contribuir a Proxynas

Gracias por querer mejorar Proxynas. Las contribuciones son bienvenidas mediante **issues** y **pull requests**. Puedes escribir en español o en inglés.

## Antes de empezar

- Para errores o propuestas grandes, abre primero un issue explicando el problema o la idea.
- Para cambios pequeños y claramente acotados (correcciones, documentación, tests, etc.), puedes abrir directamente un pull request.
- No incluyas binarios, SDKs propietarios, credenciales, material audiovisual con derechos ni archivos generados por la aplicación.

## Preparar el entorno

Necesitas Python y las dependencias del proyecto:

```powershell
git clone https://github.com/creatubers/proxynas.git
cd proxynas
python -m pip install -r requirements.txt
python Proxynas.py
```

Proxynas utiliza `ffmpeg` y `ffprobe`. Puedes tenerlos instalados en `PATH` o dejar que la aplicación gestione FFmpeg en Windows.

El soporte de Blackmagic RAW requiere el SDK oficial de Blackmagic Design. El SDK no forma parte de este repositorio y no debe incluirse en los pull requests.

## Flujo recomendado

1. Haz un fork del repositorio.
2. Crea una rama desde `main`:
   ```bash
   git checkout -b fix/descripcion-corta
   ```
3. Haz cambios pequeños y centrados en una sola finalidad.
4. Ejecuta las comprobaciones indicadas abajo.
5. Haz push a tu fork y abre un pull request contra `creatubers/proxynas:main`.

## Comprobaciones antes de enviar un PR

Ejecuta al menos:

```powershell
python -m compileall -q .
python test_backup_paths.py
python test_image_backup.py
python test_localization.py
```

Si tu cambio afecta a proxies, transcodificación, aceleración por GPU o BRAW, indica además en el PR:

- versión de Windows;
- GPU y driver, si aplica;
- versión de FFmpeg;
- códec y encoder probados;
- si has probado CPU, NVIDIA/NVENC, AMD/AMF o Intel/QSV;
- cualquier muestra o caso especial necesario para reproducir el problema, sin subir material con derechos al repositorio.

## Pull requests

Un buen PR debe:

- explicar qué problema resuelve;
- describir brevemente el enfoque usado;
- indicar cómo se ha probado;
- evitar cambios no relacionados;
- mantener el comportamiento existente salvo que el cambio esté justificado;
- actualizar documentación o tests cuando corresponda.

Los checks automáticos de GitHub deben pasar antes de integrar un cambio. El mantenedor puede pedir modificaciones antes de aceptar el PR.

## Estilo

No hay todavía un formateador obligatorio. Intenta respetar el estilo del código existente, utilizar nombres claros y evitar refactors masivos mezclados con correcciones funcionales.

## Licencia

Al enviar una contribución aceptas que tu código se distribuya bajo la licencia [MIT](LICENSE) del proyecto.
