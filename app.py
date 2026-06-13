import os, sqlite3, uuid, hmac
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, abort, flash, jsonify, session, Response
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import qrcode
from werkzeug.security import check_password_hash

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / 'web'
DB_PATH = BASE_DIR / 'instance' / 'certificados.db'
QR_DIR = BASE_DIR / 'static' / 'qrs'
PDF_DIR = BASE_DIR / 'certificados'
LOGO_PATH = BASE_DIR / 'static' / 'img' / 'logo_forja.png'
LOGO_SENCE = BASE_DIR / 'static' / 'img' / 'logo_sence.png'
LOGO_NCH = BASE_DIR / 'static' / 'img' / 'logo_nch.png'
FIRMA_PATH = BASE_DIR / 'static' / 'img' / 'firma.png'

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=int(os.environ.get('SESSION_MINUTES', '90'))),
)
app.secret_key = os.environ.get('SECRET_KEY', 'forja-secret-key-cambiar-en-produccion')
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'forja2026segura')
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'forja2026segura')

PORTAL_ADMIN_USER = os.environ.get('PORTAL_ADMIN_USER', ADMIN_USER)
PORTAL_ADMIN_PASSWORD = os.environ.get('PORTAL_ADMIN_PASSWORD', ADMIN_PASSWORD)


def verify_password(stored_password, candidate):
    """Permite contraseña plana en local y hash de Werkzeug en producción."""
    if not stored_password:
        return False
    if stored_password.startswith(('pbkdf2:', 'scrypt:', 'bcrypt:')):
        try:
            return check_password_hash(stored_password, candidate)
        except Exception:
            return False
    return hmac.compare_digest(stored_password, candidate)


def normalize_rut(value):
    return (value or '').strip().upper().replace('.', '').replace('-', '').replace(' ', '')


