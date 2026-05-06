# Sistema de certificación digital Forja Laboral

Incluye:
- Registro de alumnos.
- ID automático por alumno: `FORJA-AÑO-000001`.
- Código único de verificación.
- QR automático apuntando a la página pública de verificación.
- Descarga de certificado PDF.
- API simple para verificar certificados.

## Instalación local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
set APP_BASE_URL=http://127.0.0.1:5000
set ADMIN_KEY=forja123
python app.py
```

En navegador:

```text
http://127.0.0.1:5000/admin?key=forja123
```

## Rutas importantes

- `/admin?key=CLAVE`: panel administrativo.
- `/verificar/CODIGO`: página pública del certificado.
- `/certificados/CODIGO/pdf`: descarga del PDF.
- `/api/verificar/CODIGO`: verificación en JSON.

## Para producción

Cambia `ADMIN_KEY`, configura `APP_BASE_URL` con tu dominio real y usa un servidor como Gunicorn/Nginx o un hosting compatible con Flask.
