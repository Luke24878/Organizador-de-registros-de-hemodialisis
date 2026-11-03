"""Clasifica registros de hemodiálisis por el campo ``ID Máquina``.

El programa admite tanto un PDF por paciente como reportes que contienen varios
registros. Cada página que contiene ``ID Máquina`` inicia un registro; las
páginas siguientes se incluyen en ese mismo registro hasta encontrar el
siguiente inicio.

Por seguridad, el modo predeterminado es una simulación: no crea ni mueve
archivos. Use ``--ejecutar`` después de revisar el resultado. Los originales
se conservan al crear registros separados; ``--mover-originales`` sólo mueve
PDFs que contienen un único registro y nunca mueve reportes combinados.

También puede unir los PDFs ya separados en un único archivo, ordenando las
carpetas ``Maquina_###`` de menor a mayor o de mayor a menor.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter


# En el formato recibido, el valor del ID está debajo de la etiqueta, cerca de
# x=511, y=582. Se conserva un margen para tolerar pequeñas variaciones.
ZONA_ID_MAQUINA = (485, 585, 565, 600)  # x_min, x_max, y_min, y_max
PATRON_ID = re.compile(r"^\d{1,4}$")
CARPETA_ORIGEN_PREDETERMINADA = Path.home() / "OneDrive" / "Documentos"
CARPETA_DESTINO_PREDETERMINADA = Path.home() / "Downloads" / "Docs-organizados"


@dataclass(frozen=True)
class Registro:
    """Grupo de páginas perteneciente a una sesión de hemodiálisis."""

    maquina: str | None
    paginas: tuple[int, ...]


def normalizar(texto: str) -> str:
    """Quita acentos para comparar rótulos de PDF de forma tolerante."""
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    ).upper()


def analizar_pagina_registro(pagina) -> tuple[bool, str | None]:
    """Devuelve si la página inicia un registro y su ID, si está disponible.

    La extracción normal de texto no conserva una relación fiable entre la
    etiqueta y su valor. Por ello se consulta la ubicación del texto, que es
    estable en las hojas de registro proporcionadas. El segundo patrón cubre
    PDFs futuros que sí exporten etiqueta y valor juntos.
    """
    candidatos: list[str] = []
    x_min, x_max, y_min, y_max = ZONA_ID_MAQUINA

    def recopilar(texto, _cm, tm, _fuente, _tamano):
        valor = texto.strip()
        if not valor:
            return
        x, y = tm[4], tm[5]
        if x_min <= x <= x_max and y_min <= y <= y_max:
            valor = re.sub(r"\s+", "", valor)
            if PATRON_ID.fullmatch(valor):
                candidatos.append(valor)

    texto = pagina.extract_text(visitor_text=recopilar) or ""
    texto_normalizado = normalizar(texto)
    es_inicio = "ID MAQUINA" in texto_normalizado or "ID M QUINA" in texto_normalizado
    if not es_inicio:
        return False, None
    if candidatos:
        # Conserva ceros a la izquierda: 047 es distinto visualmente de 47.
        return True, candidatos[0].zfill(3)

    # Respaldo para diseños donde el valor aparezca junto a la etiqueta.
    coincidencia = re.search(r"ID\s*MAQUINA\s*[:#-]?\s*(\d{1,4})", texto_normalizado)
    return True, coincidencia.group(1).zfill(3) if coincidencia else None


def extraer_id_maquina(pagina) -> str | None:
    """Extrae el ID de una página de inicio (función pública de conveniencia)."""
    _es_inicio, maquina = analizar_pagina_registro(pagina)
    return maquina


def separar_registros(reader: PdfReader) -> list[Registro]:
    """Divide un PDF en registros delimitados por sus páginas de inicio."""
    inicios = [
        (indice, maquina)
        for indice, pagina in enumerate(reader.pages)
        for es_inicio, maquina in [analizar_pagina_registro(pagina)]
        if es_inicio
    ]
    if not inicios:
        # Nunca se descartan páginas si el formato no coincide con el esperado.
        return [Registro(None, tuple(range(len(reader.pages))))]

    registros: list[Registro] = []
    for posicion, (inicio, maquina) in enumerate(inicios):
        fin = inicios[posicion + 1][0] if posicion + 1 < len(inicios) else len(reader.pages)
        registros.append(Registro(maquina, tuple(range(inicio, fin))))
    return registros


def nombre_disponible(destino: Path, nombre_base: str) -> Path:
    """Evita sobrescribir expedientes con nombres iguales."""
    candidato = destino / f"{nombre_base}.pdf"
    consecutivo = 2
    while candidato.exists():
        candidato = destino / f"{nombre_base}_{consecutivo}.pdf"
        consecutivo += 1
    return candidato


def escribir_registro(reader: PdfReader, registro: Registro, salida: Path) -> None:
    """Escribe sólo las páginas del registro y comprueba el resultado."""
    writer = PdfWriter()
    for indice in registro.paginas:
        writer.add_page(reader.pages[indice])
    with salida.open("wb") as archivo:
        writer.write(archivo)

    # Validación mínima: el archivo debe reabrirse y conservar todas las páginas.
    comprobacion = PdfReader(salida)
    if len(comprobacion.pages) != len(registro.paginas):
        salida.unlink(missing_ok=True)
        raise RuntimeError(f"La verificación de {salida.name} no conservó todas las páginas.")


def procesar_pdf(pdf: Path, destino: Path) -> tuple[int, int]:
    """Separa un único PDF y devuelve ``(registros_creados, sin_id)``.

    Esta función permite que una interfaz gráfica procese sólo el documento
    elegido por la persona usuaria, sin recorrer otros expedientes de la misma
    carpeta.
    """
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise ValueError(f"No se encontró un PDF válido: {pdf}")

    reader = PdfReader(pdf)
    registros = separar_registros(reader)
    pendientes = 0
    for numero, registro in enumerate(registros, start=1):
        carpeta = destino / (f"Maquina_{registro.maquina}" if registro.maquina else "REVISAR_SIN_ID")
        sufijo = "" if len(registros) == 1 else f"_registro_{numero:03d}"
        carpeta.mkdir(parents=True, exist_ok=True)
        salida = nombre_disponible(carpeta, f"{pdf.stem}{sufijo}")
        escribir_registro(reader, registro, salida)
        if registro.maquina is None:
            pendientes += 1
    return len(registros), pendientes


def iterar_pdfs(origen: Path, destino: Path) -> Iterator[Path]:
    """Recorre PDFs, excluyendo la salida si ésta está dentro del origen."""
    destino_resuelto = destino.resolve()
    for ruta in origen.rglob("*.pdf"):
        if destino_resuelto not in ruta.resolve().parents:
            yield ruta


def carpetas_maquina(carpeta_organizada: Path, descendente: bool) -> list[tuple[int, Path]]:
    """Obtiene las carpetas ``Maquina_###`` ordenadas por su valor numérico."""
    encontradas: list[tuple[int, Path]] = []
    for carpeta in carpeta_organizada.iterdir():
        coincidencia = re.fullmatch(r"Maquina_(\d+)", carpeta.name, re.IGNORECASE)
        if carpeta.is_dir() and coincidencia:
            encontradas.append((int(coincidencia.group(1)), carpeta))
    return sorted(encontradas, key=lambda elemento: elemento[0], reverse=descendente)