def public_doc_url(value):
    value = (value or '').strip()
    if value.startswith(('http://', 'https://')):
        return value
    return ''


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    QR_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alumnos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alumno_id TEXT UNIQUE NOT NULL,
                codigo_verificacion TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                rut TEXT,
                correo TEXT,
                curso TEXT NOT NULL,
                nivel TEXT,
                horas INTEGER,
                nota_final TEXT,
                fecha_inicio TEXT,
                fecha_termino TEXT NOT NULL,
                instructor TEXT,
                empresa TEXT,
                estado TEXT DEFAULT 'VIGENTE',
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                area TEXT,
                horas INTEGER,
                modalidad TEXT,
                estado TEXT DEFAULT 'ACTIVO',
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                accion TEXT NOT NULL,
                detalle TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS portal_alumnos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rut TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                correo TEXT,
                clave TEXT NOT NULL,
                estado TEXT DEFAULT 'ACTIVO',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS portal_documentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alumno_rut TEXT NOT NULL,
                nombre TEXT NOT NULL,
                url TEXT NOT NULL,
                tipo TEXT DEFAULT 'PDF',
                created_at TEXT NOT NULL,
                FOREIGN KEY (alumno_rut) REFERENCES portal_alumnos(rut)
            )
        ''')
        # Cursos base para versión empresa
        cursos_base = [
            ('Operador Grúa Horquilla', 'Operación maquinaria', 40, 'Presencial'),
            ('Rigger Baja', 'Izaje y maniobras', 16, 'Presencial'),
            ('Rigger Media', 'Izaje y maniobras', 24, 'Presencial'),
            ('Rigger Alta', 'Izaje y maniobras', 32, 'Presencial'),
            ('Supervisor de Izaje', 'Supervisión operacional', 40, 'Presencial'),
            ('Ley Karin', 'Cumplimiento normativo', 8, 'Online/Presencial'),
            ('Camión Pluma', 'Operación maquinaria', 40, 'Presencial'),
            ('Manlift', 'Operación maquinaria', 16, 'Presencial'),
            ('Grúa Puente', 'Operación maquinaria', 24, 'Presencial'),
        ]
        for nombre, area, horas, modalidad in cursos_base:
            conn.execute(
                'INSERT OR IGNORE INTO cursos (nombre, area, horas, modalidad, created_at) VALUES (?, ?, ?, ?, ?)',
                (nombre, area, horas, modalidad, datetime.now().isoformat(timespec='seconds'))
            )
        conn.commit()


def next_alumno_id(conn):
    year = datetime.now().year
    prefix = f'FORJA-{year}-'
    row = conn.execute("SELECT alumno_id FROM alumnos WHERE alumno_id LIKE ? ORDER BY id DESC LIMIT 1", (prefix + '%',)).fetchone()
    n = int(row['alumno_id'].split('-')[-1]) + 1 if row else 1
    return f'{prefix}{n:06d}'


def require_admin():
    if not admin_required():
        abort(403)


def log_event(action, detail=''):
    try:
        with db() as conn:
            conn.execute(
                'INSERT INTO audit_log (usuario, accion, detalle, created_at) VALUES (?, ?, ?, ?)',
                (session.get('forja_admin_user', 'system'), action, detail, datetime.now().isoformat(timespec='seconds'))
            )
            conn.commit()
    except Exception:
        pass


def get_alumno(codigo):
    with db() as conn:
        return conn.execute('SELECT * FROM alumnos WHERE codigo_verificacion=?', (codigo,)).fetchone()


def qr_url(codigo):
    return f'{APP_BASE_URL}/verificar/{codigo}'


def make_qr(codigo):
    path = QR_DIR / f'{codigo}.png'
    img = qrcode.make(qr_url(codigo))
    img.save(path)
    return path


def make_pdf(alumno):
    codigo = alumno['codigo_verificacion']
    pdf_path = PDF_DIR / f'certificado_{alumno["alumno_id"]}.pdf'
    qr_path = make_qr(codigo)

    c = canvas.Canvas(str(pdf_path), pagesize=landscape(A4))
    w, h = landscape(A4)

    # Fondo y marcos
    c.setFillColor(colors.HexColor('#fcfbf7'))
    c.rect(0, 0, w, h, stroke=0, fill=1)

    c.setStrokeColor(colors.HexColor('#111827'))
    c.setLineWidth(2)
    c.rect(12*mm, 12*mm, w-24*mm, h-24*mm, stroke=1, fill=0)

    c.setStrokeColor(colors.HexColor('#b68b2c'))
    c.setLineWidth(1.5)
    c.rect(17*mm, 17*mm, w-34*mm, h-34*mm, stroke=1, fill=0)

    # Logos
    if LOGO_PATH.exists():
        c.drawImage(ImageReader(str(LOGO_PATH)), 24*mm, h-39*mm,
                    width=44*mm, height=25*mm,
                    preserveAspectRatio=True, mask='auto')

    if LOGO_SENCE.exists():
        c.drawImage(ImageReader(str(LOGO_SENCE)), w-84*mm, h-37*mm,
                    width=28*mm, height=18*mm,
                    preserveAspectRatio=True, mask='auto')

    if LOGO_NCH.exists():
        c.drawImage(ImageReader(str(LOGO_NCH)), w-52*mm, h-37*mm,
                    width=25*mm, height=18*mm,
                    preserveAspectRatio=True, mask='auto')

    # Título
    c.setFillColor(colors.HexColor('#111827'))
    c.setFont('Helvetica-Bold', 28)
    c.drawCentredString(w/2, h-42*mm, 'DIPLOMA DE CERTIFICACIÓN')

    c.setFont('Helvetica', 12)
    c.drawCentredString(w/2, h-50*mm, 'Documento verificable mediante código QR y código único digital')

    c.setFont('Helvetica', 9)
    c.setFillColor(colors.HexColor('#374151'))
    c.drawCentredString(w/2, h-57*mm, 'Certificación emitida bajo estándares de capacitación laboral en Chile')
    c.drawCentredString(w/2, h-63*mm, 'OTEC conforme a normativa chilena, procesos de capacitación vigentes y referencia SENCE cuando corresponda')

    # Cuerpo
    c.setFillColor(colors.HexColor('#111827'))
    c.setFont('Helvetica', 14)
    c.drawCentredString(w/2, h-78*mm, 'Se certifica que')

    c.setFont('Helvetica-Bold', 26)
    c.drawCentredString(w/2, h-93*mm, alumno['nombre'].upper())

    c.setFont('Helvetica', 13)
    rut = f"RUT: {alumno['rut']}" if alumno['rut'] else 'RUT: no informado'
    c.drawCentredString(w/2, h-103*mm, rut)

    c.setFont('Helvetica', 14)
    c.drawCentredString(w/2, h-120*mm, 'ha aprobado satisfactoriamente el curso')

    c.setFont('Helvetica-Bold', 20)
    c.drawCentredString(w/2, h-134*mm, alumno['curso'].upper())

    # Detalles
    detalles = [
        ('ID Alumno', alumno['alumno_id']),
        ('Código verificación', alumno['codigo_verificacion']),
        ('Fecha término', alumno['fecha_termino']),
        ('Horas', str(alumno['horas'] or 'No informado')),
        ('Nota final', alumno['nota_final'] or 'No informado'),
        ('Estado', alumno['estado']),
        ('Vigencia', 'Según programa / normativa aplicable'),
    ]

    x, y = 34*mm, 43*mm
    c.setFont('Helvetica', 10)
    for i, (k, v) in enumerate(detalles):
        yy = y + (i//2)*8*mm
        xx = x + (i%2)*88*mm
        c.setFillColor(colors.HexColor('#6b7280'))
        c.drawString(xx, yy, f'{k}:')
        c.setFillColor(colors.HexColor('#111827'))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(xx + 36*mm, yy, str(v))
        c.setFont('Helvetica', 10)

    # Firma opcional
    if FIRMA_PATH.exists():
        c.drawImage(ImageReader(str(FIRMA_PATH)), 36*mm, 25*mm,
                    width=42*mm, height=18*mm,
                    preserveAspectRatio=True, mask='auto')
    c.setFillColor(colors.HexColor('#111827'))
    c.setFont('Helvetica', 9)
    c.drawString(36*mm, 22*mm, 'Firma digital autorizada')
    c.line(34*mm, 27*mm, 90*mm, 27*mm)

    # QR
    c.drawImage(ImageReader(str(qr_path)), w-55*mm, 31*mm, width=32*mm, height=32*mm)
    c.setFont('Helvetica', 8)
    c.setFillColor(colors.HexColor('#374151'))
    c.drawCentredString(w-39*mm, 27*mm, 'Escanear para verificar')
    c.drawCentredString(w/2, 18*mm, f'Verificación pública: {qr_url(codigo)}')

    c.save()
    return pdf_path


@app.route('/')
def home():
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/index.html')
def web_index():
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/cursos.html')
def web_cursos():
    return send_from_directory(WEB_DIR, 'cursos.html')


@app.route('/portal-alumnos.html')
def web_portal_alumnos():
    return redirect(url_for('portal_alumnos'))


@app.route('/verificar-certificado.html')
def web_verificar_certificado():
    return send_from_directory(WEB_DIR, 'verificar-certificado.html')


@app.route('/admin.html')
def web_admin_interno():
    return redirect(url_for('login_portal'))


def portal_admin_required():
    return session.get('forja_portal_admin_logged') is True


@app.route('/login-portal', methods=['GET', 'POST'])
def login_portal():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '').strip()
        if usuario == PORTAL_ADMIN_USER and verify_password(PORTAL_ADMIN_PASSWORD, password):
            session.permanent = True
            session['forja_portal_admin_logged'] = True
            session['forja_portal_admin_user'] = usuario
            log_event('LOGIN_PORTAL', usuario)
            return redirect(url_for('admin_portal'))
        flash('Usuario o contraseña incorrectos.')
    if portal_admin_required():
        return redirect(url_for('admin_portal'))
    return render_template('login_portal.html')


@app.route('/logout-portal')
def logout_portal():
    session.pop('forja_portal_admin_logged', None)
    session.pop('forja_portal_admin_user', None)
    return redirect(url_for('login_portal'))


@app.route('/admin-portal')
def admin_portal():
    if not portal_admin_required():
        return redirect(url_for('login_portal'))
    with db() as conn:
        alumnos = conn.execute('SELECT * FROM portal_alumnos ORDER BY id DESC').fetchall()
        documentos = conn.execute('''
            SELECT d.*, a.nombre AS alumno_nombre
            FROM portal_documentos d
            LEFT JOIN portal_alumnos a ON a.rut = d.alumno_rut
            ORDER BY d.id DESC LIMIT 80
        ''').fetchall()
        stats = conn.execute('''
            SELECT 
                (SELECT COUNT(*) FROM portal_alumnos) AS alumnos,
                (SELECT COUNT(*) FROM portal_documentos) AS documentos
        ''').fetchone()
    return render_template('admin_portal.html', alumnos=alumnos, documentos=documentos, stats=stats)



@app.route('/administracion')
def administracion():
    return send_from_directory(WEB_DIR, 'admin-selector.html')

@app.route('/styles.css')
def web_styles():
    return send_from_directory(WEB_DIR, 'styles.css')


@app.route('/script.js')
def web_script():
    return send_from_directory(WEB_DIR, 'script.js')


@app.route('/admin-urls.js')
def web_admin_urls():
    return send_from_directory(WEB_DIR, 'admin-urls.js')


@app.route('/img/<path:filename>')
def web_img(filename):
    return send_from_directory(WEB_DIR / 'img', filename)


@app.route('/docs/<path:filename>')
def web_docs(filename):
    return send_from_directory(WEB_DIR / 'docs', filename)


@app.route('/firebase.json')
def web_firebase_json():
    return send_from_directory(WEB_DIR, 'firebase.json')



def admin_required():
    return session.get('forja_admin_logged') is True


@app.route('/login', methods=['GET', 'POST'])
@app.route('/login-certificados', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '').strip()

        if usuario == ADMIN_USER and verify_password(ADMIN_PASSWORD, password):
            session.permanent = True
            session['forja_admin_logged'] = True
            session['forja_admin_user'] = usuario
            log_event('LOGIN_CERTIFICADOS', usuario)
            return redirect(url_for('admin'))

        flash('Usuario o contraseña incorrectos.')
        return render_template('login_admin.html')

    if admin_required():
        return redirect(url_for('admin'))

    return render_template('login_admin.html')


@app.route('/logout')
def logout():
    session.pop('forja_admin_logged', None)
    session.pop('forja_admin_user', None)
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if not admin_required():
        return redirect(url_for('login'))
    with db() as conn:
        alumnos = conn.execute('SELECT * FROM alumnos ORDER BY id DESC').fetchall()
        cursos = conn.execute('SELECT * FROM cursos ORDER BY nombre ASC').fetchall()
        stats = conn.execute('''
            SELECT 
                COUNT(*) total,
                SUM(CASE WHEN estado='VIGENTE' THEN 1 ELSE 0 END) vigentes,
                SUM(CASE WHEN estado='VENCIDO' THEN 1 ELSE 0 END) vencidos,
                SUM(CASE WHEN estado='REVOCADO' THEN 1 ELSE 0 END) revocados
            FROM alumnos
        ''').fetchone()
        logs = conn.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 8').fetchall()
    return render_template('admin.html', alumnos=alumnos, cursos=cursos, stats=stats, logs=logs)


@app.route('/crear', methods=['POST'])
def crear():
    require_admin()
    data = request.form
    with db() as conn:
        alumno_id = next_alumno_id(conn)
        codigo = uuid.uuid4().hex[:12].upper()
        conn.execute('''INSERT INTO alumnos
            (alumno_id, codigo_verificacion, nombre, rut, correo, curso, nivel, horas, nota_final, fecha_inicio, fecha_termino, instructor, empresa, estado, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (alumno_id, codigo, data['nombre'].strip(), data.get('rut','').strip(), data.get('correo','').strip(), data['curso'].strip(), data.get('nivel','').strip(),
             data.get('horas') or None, data.get('nota_final','').strip(), data.get('fecha_inicio','').strip(), data['fecha_termino'].strip(),
             data.get('instructor','').strip(), data.get('empresa','').strip(), data.get('estado','VIGENTE'), datetime.now().isoformat(timespec='seconds')))
        conn.commit()
    alumno = get_alumno(codigo)
    make_pdf(alumno)
    log_event('CREAR_CERTIFICADO', f'{alumno_id} - {data.get("nombre","")}')
    flash(f'Certificado creado: {alumno_id}')
    return redirect(url_for('admin'))



