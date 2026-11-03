from cryptography.fernet import Fernet

# Generar clave
key = Fernet.generate_key().decode()
print("Tu DB_MASTER_KEY:", key)
