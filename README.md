# Job Hunter AI

Sistema automático de captación de ofertas de empleo para perfiles de entrada en **Data Analytics, BI y People Analytics**. Cada día laborable consulta varias APIs de empleo, filtra las ofertas según un perfil definido, las puntúa de 0 a 100, descarta duplicados y guarda las nuevas en una base de Notion. Todo lo captado, incluido lo descartado y el motivo, queda en un registro CSV pensado para analizarlo en Power BI.

## Arquitectura

```
GitHub Actions (L-V 8:52)
        │
        ▼
 fuentes.py ── Adzuna · Himalayas · JSearch (Google for Jobs) · InfoJobs
        │
        ▼
 reglas.py ── normalización → nivel (sénior/mid fuera) → zona y modalidad → puntuación 0-100
        │
        ▼
 deduplicación ── URL sin parámetros · empresa + puesto normalizados · lista de exclusiones
        │
        ├──► Notion (base Candidaturas): solo ofertas nuevas
        └──► data/capturas.csv: histórico completo para el dashboard
```

| Módulo | Responsabilidad |
|---|---|
| `job_hunter/fuentes.py` | Llama a cada API y unifica el formato. Si una falla, las demás siguen. |
| `job_hunter/reglas.py` | Todo el criterio de perfil. Sin llamadas externas, cubierto por tests. |
| `job_hunter/notion.py` | Lee todas las candidaturas (paginando) y crea las nuevas. |
| `job_hunter/main.py` | Orquesta el proceso y escribe el resumen de cada ejecución. |

## Criterios del perfil

- **Nivel:** se descartan títulos Senior, Lead, Principal, Director, Head of, Jefe/a y las ofertas que la fuente marca como Mid-level o superior. Las que piden 3 o más años en la descripción pasan como `revisar`.
- **Puesto:** el título debe tener un término de datos (data, BI, analytics, reporting…), o ser de analista y pedir SQL, Power BI, Tableau, Python o Looker.
- **Zona:** Alicante y San Vicente del Raspeig en cualquier modalidad; Madrid solo remoto o híbrido (sin modalidad indicada → `revisar`); resto de España solo remoto.
- **Antigüedad:** máximo 30 días desde la publicación.
- **Puntuación (0-100):** +30 puesto objetivo, +15 nivel de entrada, hasta +55 por herramientas del perfil (SQL, Power BI, Python, Tableau, Excel, Pandas, RRHH, marketing), +10 Alicante o +5 remoto, −15 si va a `revisar`.

## Puesta en marcha

### 1. Repositorio
Crea un repositorio **privado** en GitHub y sube esta carpeta. GitHub Actions es gratuito en repositorios privados dentro de un cupo mensual de sobra para una ejecución diaria de un par de minutos.

### 2. Integración de Notion
1. En https://www.notion.so/profile/integrations crea una integración interna llamada `Job Hunter AI` y copia el **token**.
2. Abre la base **Candidaturas** → menú `⋯` → **Conexiones** → añade `Job Hunter AI`.

### 3. Secrets
En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Valor |
|---|---|
| `NOTION_TOKEN` | Token de la integración de Notion |
| `NOTION_DATABASE_ID` | Opcional. Por defecto, la base Candidaturas |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Credenciales de developer.adzuna.com |
| `RAPIDAPI_KEY` | Application Key de RapidAPI (JSearch) |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | App registrada en developer.infojobs.net |
| `EXCLUSIONES_CSV` | Contenido completo de `exclusiones.csv` (ver abajo) |

Las fuentes sin credenciales se omiten con un aviso; el resto sigue funcionando.

### 4. Primera ejecución
**Actions → Job Hunter AI → Run workflow**, primero con *Simulación* marcada: verás en el resumen qué ofertas guardaría sin tocar Notion. Después, sin simulación. Desde ahí se ejecuta solo de lunes a viernes.

## Exclusiones
`exclusiones.csv` (columnas `Empresa,Puesto`) lista las candidaturas que se gestionan fuera de este sistema, para que no vuelvan a entrar. No se sube al repositorio (está en `.gitignore`): su contenido va en el secret `EXCLUSIONES_CSV`. Hay un ejemplo en `exclusiones.ejemplo.csv`.

## Uso local
```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # y rellena las claves
python -m pytest -q         # comprueba las reglas
python -m job_hunter.main --dry-run
```

## Registro `data/capturas.csv`
Una fila por oferta captada en cada ejecución, incluidas las descartadas. Es la fuente del dashboard de Power BI.

| Columna | Contenido |
|---|---|
| `fecha_captura` | Día de la ejecución |
| `canal` | Fuente; en JSearch incluye el portal de origen (`jsearch · LinkedIn`) |
| `empresa`, `puesto`, `ubicacion`, `modalidad` | Datos de la oferta |
| `estado` | `pendiente`, `revisar` o `descartar` |
| `motivo` | Por qué se descartó o va a revisión |
| `puntuacion` | Encaje 0-100 (0 si descartada) |
| `fecha_publicacion` | Según la fuente; si no la da, la de captura |
| `resultado` | `nueva` (guardada en Notion), `repetida` o `descartada` |
| `url_oferta` | Enlace para aplicar |

## Límites conocidos
- **LinkedIn** no ofrece API pública para leer ofertas. Las que llegan vía JSearch salen de Google for Jobs, no de LinkedIn directamente.
- **JSearch (plan gratuito):** 200 peticiones/mes. Se usan 4 por ejecución (~88/mes).
- **InfoJobs:** conector pendiente de validar con credenciales reales.
- El horario de ejecución usa UTC: en invierno corre una hora antes (7:52).