@app.route('/dashboard')
def dashboard():
    if not admin_required():
        return redirect(url_for('login'))
    with db() as conn:
        stats = conn.execute('''
            SELECT 
                COUNT(*) total,
                SUM(CASE WHEN estado='VIGENTE' THEN 1 ELSE 0 END) vigentes,
                SUM(CASE WHEN estado='VENCIDO' THEN 1 ELSE 0 END) vencidos,
                SUM(CASE WHEN estado='REVOCADO' THEN 1 ELSE 0 END) revocados
            FROM alumnos
        ''').fetchone()
        por_curso = conn.execute('SELECT curso, COUNT(*) total FROM alumnos GROUP BY curso ORDER BY total DESC LIMIT 10').fetchall()
        ultimos = conn.execute('SELECT * FROM alumnos ORDER BY id DESC LIMIT 5').fetchall()
    return render_template('dashboard.html', stats=stats, por_curso=por_curso, ultimos=ultimos)


@app.route('/certificados/<codigo>/estado', methods=['POST'])
def cambiar_estado(codigo):
    require_admin()
    estado = request.form.get('estado', 'VIGENTE').upper()
    if estado not in ('VIGENTE', 'VENCIDO', 'REVOCADO'):
        abort(400)
    with db() as conn:
        conn.execute('UPDATE alumnos SET estado=? WHERE codigo_verificacion=?', (estado, codigo.upper()))
        conn.commit()
    log_event('CAMBIAR_ESTADO', f'{codigo.upper()} -> {estado}')
    flash(f'Estado actualizado a {estado}')
    return redirect(url_for('admin'))