def unir_pdfs_por_maquina(carpeta_organizada: Path, descendente: bool, ejecutar: bool) -> tuple[int, int, Path | None]:
    """Une los PDFs ordenados por máquina y devuelve archivos, páginas y salida.

    ``REVISAR_SIN_ID`` se omite deliberadamente: esos expedientes requieren una
    decisión humana antes de incorporarse al archivo clínico final.
    """
    if not carpeta_organizada.is_dir():
        raise ValueError(f"La carpeta organizada no existe: {carpeta_organizada}")

    orden = "descendente" if descendente else "ascendente"
    grupos = carpetas_maquina(carpeta_organizada, descendente)
    pdfs: list[tuple[int, Path]] = []
    for maquina, carpeta in grupos:
        for pdf in sorted(carpeta.rglob("*.pdf"), key=lambda ruta: ruta.name.casefold()):
            pdfs.append((maquina, pdf))

    if not pdfs:
        raise ValueError("No se encontraron PDFs dentro de carpetas Maquina_###.")

    nombre_base = f"Registro_unido_por_maquina_{orden}"
    salida = nombre_disponible(carpeta_organizada, nombre_base)
    if not ejecutar:
        print(f"SIMULACION: se unirán {len(pdfs)} PDFs de {len(grupos)} máquinas en orden {orden}.")
        for maquina, pdf in pdfs:
            print(f"  Maquina_{maquina:03d}: {pdf.name}")
        print(f"SALIDA PREVISTA: {salida}")
        return len(pdfs), 0, None

    writer = PdfWriter()
    paginas = 0
    for maquina, pdf in pdfs:
        try:
            lector = PdfReader(pdf)
            for pagina in lector.pages:
                writer.add_page(pagina)
                paginas += 1
        except Exception as error:
            print(f"ERROR al incluir {pdf.name} de Maquina_{maquina:03d}: {error}", file=sys.stderr)

    if paginas == 0:
        raise ValueError("No se pudo leer ninguna página para el PDF unido.")

    temporal = salida.with_name(f"{salida.stem}.temporal.pdf")
    try:
        with temporal.open("wb") as archivo:
            writer.write(archivo)
        comprobacion = PdfReader(temporal)
        if len(comprobacion.pages) != paginas:
            raise RuntimeError("La verificación del PDF unido no conservó todas las páginas.")
        temporal.replace(salida)
    except Exception:
        temporal.unlink(missing_ok=True)
        raise

    print(f"UNIDO: {salida}")
    return len(pdfs), paginas, salida


