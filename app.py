from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_bcrypt import Bcrypt
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = 'super-secret-key'
bcrypt = Bcrypt(app)

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()

        # Articole
        c.execute('''CREATE TABLE IF NOT EXISTS articole (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titlu TEXT NOT NULL,
            continut TEXT NOT NULL,
            data_postarii TEXT NOT NULL,
            vizibil INTEGER NOT NULL DEFAULT 0,
            autor TEXT
        )''')

        # Utilizatori
        c.execute('''CREATE TABLE IF NOT EXISTS utilizatori (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            parola TEXT NOT NULL
        )''')

        # Categorii
        c.execute('''CREATE TABLE IF NOT EXISTS categorii (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nume TEXT UNIQUE NOT NULL
        )''')

        # Legătura articol - categorie
        c.execute('''CREATE TABLE IF NOT EXISTS articol_categorie (
            articol_id INTEGER,
            categorie_id INTEGER,
            FOREIGN KEY (articol_id) REFERENCES articole(id),
            FOREIGN KEY (categorie_id) REFERENCES categorii(id)
        )''')

        # Inserare categorii implicite
        categorii = ['politica', 'geopolitica', 'istorie']
        for cat in categorii:
            c.execute("INSERT OR IGNORE INTO categorii (nume) VALUES (?)", (cat,))

        # Utilizator admin default
        c.execute("SELECT * FROM utilizatori WHERE username = 'admin'")
        if not c.fetchone():
            from flask_bcrypt import Bcrypt
            bcrypt = Bcrypt()
            parola_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
            c.execute("INSERT INTO utilizatori (username, parola) VALUES (?, ?)", ('admin', parola_hash))

        # Like-uri (legătură articol - user)
        c.execute('''CREATE TABLE IF NOT EXISTS likes (
                    articol_id INTEGER,
                    username TEXT,
                    PRIMARY KEY (articol_id, username),
                    FOREIGN KEY (articol_id) REFERENCES articole(id),
                    FOREIGN KEY (username) REFERENCES utilizatori(username)
                )''')

def extensie_valida(nume_fisier):
    return '.' in nume_fisier and nume_fisier.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, titlu, continut, data_postarii, autor FROM articole WHERE vizibil=1 ORDER BY id DESC")
        articole = c.fetchall()
    return render_template("home.html", articole=articole)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        parola = request.form['parola']
        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            c.execute("SELECT parola FROM utilizatori WHERE username = ?", (username,))
            user = c.fetchone()
            if user and bcrypt.check_password_hash(user[0], parola):
                session['user'] = username
                return redirect(url_for('admin_panel'))
            else:
                return render_template("login.html", mesaj="Date incorecte.")
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if 'user' not in session:
        return redirect(url_for('login'))

    mesaj = None

    if request.method == 'POST':
        titlu = request.form['titlu']
        continut = request.form['continut']
        vizibil = 1 if 'vizibil' in request.form else 0
        data_postarii = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Upload imagini
        poze_salvate = []
        if 'poze' in request.files:
            fisiere = request.files.getlist('poze')
            for poza in fisiere:
                if poza and extensie_valida(poza.filename):
                    nume_sigur = secure_filename(poza.filename)
                    cale = os.path.join(app.config['UPLOAD_FOLDER'], nume_sigur)
                    poza.save(cale)
                    poze_salvate.append(nume_sigur)

        continut_complet = continut
        for poza in poze_salvate:
            continut_complet += f'<br><img src="/static/uploads/{poza}" style="max-width:100%;">'

        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            autor = session.get('user', 'Anonim')
            c.execute("INSERT INTO articole (titlu, continut, data_postarii, vizibil, autor) VALUES (?, ?, ?, ?, ?)",
                      (titlu, continut_complet, data_postarii, vizibil, autor))
            categorii_selectate = request.form.getlist('categorii')  # obține lista bifată din formular
            c.execute("SELECT id, nume FROM categorii")
            categorie_map = {nume: id_ for id_, nume in c.fetchall()}

            for cat in categorii_selectate:
                if cat in categorie_map:
                    c.execute("INSERT INTO articol_categorie (articol_id, categorie_id) VALUES (?, ?)",
                              (c.lastrowid, categorie_map[cat]))
            conn.commit()
            mesaj = "Articol adăugat cu succes!"

    return render_template("admin_panel.html", mesaj=mesaj)

@app.route('/admin/adauga-utilizator', methods=['GET', 'POST'])
def adauga_utilizator():
    if 'user' not in session:
        return redirect('/login')

    mesaj = ''
    if request.method == 'POST':
        username = request.form['username']
        parola = request.form['parola']
        parola_hash = bcrypt.generate_password_hash(parola).decode('utf-8')

        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO utilizatori (username, parola) VALUES (?, ?)", (username, parola_hash))
                mesaj = '✅ Utilizator adăugat cu succes.'
            except sqlite3.IntegrityError:
                mesaj = '⚠️ Acest nume de utilizator există deja.'

    return render_template("admin_adauga_utilizator.html", mesaj=mesaj)

