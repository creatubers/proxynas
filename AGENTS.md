# Regla de distribución

Nunca incluyas ni publiques archivos del SDK propietario de Blackmagic en builds, ZIPs, artefactos o releases de Proxynas. Antes de dar por listo cualquier ejecutable, comprueba el contenido completo de `dist/Proxynas/`. Si aparece una DLL del SDK o `portable/sdk/`, detén el build y la publicación. El usuario debe obtener e importar el SDK por su cuenta.