def organizar(origen: Path, destino: Path, ejecutar: bool, mover_originales: bool) -> tuple[int, int]:
    """Clasifica los PDFs y devuelve (registros procesados, pendientes)."""
    if not origen.is_dir():
        raise ValueError(f"La carpeta de origen no existe: {origen}")
    if origen.resolve() == destino.resolve():
        raise ValueError("La carpeta de destino debe ser distinta de la carpeta de origen.")

    procesados = pendientes = 0
    for pdf in iterar_pdfs(origen, destino):
        try:
            reader = PdfReader(pdf)
            registros = separar_registros(reader)
        except Exception as error:
            print(f"ERROR al leer {pdf.name}: {error}", file=sys.stderr)
            pendientes += 1
            continue

        # Para un único registro válido sí se puede mover el original completo,
        # sin crear un duplicado. Los documentos con varios registros jamás se
        # mueven porque se han separado en archivos nuevos.
        if mover_originales and len(registros) == 1 and registros[0].maquina:
            carpeta = destino / f"Maquina_{registros[0].maquina}"
            salida = nombre_disponible(carpeta, pdf.stem)
            if not ejecutar:
                print(f"SIMULACION: mover {pdf.name} -> {carpeta.name} ({registros[0].maquina})")
            else:
                carpeta.mkdir(parents=True, exist_ok=True)
                shutil.move(str(pdf), str(salida))
                print(f"MOVIDO: {salida}")
            procesados += 1
            continue

        for numero, registro in enumerate(registros, start=1):
            carpeta = destino / (f"Maquina_{registro.maquina}" if registro.maquina else "REVISAR_SIN_ID")
            sufijo = "" if len(registros) == 1 else f"_registro_{numero:03d}"
            salida = nombre_disponible(carpeta, f"{pdf.stem}{sufijo}")
            if not ejecutar:
                estado = registro.maquina or "SIN ID"
                print(f"SIMULACION: {pdf.name} páginas {registro.paginas[0] + 1}-{registro.paginas[-1] + 1} -> {carpeta.name} ({estado})")
                procesados += 1
                continue

            carpeta.mkdir(parents=True, exist_ok=True)
            escribir_registro(reader, registro, salida)
            print(f"CREADO: {salida}")
            procesados += 1
            if registro.maquina is None:
                pendientes += 1

    return procesados, pendientes


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Separa, organiza o une registros de hemodiálisis por ID Máquina.")
    parser.add_argument(
        "origen",
        nargs="?",
        type=Path,
        default=CARPETA_ORIGEN_PREDETERMINADA,
        help=f"Carpeta que contiene los PDFs recibidos. Predeterminada: {CARPETA_ORIGEN_PREDETERMINADA}",
    )
    parser.add_argument(
        "destino",
        nargs="?",
        type=Path,
        default=CARPETA_DESTINO_PREDETERMINADA,
        help=f"Carpeta donde se crearán Maquina_###. Predeterminada: {CARPETA_DESTINO_PREDETERMINADA}",
    )
    parser.add_argument("--ejecutar", action="store_true", help="Crea los PDFs. Sin esta opción sólo muestra la simulación.")
    parser.add_argument("--mover-originales", action="store_true", help="Mueve sólo PDFs de un registro después de crear su copia.")
    parser.add_argument(
        "--unir",
        action="store_true",
        help="Une los PDFs de las carpetas Maquina_###. Usa destino como carpeta organizada.",
    )
    parser.add_argument(
        "--descendente",
        action="store_true",
        help="Con --unir, ordena de número de máquina mayor a menor. El orden predeterminado es ascendente.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    opciones = argumentos()
    try:
        if opciones.unir:
            archivos, paginas, salida = unir_pdfs_por_maquina(
                opciones.destino, opciones.descendente, opciones.ejecutar
            )
            if opciones.ejecutar:
                print(f"\nPDF unido creado con {archivos} archivos y {paginas} páginas: {salida}")
            else:
                print(f"\nPDFs que se unirán: {archivos}.")
        else:
            total, pendientes = organizar(opciones.origen, opciones.destino, opciones.ejecutar, opciones.mover_originales)
            print(f"\nRegistros {'creados' if opciones.ejecutar else 'detectados'}: {total}. Pendientes de revisión: {pendientes}.")
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
