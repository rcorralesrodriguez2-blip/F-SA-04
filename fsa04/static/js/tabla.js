(() => {
  "use strict";

  const modulo = document.querySelector(".fsa04-module");
  if (!modulo) return;
  const formulario = modulo.querySelector("form[data-busqueda-historial]");
  const boton = formulario?.querySelector('[type="submit"]');
  if (!boton) return;
  formulario.addEventListener("submit", () => {
    boton.disabled = true;
    boton.textContent = "Buscando…";
    formulario.setAttribute("aria-busy", "true");
  });
  window.addEventListener("pageshow", () => {
    boton.disabled = false;
    boton.textContent = "Buscar";
    formulario.removeAttribute("aria-busy");
  });
})();
