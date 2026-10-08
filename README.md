# MiQuemi

Una página en español para pegar un enlace y guardar **video MP4** o **audio MP3**. Botones grandes, sin anuncios, diseñada para el celular.

**Sin laptop ni servidor en casa:** GitHub guarda el código y puede servir la interfaz; Render Free ejecuta `yt-dlp`. El Dockerfile instala Python, FFmpeg y Deno automáticamente.

## Publicarla gratis

Necesitas cuentas GitHub y Render. Estimación: **10–20 minutos**, incluido el primer build. No necesitas instalar Python ni Docker en tu computadora.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FDanielLeonBaro%2FMiQuemi)

1. **Con el código subido a [DanielLeonBaro/MiQuemi](https://github.com/DanielLeonBaro/MiQuemi), pulsa Deploy to Render**, inicia sesión y confirma el despliegue. `render.yaml` crea un único servicio con `plan: free`. Elige el workspace gratuito Hobby y conserva el plan Free. Para evitar cobros por excedentes, no añadas método de pago. Confirma las condiciones de tu cuenta en Billing.
2. **Abre la URL HTTPS del servicio**, como `https://miquemi-xxxx.onrender.com`. Ya sirve la página completa. Pega un enlace y prepara tu descarga: **nunca pide código de acceso**.

Puedes usar esa URL directamente. Para que la interfaz quede en **GitHub Pages**, completa dos pasos adicionales:

3. **En `web/config.js`, escribe la URL de Render**: `window.MIQUEMI_API = "https://miquemi-xxxx.onrender.com"`. En Render, define `ALLOWED_ORIGINS=https://danielleonbaro.github.io` y guarda los cambios para redesplegar.
4. **Sube el cambio y activa Settings → Pages → Source → GitHub Actions.** En **Actions → Comprobar y publicar → Run workflow**, selecciona `main` y ejecuta el workflow. Publica solo `web/`; las comprobaciones se ejecutan también al subir cambios. Después abre la URL publicada desde el celular.

Con dominio personalizado, usa su origen HTTPS en `ALLOWED_ORIGINS`. Puedes permitir varios orígenes separados por comas. Se conservan las comprobaciones de origen y CORS para conectar la página con Render.

Alternativa sin Blueprint: **New → Web Service → tu repositorio → Language: Docker → Instance Type: Free**. Define `ALLOWED_ORIGINS` si usas GitHub Pages. Docker configura puerto y arranque. El health check es `/api/health`.

La página permite preparar y consultar descargas directamente. Los enlaces de archivos tienen un identificador aleatorio: quien tenga uno puede descargarlo durante su vigencia.

[Docker en Render](https://render.com/docs/docker), [Blueprint](https://render.com/docs/blueprint-spec), [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

## Lo que verá tu mamá

Pegar enlace → Video o Solo audio → Calidad → **Ver duración y peso** (opcional) → **Preparar descarga** → **Guardar en mi celular**.

**Mejor calidad disponible** siempre viene seleccionada. Si cambias entre Video y Solo audio, vuelve a esa opción. Puedes elegir una calidad menor para reducir el tamaño:

- **Video:** mejor calidad disponible, preferir 1080p, preferir 720p o preferir 480p. Las preferencias eligen la mejor calidad disponible sin superar esa resolución cuando existe. Si el sitio solo ofrece resoluciones superiores, se usa la menor disponible. No se reescala ni se recodifica el video.
- **Audio:** mejor calidad disponible o MP3 a 192, 128 o 96 kbps. Las opciones de MP3 eligen la mejor fuente y la convierten con la tasa elegida.

**Ver duración y peso** muestra la duración, el peso del video MP4 y el peso estimado del MP3 antes de descargar. El botón consulta los datos de `yt-dlp` en el servidor —Render cuando está publicado— sin descargar el archivo ni ocupar un lugar de descarga. Por eso puede tardar aproximadamente un minuto si Render está dormido; no se puede consultar de forma general desde GitHub Pages sin enviar el enlace al servidor.

El video corresponde a la calidad elegida cuando seleccionas Video; en Solo audio muestra el video de mejor calidad. El MP3 corresponde a la tasa elegida en Solo audio. Para MP3 en mejor calidad, **Hasta ≈** usa una referencia de 320 kbps; el archivo puede pesar menos. **≈** indica una estimación y **No informado** aparece cuando el sitio no publica datos suficientes. El peso final puede variar, incluso por la conversión. Los avisos de duración, tamaño o transmisión en vivo son informativos; la descarga conserva las comprobaciones finales del servidor. Cambiar el enlace, formato o calidad elimina la consulta anterior y el botón para guardar el archivo anterior.

Los límites aparecen en la página. Cuando hay tres archivos listos, el botón muestra cuánto falta para liberar un lugar. Si un archivo es demasiado grande, puedes elegir menor calidad, audio o un video más corto; el audio también debe cumplir los límites.

En iPhone, si se abre una vista previa: **Compartir → Guardar en Archivos**. En Android normalmente aparece en **Descargas**. Los archivos no se agregan automáticamente a la galería. Puedes añadir la página a la pantalla de inicio desde el navegador.

## Límites de esta app

- **Una descarga a la vez.** Si otra persona prepara un archivo, espera a que termine.
- **Mejor calidad disponible de forma predeterminada.** Con esa opción, Video usa el mejor formato de yt-dlp y el mejor audio adicional cuando hace falta; conserva los códecs originales dentro de MP4, sin reducir la resolución. Audio elige la mejor fuente y se convierte a MP3 con calidad VBR máxima (`0`), salvo que ya sea MP3. MP3 es un formato con pérdida; no mejora la calidad original. Algunos celulares antiguos pueden no reproducir los códecs de video elegidos.
- **Hasta 20 minutos y 100 MB por archivo.** Si la calidad elegida supera los límites, la app avisa y no prepara ese archivo; puedes elegir menor calidad, Solo audio o un video más corto. No se baja automáticamente la calidad ni se descargan transmisiones en vivo.
- **Tres archivos listos como máximo.** Los intentos fallidos no ocupan lugares. Cada enlace dura **15 minutos** y después se elimina. La página consulta el cupo del servidor y muestra una cuenta regresiva al llenarse.
- **10 minutos de preparación y 200 MB temporales por trabajo.** Se vigila el tamaño durante la descarga. El archivo final debe caber en 100 MB. FFprobe comprueba también la duración final, aunque el sitio no la informe.
- Enlaces públicos de **YouTube, Instagram, Facebook, TikTok, Vimeo, Dailymotion y Pinterest**. La compatibilidad depende del sitio y de `yt-dlp`. No se importan cuentas ni cookies. Videos privados, bloqueados o que piden iniciar sesión pueden fallar; las IP de servidores también pueden ser rechazadas.

## Límites de Render Free

Verificados el **8 de octubre de 2026**; confirma los valores de tu cuenta en Billing.

| Recurso | Límite |
|---|---|
| Transferencia del workspace Hobby | **5 GB/mes**, compartidos con otros servicios |
| Servidor Free | **512 MB RAM, 0.1 CPU** |
| Horas gratuitas | **750 horas/mes por workspace**, compartidas |
| Inactividad | Duerme tras **15 minutos**; despierta en aproximadamente **1 minuto** |
| Builds en Hobby | **500 minutos/mes**, para construir/desplegar, no para convertir audio |
| Almacenamiento | Temporal: se pierde al dormir, reiniciar o redesplegar |

**5 GB equivalen aproximadamente a 50 archivos de 100 MB**, antes del tráfico adicional. El MP3 normalmente pesa menos. Volver a descargar un archivo consume más transferencia.

Sin método de pago, al agotar transferencia u horas gratuitas se suspenden los servicios hasta el próximo mes. Al agotar minutos de build no puedes construir de nuevo ese mes. Con método de pago pueden cobrarse excedentes. Render también puede suspender tráfico iniciado por el servicio que considere excesivo: no publica un límite numérico para ese caso.

**El contador de la app mide archivos temporales; no mide el saldo mensual de Render.** El consumo del workspace no se comunica automáticamente a esta página. Consulta **Render → Billing → Monthly Included Usage**. Cuando Render suspende el servidor, GitHub Pages puede seguir mostrando la interfaz y sus límites, pero no prepara nuevos archivos. No hay garantía de descargas gratuitas ilimitadas ni de que todos los sitios acepten la IP de Render.

[Transferencia](https://render.com/docs/outbound-bandwidth), [servidor](https://render.com/docs/compute-plans), [horas y suspensión](https://render.com/docs/free), [builds](https://render.com/docs/build-pipeline).

Cloudflare Pages también puede servir `web/`, pero no ejecuta el motor nativo de `yt-dlp` y FFmpeg. [Cloudflare Containers requiere Workers Paid](https://developers.cloudflare.com/containers/platform/pricing/). La configuración incluida usa Render Free para el motor.

## Comprobar el despliegue y actualizar

Abre `https://TU-SERVICIO.onrender.com/api/health`: debe responder `{"ok": true}`. Después prueba un video público corto en MP4 y MP3. **Esta prueba desde Render es necesaria**: una descarga local no confirma que la IP de Render funcione con cada sitio.

Si el servicio reinicia, prepara los archivos otra vez: los enlaces anteriores dejan de funcionar. Para actualizar `yt-dlp`, usa **Render → Manual Deploy → Clear build cache & deploy**. Docker instala la versión disponible. El servidor no registra enlaces.

**Si ya publicaste la versión con clave:** sube estos cambios y ejecuta **Render → Manual Deploy → Deploy latest commit** y **GitHub → Actions → Comprobar y publicar → Run workflow**. Debes actualizar tanto el servidor como la página. Si `ACCESS_CODE` sigue en Render, esta versión lo ignora.

## Desarrollo local

**Para localhost necesitas Python 3.10 o posterior con soporte `venv`/pip** (en Ubuntu, paquete `python3-venv`).

- **Windows:** doble clic en `iniciar-local.cmd`. Detecta `py -3` o `python`; si falta Python, muestra cómo instalarlo. No necesitas PowerShell.
- **Linux:** desde la carpeta del proyecto ejecuta `sh ./iniciar-local.sh`. También puedes darle permiso una vez con `chmod +x iniciar-local.sh` y ejecutar `./iniciar-local.sh`.

Ambos inician en `http://127.0.0.1:8000` y abren el navegador. Conserva la terminal abierta. Si el navegador no abre automáticamente, usa esa URL. Para detener el servidor, pulsa **Ctrl+C**. Si el puerto 8000 está ocupado, cierra el otro servidor y vuelve a iniciar.

También puedes iniciarlo manualmente:

```bash
python3 server.py
```

Abre `http://127.0.0.1:8000`. Puedes descargar e instalar herramientas directamente, sin clave. La página comprueba las herramientas y abre **Herramientas de esta computadora** si falta alguna. Pulsa **Verificar herramientas**, **Instalar yt-dlp** o **Instalar FFmpeg** según corresponda. La instalación no inicia una descarga de video al terminar.

Usa las herramientas ya instaladas en esa computadora cuando estén disponibles. Si falta algo, lo guarda en **`.tools/` dentro del proyecto**, sin `sudo` ni cambios globales: entorno Python privado para `yt-dlp`, binarios FFmpeg/ffprobe y Deno cuando hace falta para YouTube. Instalar desde la página requiere conexión a internet.

El instalador automático de FFmpeg admite **Linux x86_64 y Windows x64**. En macOS instala FFmpeg con Homebrew y vuelve a verificar; Python ya debe estar instalado. El instalador de YouTube admite Deno en Linux, Windows y macOS compatibles. Se usan fuentes oficiales: [FFmpeg de yt-dlp](https://github.com/yt-dlp/FFmpeg-Builds), [dependencias yt-dlp](https://github.com/yt-dlp/yt-dlp#dependencies), [Deno](https://docs.deno.com/runtime/getting_started/installation/).

**Instalar desde la página solo funciona en localhost**, sin clave: se comprueban dirección del servidor, conexión local, Host, Origin y ausencia de cabeceras de proxy. En Render y detrás de un túnel está desactivado. Los botones no aceptan comandos ni paquetes arbitrarios. Durante una instalación no se inicia otra descarga.

En localhost no aplica la transferencia mensual de Render; siguen aplicando los límites por archivo y de temporales.

HTML, CSS y JavaScript sin compilación; Python estándar más `yt-dlp` para las descargas. Si tienes Docker:

```bash
docker build -t miquemi .
docker run --rm -p 127.0.0.1:8000:10000 miquemi
```

Comprobaciones sin descargas externas:

```bash
python3 -m unittest -q test_server
node --check web/app.js
```

Los checks verifican uso sin clave, orígenes, validación de calidad, descargas mediante procesos de prueba, límites, cupo, errores, borrado y protección del instalador local. Con yt-dlp instalado en ese Python también comprueban la mejor calidad y las preferencias 1080p, 720p y 480p en videos horizontales y verticales; esas pruebas se omiten si falta el módulo. GitHub Actions instala las dependencias y ejecuta todas. Los botones instalaron yt-dlp y FFmpeg/ffprobe en `.tools/`; con esas herramientas se comprobaron MP4 y MP3 reales de YouTube y las tasas MP3 de 192, 128 y 96 kbps. El build Docker y el funcionamiento desde Render requieren el primer despliegue en tu cuenta.
