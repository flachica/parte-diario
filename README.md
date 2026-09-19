# parte-diario

CLI para llevar un diario profesional / parte de horas en texto plano (pensado para un vault de Obsidian, aunque no depende de Obsidian) sin tener que editar los ficheros a mano: inicia y cierra trabajos, registra interrupciones y notas, y respeta el formato de los ficheros diarios `YYYY-MM-DD.md`.

## Formato que gestiona

Cada día es un fichero `YYYY-MM-DD.md` con bloques separados por líneas en blanco:

```
Nombre de la tarea
08:15 - 08:52
* una nota sobre la tarea

[Otra tarea con URL](https://ejemplo.com/tarea/123)
09:10 -
```

- Una tarea puede tener nombre solo, o nombre + URL (`[nombre](url)`).
- Puede tener varios rangos de horas si se retoma más adelante (todos dentro del mismo bloque).
- Solo puede haber, en todo momento, **un único** rango sin cerrar (sin hora de fin).
- Puede haber ajustes en minutos sin hora asociada (`+15`, `-10`), y notas sueltas o dentro de una tarea.

## Instalación

```bash
git clone <url-de-este-repositorio>
cd parte-diario
pipx install --editable .
```

Esto deja disponible el comando `parte` en cualquier ruta.

## Configuración del vault

La primera vez, indica dónde están tus ficheros diarios:

```bash
parte config set-vault "/ruta/a/tu/Diario Profesional"
parte config show
```

Queda guardado en `~/.config/parte-diario/config.json`, así no hace falta repetirlo en cada comando. También se puede forzar puntualmente con la variable de entorno `DIARIO_VAULT` (tiene prioridad sobre el fichero de configuración). Si no se configura nada, se usa por defecto `~/Diario Profesional`.

## Uso

```bash
parte start "Biomag"                                   # inicia un trabajo sin URL
parte start "Biomag" --url "https://ejemplo.com/tarea"  # inicia un trabajo con URL
parte stop                                              # cierra el trabajo abierto sin abrir otro
parte status                                            # muestra qué hay abierto y desde cuándo
parte note "Hay que sincronizar la base de datos"       # nota dentro del trabajo abierto
parte note "Idea suelta" --loose                        # nota suelta, no ligada a ningún trabajo
parte show                                              # vuelca el diario de hoy
parte show --fecha 2026-09-10                           # vuelca el diario de otro día

parte interrupt "Llamada de un cliente" 15              # atiendes algo 15 min sin parar el cronómetro:
                                                         # resta 15 min a la tarea abierta (sigue abierta) y
                                                         # se los suma a "Llamada de un cliente" (+15)
parte log "Tarea suelta" 15                             # anota una tarea con solo minutos, sin horas (+15)
parte log "Corrección" 30 --resta                       # igual, pero en negativo (-30), sin tocar la tarea abierta
```

## Reglas que aplica

- **Un único trabajo abierto a la vez**: `start` cierra automáticamente el que estuviera abierto (con la hora actual) antes de abrir el nuevo.
- **Reanudar tarea**: si en el día ya existe un bloque con ese mismo nombre, `start` añade un nuevo rango de horas a ese bloque en vez de crear uno duplicado.
- **Nombre + URL opcional**: si se dio URL la primera vez que se creó el bloque, esa cabecera `[nombre](url)` no se toca en reanudaciones posteriores aunque no se repita `--url`.
- **Notas**: `parte note` sin `--loose` se añade al final del bloque del trabajo abierto (si no hay ninguno abierto, cae automáticamente a nota suelta). Con `--loose` siempre crea un bloque nuevo al final del día, sin hora asociada.
- **Interrupciones (`parte interrupt`)**: para cuando atiendes algo y no da tiempo a cerrar/abrir tareas en el momento. No cierra la tarea abierta ni cambia el estado: solo añade `-N` al bloque de la tarea abierta y `+N` al bloque de la tarea interruptora (creándolo si no existe).
- **Minutos sueltos (`parte log`)**: para tareas que no tienen ni hora de inicio ni de fin, solo minutos invertidos. No toca la tarea abierta.
- El fichero del día es siempre `<vault>/YYYY-MM-DD.md`, en la raíz del vault. El script no reorganiza ni mueve ficheros a subcarpetas de archivo mensual; solo los lee si `parte show --fecha` apunta a uno de ellos.

## Estado

El trabajo abierto se guarda en `~/.local/state/parte-diario/estado.json` (tarea, url, fichero, hora de inicio). Si se borra ese fichero, `parte` deja de saber qué había abierto, pero el diario en sí no se toca.

## Qué NO hace (a propósito)

- No reordena ni reescribe bloques existentes; solo añade líneas nuevas al final del bloque que corresponda o del fichero.
- No calcula el parte de horas final; solo deja el diario bien formado para rellenarlo después.
