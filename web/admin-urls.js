import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  getAuth,
  signInWithEmailAndPassword,
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

import {
  getFirestore,
  doc,
  getDoc,
  setDoc,
  updateDoc,
  serverTimestamp
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-firestore.js";

/** ✅ Config Firebase */
const firebaseConfig = {
  apiKey: "AIzaSyDkHZzbWGdhGYm7SdC6HbQMiCFlItWnP78",
  authDomain: "forja-laboral-otec-chile.firebaseapp.com",
  projectId: "forja-laboral-otec-chile",
  // Plan A: NO usamos Storage, no importa si existe o no.
  storageBucket: "forja-laboral-otec-chile.firebasestorage.app",
  messagingSenderId: "420373310622",
  appId: "1:420373310622:web:042018f7f5c850ea799f8f",
  measurementId: "G-VC24Z4352S"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

const $ = (id) => document.getElementById(id);

/** UI refs */
const adminPanel = $("adminPanel");
const loginMsg = $("adminLoginMsg");

const adminMsg = $("adminMsg");
const alumnoInfo = $("alumnoInfo");
const docsList = $("docsList");

const form = $("admin-form");
const adminFormMsg = $("adminFormMsg");
const btnLimpiar = $("btn-limpiar");

/** Estado */
let currentRut = null;       // RUT normalizado (docID)
let currentAlumno = null;    // data del alumno

/** Utils */
const normRut = (s) => (s || "").toString().trim().toUpperCase().replace(/[.\- ]/g, "");
const safe = (v) => (v == null ? "" : String(v));

function setMsg(el, text, ok = true) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove("ok", "error");
  el.classList.add(ok ? "ok" : "error");
}

function setFormMsg(text, type = "") {
  if (!adminFormMsg) return;
  adminFormMsg.textContent = text;
  adminFormMsg.classList.remove("ok", "error");
  if (type) adminFormMsg.classList.add(type);
}

/** Validación RUT (simple pero efectiva) */
const dvRut = (num) => {
  let s = 1, m = 0;
  for (; num; num = Math.floor(num / 10)) {
    s = (s + (num % 10) * (9 - (m++ % 6))) % 11;
  }
  return s ? String(s - 1) : "K";
};

const validarRut = (rutCompleto) => {
  const limpio = normRut(rutCompleto);
  if (limpio.length < 2) return false;
  const cuerpo = limpio.slice(0, -1);
  const dv = limpio.slice(-1);
  if (!/^\d+$/.test(cuerpo)) return false;
  return dv === dvRut(parseInt(cuerpo, 10));
};

/** Firestore helpers */
async function loadAlumnoByRut(rutId) {
  const ref = doc(db, "alumnos", rutId);
  const snap = await getDoc(ref);
  return { ref, snap };
}

async function ensureAlumnoExists(rutId) {
  const ref = doc(db, "alumnos", rutId);
  await setDoc(ref, { rut: rutId, updatedAt: serverTimestamp() }, { merge: true });
  return ref;
}

async function saveDocsArray(rutId, docsArray) {
  const ref = doc(db, "alumnos", rutId);
  await setDoc(ref, {
    documentos: docsArray,
    updatedAt: serverTimestamp()
  }, { merge: true });

  const snap = await getDoc(ref);
  currentAlumno = snap.data() || {};
  renderAlumno(currentAlumno);
}

/** Render alumno + lista documentos con EDIT/DELETE */
function renderAlumno(alumno) {
  if (!alumnoInfo || !docsList) return;

  if (!alumno) {
    alumnoInfo.innerHTML = "";
    docsList.innerHTML = "";
    return;
  }

  alumnoInfo.innerHTML = `
    <p><strong>Nombre:</strong> ${safe(alumno.nombre) || "-"}</p>
    <p><strong>RUT (ID):</strong> ${safe(alumno.rut) || safe(currentRut) || "-"}</p>
  `;

  const arr = Array.isArray(alumno.documentos) ? alumno.documentos : [];

  if (!arr.length) {
    docsList.innerHTML = `<p>No hay documentos aún.</p>`;
    return;
  }

  docsList.innerHTML = arr.map((d, idx) => {
    const nombre = safe(d?.nombre) || "Documento";
    const url = safe(d?.url) || "#";
    return `
      <div class="card" style="padding:12px; margin:10px 0;">
        <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap;">
          <div style="min-width:220px;">
            <div><strong>${nombre}</strong></div>
            <div style="word-break:break-all; opacity:.9; margin-top:6px;">
              <a href="${url}" target="_blank" rel="noopener">${url}</a>
            </div>
          </div>

          <div style="display:flex; gap:8px; align-items:center;">
            <button class="btn btn-outline" type="button" data-action="edit-doc" data-index="${idx}">
              <i class="fa-solid fa-pen"></i> Editar
            </button>
            <button class="btn btn-outline" type="button" data-action="delete-doc" data-index="${idx}">
              <i class="fa-solid fa-trash"></i> Eliminar
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

/** =======================
 *  Login Admin (Auth)
 *  ======================= */
$("btnLoginAdmin")?.addEventListener("click", async () => {
  try {
    const email = $("adminEmail").value.trim();
    const pass = $("adminPass").value.trim();
    await signInWithEmailAndPassword(auth, email, pass);
    setMsg(loginMsg, "Login correcto ✅", true);
  } catch (e) {
    console.error(e);
    setMsg(loginMsg, "Correo o contraseña incorrecta", false);
  }
});

$("btnLogoutAdmin")?.addEventListener("click", async () => {
  await signOut(auth);
});

/** Gate UI by auth */
onAuthStateChanged(auth, (user) => {
  if (user) {
    if (adminPanel) adminPanel.style.display = "block";
    $("btnLogoutAdmin").style.display = "inline-flex";
    setMsg(loginMsg, `Admin activo: ${user.email}`, true);
  } else {
    if (adminPanel) adminPanel.style.display = "none";
    $("btnLogoutAdmin").style.display = "none";
    setMsg(loginMsg, "Inicia sesión para administrar", false);

    currentRut = null;
    currentAlumno = null;
    renderAlumno(null);
    setFormMsg("Listo para cargar.");
  }
});

/** =======================
 *  Buscar alumno
 *  ======================= */
$("btnBuscar")?.addEventListener("click", async () => {
  try {
    const rut = normRut($("rutBuscar").value);
    if (!rut) return setMsg(adminMsg, "Pon un RUT para buscar.", false);

    const { snap } = await loadAlumnoByRut(rut);

    currentRut = rut;

    if (!snap.exists()) {
      currentAlumno = null;
      renderAlumno({ rut }); // render mínimo
      setMsg(adminMsg, "Alumno no existe aún. Puedes crearlo y/o agregar documentos por URL.", true);
      return;
    }

    currentAlumno = snap.data();
    renderAlumno(currentAlumno);
    setMsg(adminMsg, "Alumno cargado ✅", true);
  } catch (e) {
    console.error(e);
    setMsg(adminMsg, "Error buscando alumno.", false);
  }
});

/** =======================
 *  Agregar documento por URL
 *  ======================= */
$("btnAgregarDoc")?.addEventListener("click", async () => {
  try {
    if (!currentRut) return setMsg(adminMsg, "Primero busca un alumno por RUT.", false);

    const nombre = $("docNombre").value.trim();
    const url = $("docUrl").value.trim();

    if (!nombre || !url) return setMsg(adminMsg, "Completa nombre y URL.", false);
    if (!/^https?:\/\/.+/i.test(url)) return setMsg(adminMsg, "La URL debe empezar con http/https.", false);

    // Asegura doc existente
    await ensureAlumnoExists(currentRut);

    // Cargar docs actuales
    const { snap } = await loadAlumnoByRut(currentRut);
    const data = snap.exists() ? (snap.data() || {}) : {};
    const docs = Array.isArray(data.documentos) ? [...data.documentos] : [];

    docs.push({ nombre, url });

    await saveDocsArray(currentRut, docs);

    $("docNombre").value = "";
    $("docUrl").value = "";

    setMsg(adminMsg, "Documento agregado ✅", true);
  } catch (e) {
    console.error(e);
    setMsg(adminMsg, "Error agregando documento (revisa permisos).", false);
  }
});

/** =======================
 *  EDITAR / ELIMINAR docs (delegación)
 *  ======================= */
docsList?.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;

  if (!currentRut) return setMsg(adminMsg, "Primero busca un alumno por RUT.", false);

  const action = btn.getAttribute("data-action");
  const index = Number(btn.getAttribute("data-index"));

  try {
    const { snap } = await loadAlumnoByRut(currentRut);
    if (!snap.exists()) return setMsg(adminMsg, "Alumno no existe.", false);

    const data = snap.data() || {};
    const docs = Array.isArray(data.documentos) ? [...data.documentos] : [];
    if (!docs[index]) return setMsg(adminMsg, "Documento no encontrado.", false);

    if (action === "delete-doc") {
      const ok = confirm(`¿Eliminar este documento?\n\n${safe(docs[index].nombre)}`);
      if (!ok) return;

      docs.splice(index, 1);
      await saveDocsArray(currentRut, docs);
      setMsg(adminMsg, "Documento eliminado ✅", true);
      return;
    }

    if (action === "edit-doc") {
      const actual = docs[index];

      const nuevoNombre = prompt("Editar nombre del documento:", safe(actual.nombre));
      if (nuevoNombre === null) return; // cancel
      const nuevoUrl = prompt("Editar URL del documento (debe empezar con https):", safe(actual.url));
      if (nuevoUrl === null) return;

      const nombre = nuevoNombre.trim();
      const url = nuevoUrl.trim();

      if (!nombre || !url) return setMsg(adminMsg, "Nombre y URL no pueden quedar vacíos.", false);
      if (!/^https?:\/\/.+/i.test(url)) return setMsg(adminMsg, "La URL debe empezar con http/https.", false);

      docs[index] = { nombre, url };
      await saveDocsArray(currentRut, docs);

      setMsg(adminMsg, "Documento editado ✅", true);
      return;
    }
  } catch (err) {
    console.error(err);
    setMsg(adminMsg, "Error editando/eliminando (revisa permisos).", false);
  }
});

/** =======================
 *  Crear / actualizar alumno (Plan A)
 *  ======================= */
btnLimpiar?.addEventListener("click", () => {
  form?.reset();
  setFormMsg("Listo para cargar.");
});

form?.addEventListener("submit", async (e) => {
  e.preventDefault();

  const rutRaw = $("rut").value.trim();
  const clave = $("clave").value.trim();
  const nombre = $("nombre").value.trim();

  if (!validarRut(rutRaw)) {
    setFormMsg("RUT inválido. Ej: 12.345.678-9", "error");
    $("rut").focus();
    return;
  }
  if (!clave || !nombre) {
    setFormMsg("Falta clave o nombre.", "error");
    return;
  }

  const rutId = normRut(rutRaw);

  try {
    setFormMsg("Guardando alumno…");

    await setDoc(doc(db, "alumnos", rutId), {
      rut: rutId,
      clave,
      nombre,
      updatedAt: serverTimestamp()
    }, { merge: true });

    setFormMsg("✅ Alumno guardado.", "ok");

    // Si justo estás trabajando con ese alumno, refrescar vista
    if (currentRut === rutId) {
      const { snap } = await loadAlumnoByRut(rutId);
      currentAlumno = snap.exists() ? snap.data() : null;
      renderAlumno(currentAlumno);
    }
  } catch (err) {
    console.error(err);
    setFormMsg("❌ Error guardando. Revisa permisos (rules).", "error");
  }
});
