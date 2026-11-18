import os
from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_secreta_pvz_2026").strip()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Faltan las variables de entorno SUPABASE_URL y SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/register", methods=["POST"])
def register():
    try:
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        if len(username) < 3 or len(password) < 4:
            return jsonify({
                "ok": False,
                "error": "El usuario debe tener al menos 3 caracteres y la contraseña 4."
            }), 400

        existing = supabase.table("usuarios").select("id").eq("username", username).execute()
        if existing.data:
            return jsonify({"ok": False, "error": "Ese nombre de usuario ya existe."}), 409

        pw_hash = generate_password_hash(password)
        res = supabase.table("usuarios").insert({
            "username": username,
            "password_hash": pw_hash
        }).execute()

        if not res.data:
            return jsonify({
                "ok": False,
                "error": "Supabase no devolvió el usuario creado. Revisa que RLS esté desactivado."
            }), 500

        nuevo_usuario = res.data[0]
        session["user_id"] = nuevo_usuario["id"]
        session["username"] = nuevo_usuario["username"]

        return jsonify({
            "ok": True,
            "user": {
                "username": nuevo_usuario["username"],
                "dia_actual": nuevo_usuario.get("dia_actual", 1),
                "zombis_derrotados": nuevo_usuario.get("zombis_derrotados", 0),
                "partidas_ganadas": nuevo_usuario.get("partidas_ganadas", 0)
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error en Supabase: {str(e)}"}), 500


@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        res = supabase.table("usuarios").select("*").eq("username", username).execute()
        if not res.data:
            return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos."}), 401

        user = res.data[0]
        if not check_password_hash(user["password_hash"], password):
            return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos."}), 401

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({
            "ok": True,
            "user": {
                "username": user["username"],
                "dia_actual": user["dia_actual"],
                "zombis_derrotados": user["zombis_derrotados"],
                "partidas_ganadas": user["partidas_ganadas"]
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error en Supabase: {str(e)}"}), 500


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/delete_account", methods=["POST"])
def delete_account():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "No hay sesión activa."}), 401

    try:
        supabase.table("usuarios").delete().eq("id", user_id).execute()
        session.clear()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error al eliminar la cuenta: {str(e)}"}), 500


@app.route("/api/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"logged_in": False})

    try:
        res = (
            supabase.table("usuarios")
            .select("username, dia_actual, zombis_derrotados, partidas_ganadas")
            .eq("id", user_id)
            .execute()
        )

        if not res.data:
            session.clear()
            return jsonify({"logged_in": False})

        return jsonify({
            "logged_in": True,
            "user": res.data[0]
        })
    except Exception:
        return jsonify({"logged_in": False})


@app.route("/api/save_progress", methods=["POST"])
def save_progress():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "No hay sesión activa."}), 401

    try:
        data = request.get_json() or {}
        nuevo_dia = int(data.get("dia_actual", 1))
        zombis_sumados = int(data.get("zombis_derrotados", 0))
        gano_nivel = bool(data.get("gano_nivel", False))

        res = (
            supabase.table("usuarios")
            .select("dia_actual, zombis_derrotados, partidas_ganadas")
            .eq("id", user_id)
            .execute()
        )
        if not res.data:
            return jsonify({"ok": False, "error": "Usuario no encontrado."}), 404

        user = res.data[0]
        dia_final = max(user["dia_actual"], nuevo_dia)
        zombis_final = user["zombis_derrotados"] + max(0, zombis_sumados)
        victorias_final = user["partidas_ganadas"] + (1 if gano_nivel else 0)

        supabase.table("usuarios").update({
            "dia_actual": dia_final,
            "zombis_derrotados": zombis_final,
            "partidas_ganadas": victorias_final
        }).eq("id", user_id).execute()

        return jsonify({
            "ok": True,
            "user": {
                "username": session["username"],
                "dia_actual": dia_final,
                "zombis_derrotados": zombis_final,
                "partidas_ganadas": victorias_final
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error al guardar: {str(e)}"}), 500


@app.route("/api/ranking", methods=["GET"])
def ranking():
    try:
        res = (
            supabase.table("usuarios")
            .select("username, dia_actual, zombis_derrotados, partidas_ganadas")
            .order("dia_actual", desc=True)
            .order("zombis_derrotados", desc=True)
            .limit(10)
            .execute()
        )
        return jsonify(res.data or [])
    except Exception:
        return jsonify([])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
