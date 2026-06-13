
/* =============== Certificaciones: ocultar en móvil al llegar a "Capacítate" =============== */
(() => {
  const bar = document.querySelector('.cert-bar');
  const stopEl = document.getElementById('capacitate');
  if (!bar || !stopEl) return;

  const mq = window.matchMedia('(max-width: 720px)');

  const apply = () => {
    // En desktop no se oculta
    if (!mq.matches) {
      bar.classList.remove('cert-bar--hidden');
      return;
    }

    // En móvil: ocultar cuando el usuario llega a la sección
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          bar.classList.toggle('cert-bar--hidden', en.isIntersecting);
        });
      },
      { threshold: 0.05 }
    );

    obs.observe(stopEl);

    // Cleanup cuando cambia el media query
    const onChange = () => obs.disconnect();
    mq.addEventListener?.('change', onChange, { once: true });
  };

  apply();
})();

/* =========================================================
   Forja Laboral OTEC Chile — script.js (FULL)
   - Menú móvil
   - Scroll suave
   - Animaciones IntersectionObserver ([data-animate])
   - Hovers sutiles
   - Form contacto (demo)
   - Portal Alumnos: login real con Firestore (docId = RUT limpio)
   - Acceso Admin con prompt (simple)
   ========================================================= */

// Helpers
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

/* =============== Menú móvil (Forja) =============== */
(() => {
  const header = $('.main-header');
  if (!header) return;

  const nav = header.querySelector('.main-nav');
  if (!nav) return;

  let toggle = header.querySelector('.nav-toggle');
  if (!toggle) {
    toggle = document.createElement('button');
    toggle.className = 'nav-toggle';
    toggle.type = 'button';
    toggle.setAttribute('aria-label', 'Abrir menú');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<i class="fa-solid fa-bars"></i>';
    nav.parentNode.insertBefore(toggle, nav);
  }

  const closeMenu = () => {
    nav.classList.remove('nav--open');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Abrir menú');
  };

  const openMenu = () => {
    nav.classList.add('nav--open');
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Cerrar menú');
  };

  toggle.addEventListener('click', (e) => {
    e.preventDefault();
    nav.classList.contains('nav--open') ? closeMenu() : openMenu();
  });

  nav.addEventListener('click', (e) => {
    const link = e.target.closest('a');
    if (link) closeMenu();
  });

  document.addEventListener('click', (e) => {
    if (!nav.contains(e.target) && !toggle.contains(e.target)) closeMenu();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMenu();
  });

  window.addEventListener('resize', () => {
    if (window.matchMedia('(min-width: 768px)').matches) closeMenu();
  });
})();

/* =============== Scroll suave para anclas internas =============== */
(() => {
  $$('a[href^="#"]').forEach(a => {
    a.addEventListener('click', (e) => {
      const id = a.getAttribute('href');
      if (!id || id === '#') return;

      const el = document.querySelector(id);
      if (!el) return;

      e.preventDefault();
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      history.pushState(null, '', id);
    });
  });
})();

/* =============== Animaciones on-scroll =============== */
(() => {
  const items = $$('[data-animate]');
  if (!items.length || !('IntersectionObserver' in window)) {
    items.forEach(i => i.classList.add('is-inview'));
    return;
  }

  const io = new IntersectionObserver((entries) => {
    entries.forEach(({ isIntersecting, target }) => {
      if (isIntersecting) {
        target.classList.add('is-inview');
        io.unobserve(target);
      }
    });
  }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });

  items.forEach(el => io.observe(el));
})();

/* =============== Micro-interacciones hover =============== */
(() => {
  const liftables = $$('[data-hover="lift"]');
  const max = 6;

  liftables.forEach(card => {
    let rect = null;
    const onEnter = () => { rect = card.getBoundingClientRect(); };
    const onLeave = () => { card.style.transform = ''; rect = null; };

    const onMove = (e) => {
      if (!rect) return;
      const x = (e.clientX - rect.left) / rect.width;
      const y = (e.clientY - rect.top) / rect.height;
      const dx = (x - 0.5) * 2;
      const dy = (y - 0.5) * 2;
      card.style.transform = `translate(${(dx * max).toFixed(2)}px, ${(dy * max).toFixed(2)}px)`;
    };

    card.addEventListener('mouseenter', onEnter);
    card.addEventListener('mousemove', (e) => {
      window.requestAnimationFrame(() => onMove(e));
    });
    card.addEventListener('mouseleave', onLeave);
  });
})();

/* =============== Form de contacto (demo) =============== */
(() => {
  const form = $('#contact-form');
  if (!form) return;

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    alert('Formulario demo: aquí va tu integración real (EmailJS / backend / etc).');
    form.reset();
  });
})();

