# ==========================================================
# reparar_clave_aes.py
# ----------------------------------------------------------
# Repara o genera de forma segura la clave AES principal
# utilizada para cifrar y descifrar tokens en usuarios.db.
#
# - Verifica existencia de data/secure/clave_aes.key
# - Si no existe, la crea y la sincroniza con entorno
# - Garantiza que el bot no vuelva a dar "Token inválido"
# ==========================================================

import os
from pathlib import Path

# Asegurar estructura de carpetas
SECURE_DIR = Path("data") / "secure"
SECURE_DIR.mkdir(parents=True, exist_ok=True)
KEY_FILE = SECURE_DIR / "clave_aes.key"

# Importar herramientas de seguridad
from utils.security import load_master_key, _read_or_create_keyfile

def reparar_clave():
    """
    Garantiza que la clave AES esté correctamente configurada
    tanto en archivo local como en entorno.
    """
    print("🔍 Verificando clave AES...")

    # 1️⃣ Obtener clave actual
    clave = os.environ.get("DB_MASTER_KEY")
    if not clave:
        clave = load_master_key()
        if clave:
            os.environ["DB_MASTER_KEY"] = clave

    # 2️⃣ Forzar creación de archivo si no existe
    if not KEY_FILE.exists():
        print("⚠️ No existe data/secure/clave_aes.key. Creando nueva...")
        nueva_clave = _read_or_create_keyfile()
        os.environ["DB_MASTER_KEY"] = nueva_clave
        print(f"✅ Nueva clave creada y guardada en {KEY_FILE}")
    else:
        print(f"✅ Archivo de clave existente: {KEY_FILE}")

    # 3️⃣ Verificar que la clave funcione
    try:
        from utils.security import cifrar, descifrar
        test_token = cifrar("Prueba BotDeEfra")
        test_text = descifrar(test_token)
        if test_text == "Prueba BotDeEfra":
            print("🟢 Prueba de cifrado/descifrado exitosa.")
        else:
            print("🔴 Error al descifrar la prueba. Puede haber conflicto en la clave.")
    except Exception as e:
        print(f"❌ Error al probar cifrado: {e}")

    print("\n✨ Revisión completada. Reinicia el bot para aplicar los cambios.")


if __name__ == "__main__":
    reparar_clave()
