# Guía práctica: PEST_HP en modelos hidrogeológicos numéricos

Esta guía explica cómo preparar, ejecutar y post-procesar una calibración con **PEST_HP** usando las herramientas de este repo (pyEMU, FloPy, MODFLOW 6 y el entorno pixi). Se acompaña de un ejemplo ejecutable:

- Notebook: [`tutorials/part1_15_pest_hp/freyberg_pest_hp.ipynb`](../tutorials/part1_15_pest_hp/freyberg_pest_hp.ipynb)
- Funciones de apoyo: [`tutorials/part1_15_pest_hp/pest_hp_helpers.py`](../tutorials/part1_15_pest_hp/pest_hp_helpers.py)

El ejemplo usa el modelo Freyberg con pilot points de la parte 1 (`part1_08_pilotpoints_run`, `part1_09_regularization`), así que conviene haber recorrido esos notebooks antes.

> **Importante.** `pixi run get-exes` descarga e instala la suite PEST_HP (versión 18.7) y los verificadores `pestchek`, `tempchek` e `inschek` de PEST 18 (solo Windows), junto con MODFLOW y PEST++. Los comandos de esta guía siguen el manual de PEST_HP 18 (`pest_hp_18.pdf`), que queda instalado en `.pixi\envs\default\share\doc\pest_hp`. Si cambia de versión, compruébelos con el manual de **esa** versión y con `pestchek`.

---

