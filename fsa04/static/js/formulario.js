(() => {
  "use strict";

  const modulo = document.querySelector(".fsa04-module");
  if (!modulo) return;
  const formulario = modulo.querySelector("form[data-vista-previa]");
  const inicio = modulo.querySelector("#fecha_solicitud");
  const fin = modulo.querySelector("#fecha_respuesta");
  const vista = modulo.querySelector("#vista-previa");
  const cumplimiento = modulo.querySelector("#cumplimiento");
  if (!formulario || !inicio || !fin || !vista || !cumplimiento) return;

  let temporizador;
  let peticion;
  let revision = 0;
  let guardando = false;
  const botonGuardar = formulario.querySelector('[type="submit"]');
  const textoGuardar = botonGuardar.textContent;

  formulario.addEventListener("submit", (evento) => {
    if (guardando) {
      evento.preventDefault();
      return;
    }
    guardando = true;
    clearTimeout(temporizador);
    ++revision;
    if (peticion) peticion.abort();
    formulario.setAttribute("aria-busy", "true");
    botonGuardar.disabled = true;
    botonGuardar.textContent = "Guardando…";
  });
  window.addEventListener("pageshow", () => {
    guardando = false;
    formulario.removeAttribute("aria-busy");
    botonGuardar.disabled = false;
    botonGuardar.textContent = textoGuardar;
  });

  async function actualizar(actual) {
    const controlador = new AbortController();
    peticion = controlador;
    const datos = new URLSearchParams({
      fecha_solicitud: inicio.value,
      fecha_respuesta: fin.value,
      _csrf_token: formulario.querySelector('[name="_csrf_token"]').value,
    });
    try {
      const respuesta = await fetch(formulario.dataset.vistaPrevia, {
        method: "POST", body: datos, credentials: "same-origin",
        cache: "no-store", signal: controlador.signal,
      });
      if (!respuesta.ok) throw new Error("Vista previa no disponible");
      const estado = await respuesta.json();
      if (actual !== revision) return;
      // El servidor decide las reglas; aquí solo se refleja su resultado.
      cumplimiento.required = estado.cumplimiento_obligatorio;
      cumplimiento.disabled = !estado.cumplimiento_habilitado;
      if (!estado.cumplimiento_habilitado) cumplimiento.value = "";
      vista.textContent = estado.mensaje;
    } catch (error) {
      if (error.name === "AbortError" || actual !== revision) return;
      cumplimiento.required = false;
      cumplimiento.disabled = false;
      vista.textContent = "No se pudo consultar la vista previa. Al guardar, el servidor validará las fechas y el cumplimiento.";
    }
  }

  function programar() {
    if (guardando) return;
    clearTimeout(temporizador);
    if (peticion) peticion.abort();
    const actual = ++revision;
    vista.textContent = "Consultando vista previa…";
    temporizador = setTimeout(() => actualizar(actual), 200);
  }

  inicio.addEventListener("input", programar);
  fin.addEventListener("input", programar);
})();
