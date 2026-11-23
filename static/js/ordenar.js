// Ordena las tablas al hacer clic en el encabezado de una columna.
// Las tablas paginadas (class "orden-servidor") se ordenan en el servidor con enlaces.
(function () {
  function valor(celda) {
    const t = (celda.dataset.orden ?? celda.innerText).trim();
    if (!t || t === "—" || t === "-") return null;
    let m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (m) return { n: +(m[3] + m[2].padStart(2, "0") + m[1].padStart(2, "0")) };
    m = t.match(/^(\d{1,2}):(\d{2})/);
    if (m) return { n: +m[1] * 60 + +m[2] };
    m = t.match(/^-?\d[\d.]*(,\d+)?/);
    if (m) return { n: parseFloat(m[0].replace(/\./g, "").replace(",", ".")) };
    return { s: t.toLowerCase() };
  }

  function comparar(a, b) {
    if (a === null && b === null) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    if ("n" in a && "n" in b) return a.n - b.n;
    return String(a.s ?? a.n).localeCompare(String(b.s ?? b.n), "es", { numeric: true });
  }

  document.querySelectorAll(".tabla-hd table:not(.orden-servidor):not(.sin-ordenar)").forEach(function (tabla) {
    if (!tabla.tHead || !tabla.tBodies.length) return;
    const ths = [...tabla.tHead.rows[0].cells];
    ths.forEach(function (th, i) {
      if (!th.textContent.trim() || th.hasAttribute("data-no-ordenar")) return;
      th.classList.add("th-ordenable");
      th.tabIndex = 0;
      th.title = "Ordenar";
      function ordenar() {
        const cuerpo = tabla.tBodies[0];
        const filas = [...cuerpo.rows].filter(f => f.cells.length === ths.length);
        if (filas.length < 2) return;
        const valores = new Map(filas.map(f => [f, valor(f.cells[i])]));
        const numerica = [...valores.values()].some(v => v && "n" in v);
        const dir = th.dataset.dir ? (th.dataset.dir === "asc" ? "desc" : "asc") : (numerica ? "desc" : "asc");
        ths.forEach(t => delete t.dataset.dir);
        th.dataset.dir = dir;
        filas.sort((a, b) => {
          const va = valores.get(a), vb = valores.get(b);
          if (va === null || vb === null) return comparar(va, vb);
          return comparar(va, vb) * (dir === "asc" ? 1 : -1);
        });
        filas.forEach(f => cuerpo.appendChild(f));
      }
      th.addEventListener("click", ordenar);
      th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ordenar(); } });
    });
  });
})();