## Índice
1. [¿Qué es PEST_HP y cuándo usarlo?](#1-qué-es-pest_hp-y-cuándo-usarlo)
2. [Cómo funciona: manager, agentes y archivos](#2-cómo-funciona-manager-agentes-y-archivos)
3. [Instalación en Windows junto al entorno del repo](#3-instalación-en-windows-junto-al-entorno-del-repo)
4. [Flujo de trabajo paso a paso](#4-flujo-de-trabajo-paso-a-paso)
5. [Ejecutar PEST_HP desde la terminal (sin Python)](#5-ejecutar-pest_hp-desde-la-terminal-sin-python)
6. [Variables del archivo de control que más importan](#6-variables-del-archivo-de-control-que-más-importan)
7. [Regularización de Tikhonov](#7-regularización-de-tikhonov)
8. [Resultados y post-proceso](#8-resultados-y-post-proceso)
9. [Detener y reiniciar una corrida](#9-detener-y-reiniciar-una-corrida)
10. [Problemas frecuentes](#10-problemas-frecuentes)
11. [Lista de verificación para su propio modelo](#11-lista-de-verificación-para-su-propio-modelo)
12. [Referencias](#12-referencias)

---

## 1. ¿Qué es PEST_HP y cuándo usarlo?

PEST_HP es la versión de PEST de John Doherty (Watermark Numerical Computing) pensada para correr en paralelo en muchos núcleos o máquinas. Calibra con el mismo método **Gauss-Levenberg-Marquardt (GLM)** que PEST y PEST++GLM y lee el mismo archivo de control de PEST (`.pst`, versión 1).

Frente al PEST "clásico" (serie o con BEOPEST/Parallel PEST), PEST_HP:
- calcula en paralelo las derivadas (la Jacobiana) **y** las pruebas de las actualizaciones de parámetros. En cada iteración elige él mismo varias lambdas de Marquardt (nunca menos de tres, según cuántos agentes tenga) y hace además una búsqueda lineal en cada dirección, todo en una sola tanda de corridas en paralelo;
- tolera corridas del modelo que fallan: al probar actualizaciones de parámetros siempre (`LAMFORGIVE` queda activado internamente) y al calcular derivadas si usted pone `DERFORGIVE`. Esto es muy común en modelos no lineales (celdas secas, falta de convergencia);
- asigna cada corrida al agente más rápido disponible, maneja agentes lentos o perdidos y lo registra en `case.rmr` y `case.rme`.

PEST_HP **no** hace corridas en serie: siempre necesita al menos un agente. Según su manual, rinde mejor con **10 agentes o más**; con menos de 10 su desempeño puede bajar.

La suite HP incluye otros programas que usan los mismos agentes: `pest_hp_mkl` (versión de `pest_hp` con la librería Intel MKL, más rápida con muchos parámetros u observaciones), `jactest_hp`, `pcost_hp`, `pwhisp_hp`, `rsi_hp`, `cmaes_hp` y las herramientas de ensembles `ensiprep`/`ensimod`/`postensiunc`. Están descritas en `hp_suite_18.pdf`.

Cuándo elegir cada herramienta del repo:

| Necesidad | Herramienta |
|---|---|
| Calibración determinística por GLM, con regularización, en paralelo | **PEST_HP** o PEST++GLM |
| Usar las utilidades de la suite PEST (SVDAPREP, GENLINPRED, PREDUNC, ...) sobre los mismos archivos | **PEST_HP** / PEST |
| Calibración con ensembles e incertidumbre posterior no lineal | PEST++IES (`part2_06_ies`) |
| Optimización de manejo | PEST++OPT / PEST++MOU |

PEST_HP y PEST++GLM resuelven el mismo problema. Cambian las opciones avanzadas y los archivos de salida: PEST++ escribe CSV, mientras que PEST_HP escribe los archivos de texto y binarios clásicos de PEST.

---

## 2. Cómo funciona: manager, agentes y archivos

```
                ┌──────────────────────────────┐
                │  manager: pest_hp case /h :4004  │   (carpeta master_hp)
                └───────────────┬──────────────┘
           TCP/IP (puerto 4004) │
     ┌─────────────────┬────────┴────────┬─────────────────┐
 agent_hp case       agent_hp case     agent_hp case     ...
 /h localhost:4004   /h localhost:4004 /h PC2:4004
 (worker_0)          (worker_1)        (otra máquina)
```

- **Manager (`pest_hp`)**: lee el `.pst`, decide qué corridas hacer, recibe los resultados y escribe todos los archivos de salida. No corre el modelo.
- **Agentes (`agent_hp`)**: cada uno trabaja en **su propia copia completa** de la carpeta del modelo (modelo, `.tpl`, `.ins`, `.pst`, ejecutables, `forward_run.py`). Escriben los archivos de entrada con los parámetros que manda el manager, corren el modelo y leen las salidas con las instrucciones.
- Los agentes pueden estar en la misma PC (`localhost`) o en otras PCs de la red, y pueden lanzarse antes o después que el manager.
- La versión de `agent_hp` tiene que ser la misma que la de `pest_hp`; si no, el manager se detiene con un mensaje de error.

Archivos de entrada (iguales que para PEST/PEST++):

| Archivo | Para qué sirve |
|---|---|
| `case.pst` | archivo de control (parámetros, observaciones, pesos, opciones) |
| `*.tpl` | plantillas: archivos de entrada del modelo con marcadores donde van los parámetros |
| `*.ins` | instrucciones: cómo leer las salidas del modelo |
| comando del modelo | `python forward_run.py`, `run.bat`, `mf6.exe`, ... (sección `* model command line`) |

---

## 3. Instalación en Windows junto al entorno del repo

### 3.1 Instalar PEST_HP con pixi (recomendado)
Desde la carpeta del repo, en la terminal de VS Code:

```powershell
pixi install
pixi run get-exes      # MODFLOW 6/2005/NWT/USG, MODPATH 7, PEST++, PEST_HP and the PEST checkers
pixi run check-exes    # every executable should show a path inside .pixi
```

`get-exes` corre `etc/get_pest_hp.py`, que descarga dos zips de pesthomepage.org (versiones fijadas): la suite HP (`hp_suite_18.7.zip`, se instalan todos sus programas) y la suite de PEST (`pest18.zip`, se instalan solo `pestchek`, `tempchek` e `inschek`). Deja los `.exe` en la misma carpeta que `mf6.exe` y `pestpp-*.exe` (`.pixi\envs\default\Scripts`). Desde ahí están en el PATH de `pixi run ...`, `pixi shell` y del kernel de Jupyter del entorno, así que en el notebook basta con `PEST_HP_DIR = None`. Los manuales en PDF quedan en `.pixi\envs\default\share\doc\pest_hp`.

Otros usos de la tarea:

| Comando | Para qué |
|---|---|
| `pixi run get-pest-hp` | instalar solo PEST_HP y los verificadores (si ya está la misma versión, no hace nada) |
| `pixi run get-pest-hp --force` | reinstalarlo |
| `pixi run get-pest-hp --pest-all` | instalar **todos** los programas de la suite de PEST (`parrep`, `svdaprep`, `predunc`, `genlinpred`, `jcoblank`, ...), no solo los verificadores |
| `pixi run get-pest-hp --zip C:\Descargas\hp_suite_18.7.zip --pest-zip C:\Descargas\pest18.zip` | instalar desde zips descargados a mano (sin internet, proxy, etc.) |
| `pixi run get-pest-hp --url <url>` / `--pest-url <url>` | probar otra versión de la suite HP / de PEST |

Para cambiar las versiones fijas para todos, edite `PEST_HP_URL` y `PEST_URL` en `etc/get_pest_hp.py`. Los manuales de PEST (`pestman1.pdf`, `pestman2.pdf`) quedan junto a los de PEST_HP.

> PEST_HP y PEST solo se distribuyen para Windows. En Linux/macOS el script los omite sin error.

### 3.2 Alternativa: PEST_HP en otra carpeta
Si prefiere tener PEST_HP fuera del entorno (por ejemplo en `C:\PEST_HP`):
- en el notebook ponga `PEST_HP_DIR = r"C:\PEST_HP"`, y `hp.prep_pest_hp_bins()` copiará los ejecutables a la carpeta plantilla; o
- agregue esa carpeta al PATH de Windows y reinicie VS Code.

Compruébelo con:
```powershell
pixi run python -c "import shutil; print(shutil.which('pest_hp'), shutil.which('agent_hp'))"
```

### 3.3 Otras versiones de MODFLOW
`get-exes` también instala `mf2005`, `mfnwt`, `mfusg` y `mfusg_gsi` (release 29.0 de MODFLOW-ORG/executables) para usarlos con sus propios modelos. Para agregar otros programas de esa release (`zbud6`, `mt3dms`, `mt3dusgs`, `mp6`, `zonbud`, `gridgen`, ...), súmelos a `--subset` en la tarea `get-exes` de `pixi.toml` y a la lista de `check-exes`.

Si su modelo usa alguno de ellos, recuerde copiarlo también a la carpeta plantilla, porque cada agente necesita su copia: `hbd.prep_bins()` solo copia los ejecutables de los tutoriales. Por ejemplo:
```python
import shutil
# copy the MODFLOW-USG executable from the pixi environment into the template folder
shutil.copy2(shutil.which('mfusg'), tmp_d)
```

### 3.4 Que los agentes encuentren Python y MODFLOW
El comando del modelo del ejemplo es `python forward_run.py`. Cada `agent_hp` lo ejecuta, así que **el `python` del entorno pixi tiene que estar en el PATH del agente**:
- Si lanza todo desde Jupyter abierto con `pixi run jupyter` (o desde VS Code con el kernel de `.pixi`), los agentes heredan ese entorno. No hay que hacer nada más.
- Si lanza a mano desde PowerShell, abra antes el entorno con `pixi shell`.
- `mf6.exe` y `mp7.exe` se copian a la carpeta del modelo con `hbd.prep_bins()`, así que no dependen del PATH.

### 3.5 Firewall
La primera vez que corra `pest_hp`/`agent_hp`, Windows Defender puede pedir permiso de red. En la misma PC (`localhost`) funciona aunque lo cancele. Si va a usar agentes en **otras** PCs, permita el acceso en redes privadas.

---

## 4. Flujo de trabajo paso a paso

Este es el flujo que sigue el notebook `freyberg_pest_hp.ipynb`. Todos los pasos son los mismos para un modelo propio.

### Paso 1: Construir la interfaz de PEST
Con lo que usa siempre: plantillas e instrucciones hechas a mano, `pyemu.Pst.from_io_files()`, o `pyemu.utils.PstFrom`. En el ejemplo:

```python
import os, sys, shutil
import pyemu
sys.path.insert(0, "..")
import herebedragons as hbd
import pest_hp_helpers as hp

org_d = os.path.join('..', '..', 'models', 'monthly_model_files_1lyr_newstress')
tmp_d = 'freyberg_mf6'                      # the "template" folder
if os.path.exists(tmp_d):
    shutil.rmtree(tmp_d)
shutil.copytree(org_d, tmp_d)
hbd.prep_bins(tmp_d)                        # copy mf6/mp7 into the template
hbd.prep_pest(tmp_d)                        # base control file, tpl and ins files
hbd.add_ppoints(tmp_d)                      # pilot points + forward_run.py
pst = pyemu.Pst(os.path.join(tmp_d, 'freyberg_pp.pst'))
```

> Si usa `PstFrom`, póngale `longnames=False`. Así ya genera nombres que cumplen los límites de PEST/PEST_HP.

### Paso 2: Revisar la compatibilidad con PEST_HP
PEST_HP tiene límites que PEST++ no tiene:

| Elemento | Límite en PEST / PEST_HP |
|---|---|
| Nombre de parámetro | 12 caracteres |
| Nombre de observación | 20 caracteres |
| Nombre de información previa | 20 caracteres |
| Nombre de grupo (parámetros u observaciones) | 12 caracteres |
| Espacios en nombres | no permitidos |
| Archivo de control | solo versión 1 (pyEMU escribe la versión 2 por defecto cuando hay más de 10 000 parámetros) |
| Opciones `++` de PEST++ | no se usan |
| Grupos de regularización | deben empezar con `regul` |

```python
problems = hp.check_pest_hp_compat(pst)
```

En el ejemplo Freyberg aparecen 58 parámetros con nombres de más de 12 caracteres (`hk_i:12_j:12_zone:1`, el formato que usa pyEMU para los pilot points).

### Paso 3: Corregir los nombres y limpiar el archivo de control
```python
name_map = hp.shorten_par_names(pst, tmp_d)   # renames in the .pst AND in every .tpl
forecasts = pst.pestpp_options['forecasts'].split(',')  # keep them for FOSM later
hp.prepare_pst_for_pest_hp(pst)               # drop the "++" PEST++ options
```
- `shorten_par_names()` reemplaza cada nombre largo por `<grupo>_<número>` (`hk1_0001`) en el control y en las plantillas, sin cambiar el formato de los archivos de entrada. Guarda la tabla `par_name_map.csv` (nombre viejo → nuevo).
- Hágalo **antes** de agregar regularización (la información previa usa los nombres de los parámetros).
- Si sus **observaciones** tienen nombres de más de 20 caracteres, lo más simple es regenerar las instrucciones con nombres más cortos (por ejemplo, `PstFrom(..., longnames=False)`).

### Paso 4: Escribir el `.pst` y verificar con `pestchek`
```python
pst.control_data.noptmax = 0                  # test run first
hp.write_pst_for_pest_hp(pst, os.path.join(tmp_d, 'freyberg_hp.pst'))
hp.prep_pest_hp_bins(tmp_d)                   # copy pest_hp/agent_hp (+pestchek) from the PATH
hp.run_pestchek('freyberg_hp', cwd=tmp_d)
```
Corrija hasta que `pestchek` no informe **errores** (las advertencias conviene leerlas). Si tiene dudas con una plantilla o instrucción, use `tempchek` e `inschek` sobre ese archivo.

### Paso 5: Corrida de prueba (`NOPTMAX = 0`)
```python
hp.start_pest_hp(tmp_d, 'freyberg_hp.pst', num_agents=1, master_dir='master_hp')
pst_test, _, _ = hp.load_results('master_hp', 'freyberg_hp.pst')
print(pst_test.phi, pst_test.phi_components)
```
Con `NOPTMAX = 0` el modelo corre una vez con los valores iniciales. Si falla, el problema está en la interfaz (comando del modelo, plantillas, instrucciones), no en la calibración. Revise `master_hp/freyberg_hp.rec` y la carpeta del agente (`hp.start_pest_hp(..., cleanup=False)` la conserva).

`hp.start_pest_hp()` hace lo que `pyemu.os_utils.start_workers()` hace con PEST++, pero con los comandos de PEST_HP:
1. Copia la carpeta plantilla a `master_hp` y lanza `pest_hp case /h :4004`.
2. Copia la plantilla a `worker_0 ... worker_n` y en cada una lanza `agent_hp case /h localhost:4004`.
3. Espera a que el manager termine y borra las carpetas de los agentes.

> `pyemu.os_utils.start_workers()` no sirve directamente con PEST_HP porque lanza el **mismo** ejecutable como manager y como agente. PEST_HP usa dos ejecutables distintos.
>
> Si su versión de `agent_hp` no acepta el nombre del caso (solo `/h host:puerto`), use `hp.start_pest_hp(..., agent_takes_case=False)`.

### Paso 6: Calibración
```python
pst.control_data.pestmode = 'estimation'
pst.control_data.noptmax = 8
pst.control_data.derforgive = 'derforgive'      # tolerate failed runs while filling the Jacobian
pst.control_data.jacupdate = 999                # Broyden Jacobian updates (0 = none)
hp.write_pst_for_pest_hp(pst, os.path.join(tmp_d, 'freyberg_hp.pst'))

hp.start_pest_hp(tmp_d, 'freyberg_hp.pst', num_agents=10, master_dir='master_hp')
```

No hace falta ajustar `NUMLAM`, `RLAMBDA1`, `RLAMFAC`, `PHIRATSUF` ni `PHIREDLAM`: PEST_HP los ignora y elige las lambdas solo. Conviene dejarlos con valores razonables (los de pyEMU sirven) para que `pestchek` no se queje.

Cuántos agentes usar:
- Para empezar, uno por **núcleo físico** (`psutil.cpu_count(logical=False)`). El manual recomienda 10 o más; si su PC tiene menos núcleos, sume agentes en otras PCs (sección 5.2).
- Cada iteración necesita unas `NPAR_adj` corridas para la Jacobiana más una tanda de pruebas de actualización (aprox. una por agente). Más agentes que parámetros ajustables casi no aceleran el cálculo de la Jacobiana.
- Si el modelo usa mucha RAM o disco, use menos agentes que núcleos.

### Paso 7: Resultados
```python
pst_est, par_est, jco = hp.load_results('master_hp', 'freyberg_hp.pst')
df_phi = hp.read_ofr('master_hp/freyberg_hp.ofr')       # phi per iteration (PEST_HP table)
hbd.plot_1to1(pst_est)                                   # measured vs simulated
```
Ver la [sección 8](#8-resultados-y-post-proceso).

---

## 5. Ejecutar PEST_HP desde la terminal (sin Python)

Útil para corridas largas, para correr en un servidor o para usar varias PCs.

### 5.1 En una sola PC (PowerShell)
```powershell
# 1) environment with python/mf6 on the PATH
pixi shell

# 2) manager, in the master folder
cd tutorials\part1_15_pest_hp\master_hp
Start-Process pest_hp -ArgumentList "freyberg_hp /h :4004"

# 3) agents, each in its own copy of the template folder
cd ..
foreach ($i in 0..5) {
    Copy-Item -Recurse -Force freyberg_mf6 "worker_$i"
    Start-Process -WorkingDirectory "worker_$i" agent_hp -ArgumentList "freyberg_hp /h localhost:4004"
}
```

### 5.2 En varias PCs de la red
1. En la PC del manager: `pest_hp freyberg_hp /h :4004`.
2. Copie la carpeta plantilla completa (modelo, `.tpl`, `.ins`, `.pst`, ejecutables, `forward_run.py`) a cada PC con agentes. Si el comando del modelo usa Python, cada PC necesita un Python con pyemu/flopy (por ejemplo, clonando el repo y con `pixi install`).
3. En cada PC: `agent_hp freyberg_hp /h NOMBRE_O_IP_DEL_MANAGER:4004`.
4. Abra el puerto 4004 (o el que use) en el firewall de la PC del manager.

Los agentes se pueden agregar o quitar durante la corrida. El manager reparte el trabajo entre los que estén conectados y guarda el registro en `case.rmr`.

---

## 6. Variables del archivo de control que más importan

Todas están en `* control data` y pyEMU las expone en `pst.control_data.<nombre>`.

| Variable | Qué controla | Recomendación práctica |
|---|---|---|
| `PESTMODE` | `estimation`, `regularization`, `prediction` | `estimation` con pocos parámetros; `regularization` con muchos |
| `NOPTMAX` | iteraciones máximas (`0` = una corrida; `-1` = solo la Jacobiana) | `0` para probar, `-1` para sensibilidades, 8–30 para calibrar |
| `RLAMBDA1`, `RLAMFAC`, `PHIRATSUF`, `PHIREDLAM`, `NUMLAM` | selección de lambdas en PEST | **PEST_HP los ignora** (elige las lambdas solo); déjelos con valores válidos para `pestchek` |
| `JACUPDATE` | nº de actualizaciones de Broyden de la Jacobiana tras las pruebas de lambda (una segunda tanda de pruebas) | `999` = todas las posibles; `0` u omitido = ninguna. Con muchos agentes suele convenir `0` |
| `LAMFORGIVE` | tolerar corridas fallidas al probar actualizaciones | PEST_HP lo activa siempre internamente |
| `DERFORGIVE` | tolerar corridas fallidas al calcular derivadas | `derforgive` en modelos no lineales |
| `RELPARMAX`, `FACPARMAX` | cambio máximo de parámetros por iteración | bájelos (p. ej. 3–5) si phi oscila |
| `PHIREDSWH` | cuándo pasar a derivadas centrales | por defecto `0.1` |
| `PHIREDSTP`, `NPHISTP`, `NPHINORED`, `RELPARSTP`, `NRELPAR` | criterios de parada | por defecto |
| `RSTFLE` | guardar datos para reiniciar | `restart` |
| `DERINC`, `INCTYP`, `FORCEN` (grupos de parámetros) | incremento para las derivadas | si las derivadas son ruidosas, aumente `DERINC` (p. ej. 0.01–0.05 relativo) |
| `PARTRANS` (parámetros) | `log`, `none`, `fixed`, `tied` | `log` para K, recarga y almacenamiento |

Ejemplo:
```python
cd = pst.control_data
cd.noptmax = 10
cd.relparmax = 5
cd.facparmax = 5
cd.derforgive = 'derforgive'
pst.parameter_groups.loc[:, 'derinc'] = 0.02
```

### 6.1 Variables propias de PEST_HP
PEST_HP acepta variables adicionales que se escriben como `NOMBRE=valor` al final de ciertas líneas de `* control data` (PEST y BEOPEST no las aceptan). pyEMU no las escribe, así que se agregan editando el `.pst` después de `pst.write()`. Algunas útiles:

| Variable | Línea de `* control data` | Qué hace |
|---|---|---|
| `UPTESTMIN=N` / `UPTESTLIM=N` | 6ª (la de `RLAMBDA1 ... NUMLAM [JACUPDATE]`) | mínimo / máximo de pruebas de actualización por iteración. La eficiencia es máxima si `UPTESTMIN` es múltiplo del nº de agentes |
| `RUN_SLOW_FAC`, `RUN_ABANDON_FAC`, `WIN_MRUN_HOURS` | ver manual (sección 7.2) | manejo de corridas lentas o colgadas |
| `JCOWARNTHRESH=1E20`, `JCOZEROTHRESH=1E30` | 8ª (la que empieza con `PHIREDSWH`) | avisar / poner en cero derivadas absurdas (corridas con fallas) |

Ejemplo del manual, con `UPTESTMIN` en la 6ª línea y los umbrales en la 8ª:
```
* control data
restart estimation
     104      14      13       0       6
     1     2 single  point  2   0   0
 10.0  -3.0  0.3  0.03  10 999  uptestmin=15
 10.0  10.0  0.001
 0.1  noaui jcowarnthresh=1.0E10 jcozerothresh=1.0E30
 30  0.005  4  4  0.005  4
 1  1  1
```

---

## 7. Regularización de Tikhonov

Con muchos parámetros (pilot points, zonas, multiplicadores por celda) el problema inverso no tiene solución única. Por eso conviene usar el modo `regularization`:

```python
# rename first (section 4, step 3), then:
pyemu.helpers.zero_order_tikhonov(pst, parbounds=True)          # preferred value
v = pyemu.geostats.ExpVario(contribution=1.0, a=2500.0)
gs = pyemu.geostats.GeoStruct(variograms=v, nugget=0.0)
df_pp = pyemu.pp_utils.pp_tpl_to_dataframe(os.path.join(tmp_d, 'hkpp.dat.tpl'))
cov = gs.covariance_matrix(df_pp.x, df_pp.y, df_pp.parnme)
pyemu.helpers.first_order_pearson_tikhonov(pst, cov, reset=False)  # preferred difference

pst.control_data.pestmode = 'regularization'
pst.reg_data.phimlim = pst.nnz_obs               # target measurement phi
pst.reg_data.phimaccept = 1.1 * pst.reg_data.phimlim
hp.write_pst_for_pest_hp(pst, os.path.join(tmp_d, 'freyberg_hp_reg.pst'))
```

Claves:
- **`PHIMLIM`** es la phi de medición que usted acepta. Un buen punto de partida es el nº de observaciones con peso distinto de cero (si los pesos son la inversa del error de medición). Si `PHIMLIM` es muy bajo, sobreajusta el ruido y los parámetros salen con artefactos. Si es muy alto, el ajuste empeora pero los parámetros quedan más suaves y "creíbles". Pruebe varios valores, como en `part1_09_regularization`.
- `PHIMACCEPT` suele ser un 5–10 % mayor que `PHIMLIM`.
- Los grupos de información previa **deben** empezar con `regul` (pyEMU ya los nombra `regulhk1`, `regulrchpp`, ...).
- Para problemas con cientos o miles de parámetros, la suite PEST incluye **SVD-assist** (utilidad `SVDAPREP`): crea un archivo de control con "superparámetros" que PEST_HP estima mucho más rápido. Consulte el manual de PEST para el flujo completo.

---

## 8. Resultados y post-proceso

Archivos que deja PEST_HP en la carpeta del manager:

| Archivo | Contenido | Cómo leerlo |
|---|---|---|
| `case.rec` | registro completo (phi por iteración, lambdas, parámetros, estadísticos, sensibilidades) | editor de texto |
| `case.par` | parámetros óptimos | `pyemu.pst_utils.read_parfile()`; `pst.parrep('case.par')` |
| `case.rei` / `case.res` | residuos de la mejor corrida (con `NOPTMAX = 0` solo se escribe `case.res`) | `hp.load_results()` o `pst.set_res('case.rei')`, luego `pst.phi`, `pst.res`, `hbd.plot_1to1(pst)` |
| `case.jco` | Jacobiana (binaria) | `pyemu.Jco.from_binary()` |
| `case.sen` / `case.seo` | sensibilidades compuestas de parámetros / observaciones | editor de texto |
| `case.ofr` | tabla de phi (total y por grupo; en `regularization`, phi de medición y de regularización) por iteración. Propio de PEST_HP | `hp.read_ofr()` |
| `case.rmr` | registro de la gestión de corridas en paralelo | editor de texto (agentes caídos, tiempos) |
| `case.rme` | eficiencia de cada agente (corridas, fallas, tiempos). Propio de PEST_HP | editor de texto u hoja de cálculo |
| `case.rst`, `pest###.dap`, `pest###.dao`, ... | datos para reiniciar y cola de corridas en paralelo (pueden ser grandes) | no se editan; bórrelos al terminar si no va a reiniciar |

### 8.1 Ver el modelo calibrado
```python
pst = pyemu.Pst('master_hp/freyberg_hp.pst')
pst.parrep('master_hp/freyberg_hp.par')            # use the estimated values
pst.write_input_files(pst_path='master_hp')        # write the model input files
pyemu.os_utils.run('python forward_run.py', cwd='master_hp')
# then load with flopy and plot as usual
```

### 8.2 Análisis lineal (FOSM) con la Jacobiana
PEST_HP no escribe los `*.usum.csv` de PEST++, pero con `case.jco` pyEMU hace lo mismo que en `part1_10_intro_to_fosm` y `part2_05_fosm_and_dataworth`:

```python
jco_file = 'master_hp/freyberg_hp.jco'
pst = pyemu.Pst('master_hp/freyberg_hp.pst')

# parameter identifiability
ev = pyemu.ErrVar(jco=jco_file, pst=pst)
ident = ev.get_identifiability_dataframe(singular_value=20)

# prior/posterior forecast uncertainty (prior from parameter bounds, noise from weights)
sc = pyemu.Schur(jco=jco_file, pst=pst, forecasts=forecasts)
sc.get_forecast_summary()
sc.get_par_group_contribution()
```
Use la Jacobiana de una corrida en modo `estimation` o una con `NOPTMAX = -1`, para que la información previa no se cuente como datos.

Para el análisis de valor de los datos, también puede usar las utilidades clásicas de la suite PEST sobre el mismo `.jco` (`PREDUNC`, `GENLINPRED`, `IDENTPAR`, ...).

---

## 9. Detener y reiniciar una corrida

**Detener:** `Ctrl+C` en la ventana de PEST_HP, o desde otra terminal abierta en la carpeta del manager:
- `pstop`: detiene el manager de inmediato;
- `pstopst`: detiene el manager después de escribir el estado actual en el `.rec`.

Los agentes terminan al acabar la corrida que tengan en curso.

**Reiniciar:** con `RSTFLE = restart` (es el valor por defecto de pyEMU), una corrida detenida (o cortada por un apagón) se retoma con el switch **`/s`**, que va **antes** de `/h`:

```
pest_hp case /s /h :4004
```

Si se cortó mientras llenaba la Jacobiana, PEST_HP retoma exactamente donde iba y solo hace las corridas que faltaban. Si se cortó probando actualizaciones, repite esa tanda. Los agentes se relanzan con el comando de siempre (sin `/s`). Con el helper:
```python
hp.start_pest_hp(tmp_d, 'freyberg_hp.pst', num_agents=10, master_dir='master_hp', restart_flag='/s')
```
Con `restart_flag`, la carpeta `master_hp` **no** se borra.

> Los archivos de reinicio de PEST/BEOPEST y de PEST_HP no son compatibles: una corrida empezada con uno no se puede terminar con el otro.

Otros switches útiles:

| Switch | Qué hace |
|---|---|
| `/i` | usa una Jacobiana (`.jco`) ya calculada en la primera iteración. PEST_HP pregunta el nombre del archivo, así que láncelo desde una terminal y no desde el helper |
| `/hpstart` | lee un "hp starter file" (`case.hp`) creado antes con PEST serie (`pest case /hpstart`, una sola corrida del modelo). Así PEST_HP empieza directamente a llenar la Jacobiana en paralelo |
| `/f` | modo de corridas en lote a partir de archivos de parámetros (ver manual, sección 4.3) |

Truco útil: con `NOPTMAX = -1` PEST_HP calcula solo la Jacobiana y termina. Esa Jacobiana sirve para sensibilidades, identificabilidad y FOSM antes de calibrar.

---

## 10. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `pestchek`: nombre de parámetro demasiado largo | nombres de pyEMU/PstFrom (`hk_i:12_j:12_zone:1`) | `hp.shorten_par_names()` o `PstFrom(longnames=False)` |
| `pestchek`: error en la línea `++...` o versión del archivo | opciones de PEST++ o control versión 2 | `hp.prepare_pst_for_pest_hp()` y `hp.write_pst_for_pest_hp()` |
| El agente no conecta / queda esperando | puerto ocupado, firewall, nombre de host | cambie `port`, permita el acceso en el firewall, use `localhost` en la misma PC |
| `'python' no se reconoce como comando` en los agentes | el agente no ve el Python de pixi | lance desde `pixi shell` o `pixi run jupyter`; o use en el `.pst` la ruta completa (`sys.executable`) |
| El modelo no encuentra `mf6` en el agente | ejecutables no copiados | `hbd.prep_bins(tmp_d)` antes de lanzar |
| Error de lectura de una observación (instrucción) | la salida del modelo cambió de formato o el modelo falló | corra el modelo a mano en `worker_0` (`cleanup=False`) y revise con `inschek` |
| phi no baja o sube y baja | derivadas ruidosas, parámetros sin sensibilidad, pesos mal balanceados | aumente `DERINC`, fije o agrupe parámetros insensibles (vea `case.sen`), revise `pst.phi_components` |
| Parámetros pegados a los límites | sobreajuste o error conceptual del modelo | regularización, revisar la conceptualización y los límites |
| Muchas corridas fallidas | no convergencia o celdas secas | `DERFORGIVE`, bajar `RELPARMAX`/`FACPARMAX`, revisar el solver (IMS); vea en `case.rme` qué agente falla |
| Un agente solo tiene fallas (aviso al inicio de cada iteración) | falta o está dañado un archivo en la carpeta de ese agente | revise esa carpeta (`cleanup=False`) |
| El manager se detiene por versión de agente | `agent_hp` y `pest_hp` de versiones distintas | use ambos de la misma suite (`pixi run get-pest-hp --force`) |
| `pixi run get-exes` falla en la descarga de PEST_HP o PEST | sin internet, proxy o cambió la dirección | descargue los zips a mano y use `pixi run get-pest-hp --zip <hp_suite zip> --pest-zip <pest zip>` |
| `hp.read_ofr()` devuelve vacío | el `.ofr` aún no se escribió o tiene otro formato | abra `case.ofr`; como alternativa use `hp.read_rec_phi()` |

---

## 11. Lista de verificación para su propio modelo

- [ ] El modelo corre solo desde su carpeta (sin rutas absolutas) con un único comando (`forward_run.py` o `.bat`).
- [ ] Las plantillas (`.tpl`) e instrucciones (`.ins`) pasan `tempchek`/`inschek`.
- [ ] `hp.check_pest_hp_compat(pst)` sin problemas (nombres cortos, sin `++`).
- [ ] Parámetros con transformación `log` donde corresponda, con límites razonables.
- [ ] Pesos de las observaciones ≈ 1/(desviación estándar del error) y grupos balanceados (`pst.phi_components`).
- [ ] Pronósticos incluidos como observaciones con **peso cero** (para FOSM).
- [ ] `pestchek case` sin errores.
- [ ] Corrida de prueba con `NOPTMAX = 0` y 1 agente: phi coherente con lo esperado.
- [ ] (Opcional) `NOPTMAX = -1` para la Jacobiana: identificabilidad y sensibilidades antes de calibrar.
- [ ] Calibración en `estimation` (pocos parámetros) → `regularization` (muchos parámetros) con `PHIMLIM` razonado.
- [ ] Post-proceso: ajuste (1 a 1, residuos en el tiempo), mapas de parámetros, incertidumbre de los pronósticos (FOSM).

---

## 12. Referencias

- PEST y PEST_HP (descargas y manuales): https://pesthomepage.org
- Manuales instalados por `pixi run get-exes`: `.pixi\envs\default\share\doc\pest_hp\pest_hp_18.pdf` y `hp_suite_18.pdf`.
- Doherty, J. *PEST: Model-Independent Parameter Estimation, User Manual*, Parts I y II. Watermark Numerical Computing.
- Doherty, J. *PEST_HP: PEST for Highly Parallelized Computing Environments* (versión 18). Watermark Numerical Computing.
- Tutoriales GMDSI sin programación (incluyen ejemplos con PEST_HP): https://gmdsi.org/education/tutorials/
- Notebooks de este repo relacionados: `part1_02_pest_setup`, `part1_08_pilotpoints_run`, `part1_09_regularization`, `part1_10_intro_to_fosm`, `part1_11_local_and_global_sensitivity`, `part2_01_pstfrom_pest_setup`.
