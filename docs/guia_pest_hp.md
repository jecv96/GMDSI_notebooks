# Guía práctica: PEST_HP en modelos hidrogeológicos numéricos

Esta guía explica cómo preparar, ejecutar y post-procesar una calibración con **PEST_HP** usando las herramientas de este repo (pyEMU, FloPy, MODFLOW 6 y el entorno pixi). Se acompaña de un ejemplo ejecutable:

- Notebook: [`tutorials/part1_15_pest_hp/freyberg_pest_hp.ipynb`](../tutorials/part1_15_pest_hp/freyberg_pest_hp.ipynb)
- Funciones de apoyo: [`tutorials/part1_15_pest_hp/pest_hp_helpers.py`](../tutorials/part1_15_pest_hp/pest_hp_helpers.py)

El ejemplo usa el modelo Freyberg con pilot points de la parte 1 (`part1_08_pilotpoints_run`, `part1_09_regularization`), así que conviene haber recorrido esos notebooks antes.

> **Importante.** El repo no incluye PEST_HP ni lo instala con pixi. Los comandos y switches de esta guía son los de uso habitual de PEST_HP, pero compruébelos siempre con el manual de **su** versión (viene en la descarga) y con `pestchek`.

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
9. [Reiniciar una corrida](#9-reiniciar-una-corrida)
10. [Problemas frecuentes](#10-problemas-frecuentes)
11. [Lista de verificación para su propio modelo](#11-lista-de-verificación-para-su-propio-modelo)
12. [Referencias](#12-referencias)

---

## 1. ¿Qué es PEST_HP y cuándo usarlo?

PEST_HP es la versión de PEST de John Doherty (Watermark Numerical Computing) pensada para correr en paralelo en muchos núcleos o máquinas. Calibra con el mismo método **Gauss-Levenberg-Marquardt (GLM)** que PEST y PEST++GLM y lee el mismo archivo de control de PEST (`.pst`, versión 1).

Frente al PEST "clásico" (serie o con BEOPEST/Parallel PEST), PEST_HP:
- calcula en paralelo las derivadas (la Jacobiana) **y** las pruebas de lambda de cada iteración;
- tolera corridas del modelo que fallan (`LAMFORGIVE`, `DERFORGIVE`), algo muy común en modelos no lineales (celdas secas, falta de convergencia);
- reparte mejor las corridas entre agentes de distinta velocidad (lo registra en `case.rmr`).

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
- Los agentes pueden estar en la misma PC (`localhost`) o en otras PCs de la red.

Archivos de entrada (iguales que para PEST/PEST++):

| Archivo | Para qué sirve |
|---|---|
| `case.pst` | archivo de control (parámetros, observaciones, pesos, opciones) |
| `*.tpl` | plantillas: archivos de entrada del modelo con marcadores donde van los parámetros |
| `*.ins` | instrucciones: cómo leer las salidas del modelo |
| comando del modelo | `python forward_run.py`, `run.bat`, `mf6.exe`, ... (sección `* model command line`) |

---

## 3. Instalación en Windows junto al entorno del repo

### 3.1 Requisitos previos (lo que ya tiene)
- El repo clonado y el entorno instalado: `pixi install` y `pixi run get-exes` (ver `README.md`).
- Puede comprobarlo con `pixi run check-exes`.

### 3.2 Descargar PEST_HP
1. Descargue PEST_HP desde https://pesthomepage.org (sección de descargas). Descargue también la **suite de PEST** si aún no la tiene: trae `pestchek`, `tempchek`, `inschek` y otras utilidades útiles.
2. Descomprima en una carpeta **sin espacios**, por ejemplo `C:\PEST_HP`. Debería tener al menos `pest_hp.exe` y `agent_hp.exe`, además del manual en PDF.

### 3.3 Hacer visibles los ejecutables
Elija **una** de estas opciones:

- **A. Indicar la carpeta en el notebook** (la más simple): en el notebook ponga `PEST_HP_DIR = r"C:\PEST_HP"`. El helper `hp.prep_pest_hp_bins()` copia los ejecutables a la carpeta plantilla.
- **B. Agregarla al PATH de Windows**: *Configuración → Sistema → Acerca de → Configuración avanzada del sistema → Variables de entorno → Path → Nuevo → `C:\PEST_HP`*. Reinicie VS Code después.
- **C. Solo para la sesión de PowerShell**:
  ```powershell
  $env:PATH = "C:\PEST_HP;" + $env:PATH
  ```

Compruébelo desde la terminal de VS Code:
```powershell
where.exe pest_hp
where.exe agent_hp
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
hp.prep_pest_hp_bins(tmp_d, exe_dir=r"C:\PEST_HP")   # copy pest_hp/agent_hp (+pestchek)
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
pst.control_data.numlam = 6                     # lambdas tested in parallel
pst.control_data.lamforgive = 'lamforgive'      # tolerate failed runs (lambda testing)
pst.control_data.derforgive = 'derforgive'      # tolerate failed runs (derivatives)
pst.control_data.jacupdate = 999                # Broyden Jacobian update
hp.write_pst_for_pest_hp(pst, os.path.join(tmp_d, 'freyberg_hp.pst'))

hp.start_pest_hp(tmp_d, 'freyberg_hp.pst', num_agents=8, master_dir='master_hp')
```

Cuántos agentes usar:
- Para empezar, uno por **núcleo físico** (`psutil.cpu_count(logical=False)`).
- Cada iteración necesita unas `NPAR_adj` corridas para la Jacobiana más `NUMLAM` para las lambdas. Más agentes que parámetros ajustables no aceleran nada.
- Si el modelo usa mucha RAM o disco, use menos agentes que núcleos.

### Paso 7: Resultados
```python
pst_est, par_est, jco = hp.load_results('master_hp', 'freyberg_hp.pst')
df_phi = hp.read_rec_phi('master_hp/freyberg_hp.rec')   # phi per iteration
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
| `RLAMBDA1`, `RLAMFAC` | lambda inicial y factor de cambio | por defecto (`20`, `-3`) suele ir bien |
| `NUMLAM` | lambdas probadas por iteración (en paralelo en PEST_HP) | 5–10 y no más que el nº de agentes |
| `JACUPDATE` | actualización de Broyden de la Jacobiana | `999` para aprovechar las corridas de lambda |
| `LAMFORGIVE` / `DERFORGIVE` | seguir aunque fallen corridas del modelo | actívelos en modelos no lineales |
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
cd.numlam = 6
cd.relparmax = 5
cd.facparmax = 5
cd.lamforgive = 'lamforgive'
cd.derforgive = 'derforgive'
pst.parameter_groups.loc[:, 'derinc'] = 0.02
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
| `case.rec` | registro completo (phi por iteración, lambdas, parámetros, estadísticos, sensibilidades) | editor de texto; `hp.read_rec_phi()` para la historia de phi |
| `case.par` | parámetros óptimos | `pyemu.pst_utils.read_parfile()`; `pst.parrep('case.par')` |
| `case.rei` | residuos de la mejor corrida | `pst.set_res('case.rei')`, luego `pst.phi`, `pst.res`, `hbd.plot_1to1(pst)` |
| `case.jco` | Jacobiana (binaria) | `pyemu.Jco.from_binary()` |
| `case.sen` / `case.seo` | sensibilidades compuestas de parámetros / observaciones | editor de texto |
| `case.rmr` | registro de la gestión de corridas en paralelo | editor de texto (agentes caídos, tiempos) |
| `case.rst`, `case.jac`, ... | datos para reiniciar | no se editan |

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

## 9. Reiniciar una corrida

Con `RSTFLE = restart` (es el valor por defecto de pyEMU), PEST_HP guarda lo necesario para reiniciar en la carpeta del manager:

| Comando | Reinicia... |
|---|---|
| `pest_hp case /r /h :4004` | desde el comienzo de la última iteración guardada |
| `pest_hp case /j /h :4004` | usando la última Jacobiana completa (ahorra recalcularla) |

Después vuelva a lanzar los agentes. Con el helper:
```python
hp.start_pest_hp(tmp_d, 'freyberg_hp.pst', num_agents=8, master_dir='master_hp', restart_flag='/j')
```
Con `restart_flag`, la carpeta `master_hp` **no** se borra. El manual de PEST_HP describe otros switches de reinicio.

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
| Muchas corridas fallidas | no convergencia o celdas secas | `LAMFORGIVE`/`DERFORGIVE`, bajar `RELPARMAX`/`FACPARMAX`, revisar el solver (IMS) |
| `hp.read_rec_phi()` devuelve vacío | el texto del `.rec` difiere en su versión | abra el `.rec` y ajuste los patrones del helper |

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
- Doherty, J. *PEST: Model-Independent Parameter Estimation, User Manual*, Parts I y II. Watermark Numerical Computing.
- Doherty, J. *PEST_HP: PEST for Highly Parallelized Computing Environments*. Watermark Numerical Computing.
- Tutoriales GMDSI sin programación (incluyen ejemplos con PEST_HP): https://gmdsi.org/education/tutorials/
- Notebooks de este repo relacionados: `part1_02_pest_setup`, `part1_08_pilotpoints_run`, `part1_09_regularization`, `part1_10_intro_to_fosm`, `part1_11_local_and_global_sensitivity`, `part2_01_pstfrom_pest_setup`.
