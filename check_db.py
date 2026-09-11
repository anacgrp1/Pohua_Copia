from app.auth import passwords

hash_guardado = "pbkdf2_sha256$480000$r3q6rn66I9l36woefxrgzA==$d/TobhzyowSVRNTsz6XHnPb6xcMbcBjPDM6v5yt7LC8="
print("Verifying password123:", passwords.verificar("password123", hash_guardado))
print("Verifying Tu contraseña:", passwords.verificar("Tu contraseña", hash_guardado))
