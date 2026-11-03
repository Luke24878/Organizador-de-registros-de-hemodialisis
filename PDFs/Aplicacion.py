"""Interfaz sencilla para organizar y unir registros de hemodiálisis."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from Acomodar import procesar_pdf, unir_pdfs_por_maquina


class OrganizadorApp:
    def __init__(self, raiz: tk.Tk) -> None:
        self.raiz = raiz
        self.raiz.title("Organizador de Hemodiálisis")
        self.raiz.minsize(760, 400)
        self.archivo = tk.StringVar()
        self.carpeta_salida = tk.StringVar()
        self.estado = tk.StringVar(value="Selecciona un PDF para comenzar.")
        self.incidencias: list[str] = []
        self.botones_proceso: list[ttk.Button] = []
        self._crear_interfaz()

    @staticmethod
    def _carpeta_disponible(base: Path) -> Path:
        """Propone una carpeta nueva para no mezclar ejecuciones anteriores."""
        candidata = base
        consecutivo = 2
        while candidata.exists():
            candidata = base.with_name(f"{base.name}_{consecutivo}")
            consecutivo += 1
        return candidata

    def _crear_interfaz(self) -> None:
        marco = ttk.Frame(self.raiz, padding=22)
        marco.grid(sticky="nsew")
        self.raiz.columnconfigure(0, weight=1)
        self.raiz.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)

        ttk.Label(marco, text="Organizador de registros de hemodiálisis", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            marco,
            text="Selecciona un PDF. La aplicación separa sus registros y crea un PDF final ordenado por ID Máquina.",
            wraplength=690,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 18))

        ttk.Label(marco, text="Documento PDF").grid(row=2, column=0, sticky="w")
        ttk.Entry(marco, textvariable=self.archivo, state="readonly").grid(row=3, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(marco, text="Buscar archivo...", command=self.seleccionar_archivo).grid(row=3, column=1, sticky="ew")

        ttk.Label(marco, text="Carpeta de salida").grid(row=4, column=0, sticky="w", pady=(16, 0))
        ttk.Entry(marco, textvariable=self.carpeta_salida).grid(row=5, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(marco, text="Cambiar carpeta...", command=self.seleccionar_carpeta).grid(row=5, column=1, sticky="ew")

        opciones = ttk.LabelFrame(marco, text="Orden del PDF final", padding=14)
        opciones.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(22, 12))
        opciones.columnconfigure((0, 1), weight=1)
        boton_ascendente = ttk.Button(opciones, text="Ordenar menor → mayor", command=lambda: self.iniciar_proceso(False))
        boton_descendente = ttk.Button(opciones, text="Ordenar mayor → menor", command=lambda: self.iniciar_proceso(True))
        boton_ascendente.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        boton_descendente.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.botones_proceso.extend([boton_ascendente, boton_descendente])

        ttk.Separator(marco).grid(row=7, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(marco, textvariable=self.estado, wraplength=690).grid(row=8, column=0, columnspan=2, sticky="w")

        acciones = ttk.Frame(marco)
        acciones.grid(row=9, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(acciones, text="Revisar problemas", command=self.revisar_problemas).grid(row=0, column=0, padx=5)
        ttk.Button(acciones, text="Reiniciar", command=self.reiniciar).grid(row=0, column=1, padx=5)
        ttk.Button(acciones, text="Cerrar", command=self.raiz.destroy).grid(row=0, column=2, padx=(5, 0))

    def seleccionar_archivo(self) -> None:
        ruta = filedialog.askopenfilename(title="Selecciona el registro PDF", filetypes=[("Documentos PDF", "*.pdf")])
        if not ruta:
            return
        pdf = Path(ruta)
        self.archivo.set(str(pdf))
        # Cada documento queda en una subcarpeta propia para no mezclar turnos.
        base = Path.home() / "Downloads" / "Docs-organizados" / f"{pdf.stem}_ordenado"
        predeterminada = self._carpeta_disponible(base)
        self.carpeta_salida.set(str(predeterminada))
        self.estado.set("Documento cargado. Elige el orden del PDF final.")
        self.incidencias.clear()

    def seleccionar_carpeta(self) -> None:
        ruta = filedialog.askdirectory(title="Selecciona la carpeta de salida")
        if ruta:
            self.carpeta_salida.set(ruta)

    def iniciar_proceso(self, descendente: bool) -> None:
        if not self.archivo.get():
            messagebox.showwarning("Falta el documento", "Primero selecciona un archivo PDF.")
            return
        if not self.carpeta_salida.get():
            messagebox.showwarning("Falta la salida", "Selecciona una carpeta de salida.")
            return

        for boton in self.botones_proceso:
            boton.configure(state="disabled")
        self.estado.set("Procesando documento. Esto puede tardar unos momentos...")
        pdf = Path(self.archivo.get())
        destino = Path(self.carpeta_salida.get())
        threading.Thread(target=self._procesar, args=(pdf, destino, descendente), daemon=True).start()

    def _procesar(self, pdf: Path, destino: Path, descendente: bool) -> None:
        try:
            registros, sin_id = procesar_pdf(pdf, destino)
            archivos, paginas, salida = unir_pdfs_por_maquina(destino, descendente, ejecutar=True)
            orden = "mayor a menor" if descendente else "menor a mayor"
            self.incidencias = []
            if sin_id:
                self.incidencias.append(f"{sin_id} registro(s) sin ID Máquina se guardaron en REVISAR_SIN_ID y no se incluyeron en el PDF final.")
            mensaje = f"Listo: {registros} registros separados, {archivos} archivos unidos y {paginas} páginas en orden {orden}."
            self.raiz.after(0, self._finalizar, mensaje, salida)
        except Exception as error:
            self.incidencias = [f"Error durante el procesamiento: {error}"]
            self.raiz.after(0, self._finalizar_error, str(error))

    def _finalizar(self, mensaje: str, salida: Path | None) -> None:
        self.estado.set(mensaje)
        for boton in self.botones_proceso:
            boton.configure(state="normal")
        messagebox.showinfo("Proceso terminado", f"{mensaje}\n\nArchivo final:\n{salida}")

    def _finalizar_error(self, error: str) -> None:
        self.estado.set("El proceso no terminó. Usa ‘Revisar problemas’ para ver el detalle.")
        for boton in self.botones_proceso:
            boton.configure(state="normal")
        messagebox.showerror("No se pudo procesar el PDF", error)

    def revisar_problemas(self) -> None:
        if self.incidencias:
            messagebox.showwarning("Revisión de problemas", "\n\n".join(self.incidencias))
        else:
            messagebox.showinfo("Revisión de problemas", "No hay problemas registrados en esta sesión.")

    def reiniciar(self) -> None:
        self.archivo.set("")
        self.carpeta_salida.set("")
        self.incidencias.clear()
        self.estado.set("Selecciona un PDF para comenzar.")


if __name__ == "__main__":
    raiz = tk.Tk()
    OrganizadorApp(raiz)
    raiz.mainloop()