@app.route('/export/certificados.csv')
def export_certificados_csv():
    require_admin()
    with db() as conn:
        rows = conn.execute('SELECT alumno_id,codigo_verificacion,nombre,rut,correo,curso,nivel,horas,nota_final,fecha_inicio,fecha_termino,instructor,empresa,estado,created_at FROM alumnos ORDER BY id DESC').fetchall()
    header = ['alumno_id','codigo_verificacion','nombre','rut','correo','curso','nivel','horas','nota_final','fecha_inicio','fecha_termino','instructor','empresa','estado','created_at']
    lines = [','.join(header)]
    for r in rows:
        vals = []
        for h in header:
            v = '' if r[h] is None else str(r[h])
            vals.append('"' + v.replace('"','""') + '"')
        lines.append(','.join(vals))
    log_event('EXPORTAR_CSV', f'{len(rows)} registros')
    return Response('\\n'.join(lines), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition':'attachment; filename=certificados_forja.csv'})


@app.route('/api/dashboard')
def api_dashboard():
    require_admin()
    with db() as conn:
        stats = conn.execute('''
            SELECT 
                COUNT(*) total,
                SUM(CASE WHEN estado='VIGENTE' THEN 1 ELSE 0 END) vigentes,
                SUM(CASE WHEN estado='VENCIDO' THEN 1 ELSE 0 END) vencidos,
                SUM(CASE WHEN estado='REVOCADO' THEN 1 ELSE 0 END) revocados
            FROM alumnos
        ''').fetchone()
        por_curso = conn.execute('SELECT curso, COUNT(*) total FROM alumnos GROUP BY curso ORDER BY total DESC LIMIT 10').fetchall()
    return jsonify({'stats': dict(stats), 'por_curso': [dict(r) for r in por_curso]})



@app.route('/portal', methods=['GET', 'POST'])
@app.route('/alumnos', methods=['GET', 'POST'])
def portal_alumnos():
    alumno = None
    documentos = []
    if request.method == 'POST':
        rut = normalize_rut(request.form.get('rut'))
        clave = request.form.get('clave', '').strip()
        with db() as conn:
            alumno = conn.execute('SELECT * FROM portal_alumnos WHERE rut=? AND estado="ACTIVO"', (rut,)).fetchone()
            if alumno and hmac.compare_digest(alumno['clave'], clave):
                documentos = conn.execute('SELECT * FROM portal_documentos WHERE alumno_rut=? ORDER BY id DESC', (rut,)).fetchall()
                log_event('ACCESO_ALUMNO_PORTAL', rut)
                return render_template('portal_alumnos.html', alumno=alumno, documentos=documentos)
        flash('RUT o clave incorrectos.')
    return render_template('portal_alumnos.html', alumno=alumno, documentos=documentos)


@app.route('/portal/alumnos/guardar', methods=['POST'])
def portal_guardar_alumno():
    if not portal_admin_required():
        return redirect(url_for('login_portal'))
    rut = normalize_rut(request.form.get('rut'))
    nombre = request.form.get('nombre', '').strip()
    correo = request.form.get('correo', '').strip()
    clave = request.form.get('clave', '').strip()
    estado = request.form.get('estado', 'ACTIVO').strip().upper()
    if not rut or not nombre or not clave:
        flash('Completa RUT, nombre y clave.')
        return redirect(url_for('admin_portal'))
    if estado not in ('ACTIVO', 'INACTIVO'):
        estado = 'ACTIVO'
    now = datetime.now().isoformat(timespec='seconds')
    with db() as conn:
        conn.execute("""
            INSERT INTO portal_alumnos (rut, nombre, correo, clave, estado, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rut) DO UPDATE SET
                nombre=excluded.nombre,
                correo=excluded.correo,
                clave=excluded.clave,
                estado=excluded.estado,
                updated_at=excluded.updated_at
        """, (rut, nombre, correo, clave, estado, now, now))
        conn.commit()
    log_event('GUARDAR_ALUMNO_PORTAL', f'{rut} - {nombre}')
    flash('Alumno guardado correctamente.')
    return redirect(url_for('admin_portal'))


@app.route('/portal/documentos/guardar', methods=['POST'])
def portal_guardar_documento():
    if not portal_admin_required():
        return redirect(url_for('login_portal'))
    rut = normalize_rut(request.form.get('rut'))
    nombre = request.form.get('nombre', '').strip()
    url = public_doc_url(request.form.get('url'))
    if not rut or not nombre or not url:
        flash('Completa RUT, nombre del documento y URL válida.')
        return redirect(url_for('admin_portal'))
    with db() as conn:
        alumno = conn.execute('SELECT rut FROM portal_alumnos WHERE rut=?', (rut,)).fetchone()
        if not alumno:
            flash('Primero debes crear el alumno.')
            return redirect(url_for('admin_portal'))
        conn.execute("""
            INSERT INTO portal_documentos (alumno_rut, nombre, url, tipo, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (rut, nombre, url, 'PDF', datetime.now().isoformat(timespec='seconds')))
        conn.commit()
    log_event('AGREGAR_DOCUMENTO_PORTAL', f'{rut} - {nombre}')
    flash('Documento agregado correctamente.')
    return redirect(url_for('admin_portal'))


@app.route('/portal/documentos/<int:doc_id>/eliminar', methods=['POST'])
def portal_eliminar_documento(doc_id):
    if not portal_admin_required():
        return redirect(url_for('login_portal'))
    with db() as conn:
        row = conn.execute('SELECT * FROM portal_documentos WHERE id=?', (doc_id,)).fetchone()
        if row:
            conn.execute('DELETE FROM portal_documentos WHERE id=?', (doc_id,))
            conn.commit()
            log_event('ELIMINAR_DOCUMENTO_PORTAL', f'{row["alumno_rut"]} - {row["nombre"]}')
    flash('Documento eliminado.')
    return redirect(url_for('admin_portal'))



@app.route('/manifest.webmanifest')
def manifest():
    return send_from_directory(WEB_DIR, 'manifest.webmanifest')


@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(WEB_DIR, 'service-worker.js')


@app.route('/robots.txt')
def robots():
    return send_from_directory(WEB_DIR, 'robots.txt')


@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(WEB_DIR, 'sitemap.xml')

@app.route('/verificar/<codigo>')
def verificar(codigo):
    alumno = get_alumno(codigo.upper())
    if not alumno:
        return render_template('no_valido.html', codigo=codigo), 404
    return render_template('verificar.html', alumno=alumno)


@app.route('/certificados/<codigo>/pdf')
def descargar_pdf(codigo):
    alumno = get_alumno(codigo.upper())
    if not alumno:
        abort(404)
    pdf_path = make_pdf(alumno)
    return send_file(pdf_path, as_attachment=True, download_name=f'certificado_{alumno["alumno_id"]}.pdf')


@app.route('/api/certificados')
def api_certificados():
    require_admin()
    with db() as conn:
        rows = conn.execute('SELECT * FROM alumnos ORDER BY id DESC').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/verificar/<codigo>')
def api_verificar(codigo):
    alumno = get_alumno(codigo.upper())
    if not alumno:
        return jsonify({'valido': False, 'codigo': codigo}), 404
    data = dict(alumno)
    data['valido'] = alumno['estado'] == 'VIGENTE'
    data['url_pdf'] = f'/certificados/{alumno["codigo_verificacion"]}/pdf'
    return jsonify(data)


init_db()

if __name__ == '__main__':
    app.run(debug=True)