@app.route('/admin/profil', methods=['GET', 'POST'])
def modifica_profil():
    if 'user' not in session:
        return redirect('/login')

    mesaj = ''
    user_vechi = session['user']

    if request.method == 'POST':
        user_nou = request.form['username']
        parola_noua = request.form['parola']
        parola_hash = bcrypt.generate_password_hash(parola_noua).decode('utf-8')

        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            c.execute("UPDATE utilizatori SET username = ?, parola = ? WHERE username = ?",
                      (user_nou, parola_hash, user_vechi))
            session['user'] = user_nou
            mesaj = '✅ Cont actualizat cu succes.'

    return render_template("admin_profil.html", mesaj=mesaj)

@app.route('/admin/articole')
def lista_articole():
    if 'user' not in session:
        return redirect(url_for('login'))
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, titlu, data_postarii, vizibil, autor FROM articole ORDER BY id DESC")
        articole = c.fetchall()
    return render_template("admin_articole.html", articole=articole)

@app.route('/admin/editeaza/<int:id>', methods=['GET', 'POST'])
def editeaza_articol(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        if request.method == 'POST':
            titlu = request.form['titlu']
            continut = request.form['continut']
            vizibil = 1 if 'vizibil' in request.form else 0

            # poze noi (suplimentar)
            poze_salvate = []
            if 'poze' in request.files:
                fisiere = request.files.getlist('poze')
                for poza in fisiere:
                    if poza and extensie_valida(poza.filename):
                        nume_sigur = secure_filename(poza.filename)
                        cale = os.path.join(app.config['UPLOAD_FOLDER'], nume_sigur)
                        poza.save(cale)
                        poze_salvate.append(nume_sigur)

            for poza in poze_salvate:
                continut += f'<br><img src="/static/uploads/{poza}" style="max-width:100%;">'

            c.execute("UPDATE articole SET titlu=?, continut=?, vizibil=? WHERE id=?",
                      (titlu, continut, vizibil, id))
            conn.commit()
            return redirect(url_for('lista_articole'))

        c.execute("SELECT titlu, continut, vizibil FROM articole WHERE id=?", (id,))
        articol = c.fetchone()

    return render_template("admin_editeaza.html", articol=articol, id=id)

@app.route('/admin/sterge/<int:id>', methods=['POST'])
def sterge_articol(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("DELETE FROM articole WHERE id=?", (id,))
        conn.commit()
    return redirect(url_for('lista_articole'))

@app.route('/articol/<int:id>')
def articol_complet(id):
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT titlu, continut, data_postarii, autor FROM articole WHERE id = ? AND vizibil = 1", (id,))
        articol = c.fetchone()

        # număr total like-uri
        c.execute("SELECT COUNT(*) FROM likes WHERE articol_id = ?", (id,))
        total_likes = c.fetchone()[0]

        # userul curent a dat like?
        user = session.get('user')
        a_dat_like = False
        if user:
            c.execute("SELECT 1 FROM likes WHERE articol_id = ? AND username = ?", (id, user))
            a_dat_like = c.fetchone() is not None

        if articol:
            return render_template("articol_complet.html", titlu=articol[0], continut=articol[1], data=articol[2], autor=articol[3], likes=total_likes,
                               a_dat_like=a_dat_like, articol_id=id)
        else:
            return "Articolul nu există sau nu este vizibil.", 404

@app.route('/<categorie>')
def pagina_categorie(categorie):
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT a.id, a.titlu, a.continut, a.data_postarii , a.autor
            FROM articole a
            JOIN articol_categorie ac ON a.id = ac.articol_id
            JOIN categorii c ON c.id = ac.categorie_id
            WHERE c.nume = ? AND a.vizibil = 1
            ORDER BY a.id DESC
        """, (categorie,))
        articole = c.fetchall()

    titlu_pagina = f"Articole din categoria: {categorie.capitalize()}"
    return render_template("home.html", articole=articole, titlu_pagina=titlu_pagina)

    titlu_pagina = f"Articole din categoria: {categorie.capitalize()}"
    return render_template("home.html", articole=articole, titlu_pagina=titlu_pagina)

@app.route('/toggle_like/<int:id>', methods=['POST'])
def toggle_like(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM likes WHERE articol_id = ? AND username = ?", (id, user))
        exista = c.fetchone()

        if exista:
            # Retrage like
            c.execute("DELETE FROM likes WHERE articol_id = ? AND username = ?", (id, user))
        else:
            # Adaugă like
            c.execute("INSERT INTO likes (articol_id, username) VALUES (?, ?)", (id, user))
        conn.commit()

    return redirect(url_for('articol_complet', id=id))

@app.route('/api/like/<int:id>', methods=['POST'])
def api_toggle_like(id):
    if 'user' not in session:
        return jsonify({"success": False, "message": "Neautentificat"}), 401

    user = session['user']
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM likes WHERE articol_id = ? AND username = ?", (id, user))
        exista = c.fetchone()

        if exista:
            c.execute("DELETE FROM likes WHERE articol_id = ? AND username = ?", (id, user))
            actiune = 'unliked'
        else:
            c.execute("INSERT INTO likes (articol_id, username) VALUES (?, ?)", (id, user))
            actiune = 'liked'

        conn.commit()
        # returnăm numărul actualizat de like-uri
        c.execute("SELECT COUNT(*) FROM likes WHERE articol_id = ?", (id,))
        total = c.fetchone()[0]

    return jsonify({"success": True, "actiune": actiune, "total": total})

# Pornim aplicația
if __name__ == "__main__":
    init_db()
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)