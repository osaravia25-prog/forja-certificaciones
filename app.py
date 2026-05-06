import os, sqlite3, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_file, abort, flash, jsonify
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import qrcode

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'instance' / 'certificados.db'
QR_DIR = BASE_DIR / 'static' / 'qrs'
PDF_DIR = BASE_DIR / 'certificados'
LOGO_PATH = BASE_DIR / 'static' / 'img' / 'logo_forja.png'
LOGO_SENCE = BASE_DIR / 'static' / 'img' / 'logo_sence.png'
LOGO_NCH = BASE_DIR / 'static' / 'img' / 'logo_nch.png'
FIRMA_PATH = BASE_DIR / 'static' / 'img' / 'firma.png'

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'Forja2026.')


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
        conn.commit()


def next_alumno_id(conn):
    year = datetime.now().year
    prefix = f'FORJA-{year}-'
    row = conn.execute("SELECT alumno_id FROM alumnos WHERE alumno_id LIKE ? ORDER BY id DESC LIMIT 1", (prefix + '%',)).fetchone()
    n = int(row['alumno_id'].split('-')[-1]) + 1 if row else 1
    return f'{prefix}{n:06d}'


def require_admin():
    key = request.args.get('key') or request.form.get('key') or request.headers.get('X-Admin-Key')
    if key != ADMIN_KEY:
        abort(403)


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
    return redirect(url_for('admin'))


@app.route('/admin')
def admin():
    key = request.args.get('key', '')
    if key != ADMIN_KEY:
        return render_template('login.html')
    with db() as conn:
        alumnos = conn.execute('SELECT * FROM alumnos ORDER BY id DESC').fetchall()
    return render_template('admin.html', alumnos=alumnos, key=key)


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
    flash(f'Certificado creado: {alumno_id}')
    return redirect(url_for('admin', key=request.form.get('key')))


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


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