/* =============== Portal Alumnos (Firestore REAL) =============== */
(() => {
  // En tu portal-alumnos.html existen estos:
  const form = $('#portal-form');
  const rutInput = $('#rut');
  const passInput = $('#clave');

  const panelAlumno = $('[data-panel="alumno"]');
  const panelLogin = $('[data-panel="login"]');
  const nombreSpan = $('[data-field="nombre"]');
  const msg = $('#portal-mensaje');
  const docsWrap = $('[data-docs]');

  // Compatibilidad con tu versión antigua (por si hay páginas viejas)
  const btnLegacy = $('#btn-ingresar');
  const msgLegacy = $('#portal-msg');

  // Si no estamos en portal, salimos
  if (!form && !btnLegacy) return;

  const setMsg = (text, ok = true) => {
    const el = msg || msgLegacy;
    if (!el) return;
    el.textContent = text;
    el.classList.remove('ok', 'error');
    el.classList.add(ok ? 'ok' : 'error');
  };

  // Normaliza a ID de doc: sin puntos/guión/espacios, DV en mayúscula (K)
  const rutToDocId = (s) => (s || '')
    .toString()
    .trim()
    .toUpperCase()
    .replace(/[.\- ]/g, '');

  const safe = (v) => (v == null ? '' : String(v));

  const renderDocs = (alumno) => {
    if (!docsWrap) return;

    const items = [];

    // malla / certificado (guardados por admin)
    if (alumno.malla) {
      items.push({
        nombre: 'Malla curricular (PDF)',
        url: alumno.malla
      });
    }
    if (alumno.certificado) {
      items.push({
        nombre: 'Certificado (PDF)',
        url: alumno.certificado
      });
    }

    // documentos extra: [{nombre,url}, ...]
    const extra = Array.isArray(alumno.documentos) ? alumno.documentos : [];
    extra.forEach(d => {
      const nombre = (d && d.nombre) ? d.nombre : 'Documento';
      const url = (d && d.url) ? d.url : '';
      if (url) items.push({ nombre, url });
    });

    if (!items.length) {
      docsWrap.innerHTML = `<p style="opacity:.85;">Aún no hay documentos cargados para tu cuenta.</p>`;
      return;
    }

    docsWrap.innerHTML = items.map(d => {
      const href = safe(d.url);
      const name = safe(d.nombre) || 'Documento';
      return `
        <a class="portal-doc" href="${href}" target="_blank" rel="noopener"
           style="display:flex; align-items:center; gap:10px; padding:12px 14px; margin:10px 0; border-radius:12px; background:#fff; box-shadow:0 8px 20px rgba(0,0,0,.10); text-decoration:none;">
          <i class="fa-solid fa-file-pdf" style="font-size:18px;"></i>
          <span style="font-weight:600;">${name}</span>
        </a>
      `;
    }).join('');
  };

  const showAlumnoPanel = () => {
    if (panelAlumno) panelAlumno.classList.remove('panel--hidden');
    if (panelLogin) panelLogin.style.display = 'none';
  };

  const showLoginPanel = () => {
    if (panelAlumno) panelAlumno.classList.add('panel--hidden');
    if (panelLogin) panelLogin.style.display = '';
  };

  const doLogin = async () => {
    const rut = (rutInput?.value || '').trim();
    const clave = (passInput?.value || '').trim();

    if (!rut || !clave) {
      setMsg('Completa RUT y clave.', false);
      return;
    }

    // Requiere que portal-alumnos.html haya expuesto Firestore
    const db = window.db;
    const docFn = window.firestoreDoc;
    const getDocFn = window.firestoreGetDoc;

    if (!db || !docFn || !getDocFn) {
      setMsg('Portal no pudo conectar con la base de datos (Firestore).', false);
      return;
    }

    const rutId = rutToDocId(rut);

    try {
      setMsg('Verificando datos…', true);

      const ref = docFn(db, 'alumnos', rutId);
      const snap = await getDocFn(ref);

      if (!snap.exists()) {
        setMsg('No encontramos tu RUT. Verifica el formato o contacta a administración.', false);
        return;
      }

      const alumno = snap.data() || {};
      const claveDB = safe(alumno.clave).trim();

      if (claveDB !== clave) {
        setMsg('Clave incorrecta. Intenta nuevamente.', false);
        return;
      }

      // OK
      if (nombreSpan) nombreSpan.textContent = alumno.nombre || 'Alumno';
      setMsg('Acceso correcto ✅', true);
      renderDocs(alumno);
      showAlumnoPanel();

    } catch (e) {
      console.error(e);
      setMsg('Ocurrió un error consultando tu información. Intenta de nuevo.', false);
    }
  };

  // Submit del form real
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      doLogin();
    });
  }

  // Botón legacy (si existe en alguna página vieja)
  if (btnLegacy) {
    btnLegacy.addEventListener('click', (e) => {
      e.preventDefault();
      doLogin();
    });
  }

  // Enter en inputs
  [rutInput, passInput].filter(Boolean).forEach(inp => {
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        doLogin();
      }
    });
  });

  // Recuperar clave (por ahora informativo)
  const rec = $('[data-action="recuperar"]');
  rec?.addEventListener('click', (e) => {
    e.preventDefault();
    alert('Recuperación de clave: por ahora debes contactar a administración (WhatsApp).');
  });

  // Salir
  const salir = $('[data-action="salir"]');
  salir?.addEventListener('click', () => {
    // Limpia y vuelve al login
    if (rutInput) rutInput.value = '';
    if (passInput) passInput.value = '';
    if (docsWrap) docsWrap.innerHTML = '';
    if (nombreSpan) nombreSpan.textContent = 'Alumno';
    setMsg('Sesión cerrada.', true);
    showLoginPanel();
  });
})();

/* Acceso Admin público eliminado: el sistema administrativo vive en Render con clave privada. */
